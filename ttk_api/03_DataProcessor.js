// ====================================================================
// 03_DATA_PROCESSOR.GS - Processa dados TikTok Shop
// ====================================================================

const DataProcessor = {
  
  processarEmpresaOrders: function(config) {
    try {
      config = ConfigManager.verificarERenovarToken(config);
      const periodo = this.determinarPeriodo(config);
      
      Logger.registrar('INFO', config.nomeEmpresa, config.nomeConta,
        `Processando período: ${periodo.inicio} a ${periodo.fim}`, {});
      
      const ordersData = this.buscarOrdersComPaginacao(
        config.accessToken,
        config.shopId,
        periodo.inicio,
        periodo.fim
      );
      
      if (ordersData.length === 0) {
        Logger.registrar('INFO', config.nomeEmpresa, config.nomeConta,
          'Nenhum pedido encontrado', {});
        return { vendas: 0, pedidos: 0 };
      }
      
      const dadosProcessados = this.processarOrders(ordersData, config);
      const agregados = this.agregarPorMes(dadosProcessados, config);
      
      Aggregator.salvarDadosAgregados(config.abaDestino, agregados);
      
      const novaData = periodo.fim;
      const novoStatus = Utilitarios.ehMesAtual(new Date(novaData))
        ? 'ATUALIZADO'
        : 'EM_PROGRESSO';
      
      ConfigManager.atualizarStatus(
        config.nomeEmpresa,
        config.nomeConta,
        novoStatus,
        novaData
      );
      
      const totalVendas = agregados.reduce((sum, a) => sum + a.vendasTotal, 0);
      
      Logger.registrar('SUCCESS', config.nomeEmpresa, config.nomeConta,
        'Processamento concluído', { pedidos: ordersData.length, vendas: totalVendas });
      
      return { vendas: totalVendas, pedidos: ordersData.length };
      
    } catch (erro) {
      Logger.registrar('ERROR', config.nomeEmpresa, config.nomeConta,
        'Erro no processamento', { erro: erro.toString() });
      throw erro;
    }
  },
  
  determinarPeriodo: function(config) {
    const hoje = new Date();
    let dataInicio, dataFim;
    
    if (config.status === 'PENDENTE') {
      const partes = config.ultimaData.split('-');
      dataInicio = new Date(partes[0], partes[1] - 1, partes[2]);
    } else if (config.status === 'EM_PROGRESSO') {
      const partes = config.ultimaData.split('-');
      const ultimaData = new Date(partes[0], partes[1] - 1, partes[2]);
      dataInicio = new Date(ultimaData.getFullYear(), ultimaData.getMonth() + 1, 1);
    } else {
      dataInicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
    }
    
    dataFim = new Date(dataInicio.getFullYear(), dataInicio.getMonth() + 1, 0);
    if (dataFim > hoje) dataFim = hoje;
    
    return {
      inicio: Utilitarios.formatarData(dataInicio),
      fim: Utilitarios.formatarData(dataFim)
    };
  },
  
  buscarOrdersComPaginacao: function(accessToken, shopId, dataInicio, dataFim) {
    let todosOrders = [];
    let cursor = null;
    let tentativas = 0;
    const maxTentativas = 200;
    
    do {
      try {
        const resultado = TikTokAPI.buscarOrders(
          accessToken,
          shopId,
          dataInicio,
          dataFim,
          cursor
        );
        
        if (resultado.orders && resultado.orders.length > 0) {
          todosOrders = todosOrders.concat(resultado.orders);
        }
        
        cursor = resultado.next_cursor;
        
        if (!cursor || !resultado.more) break;
        
        tentativas++;
        if (tentativas >= maxTentativas) break;
        
        Utilities.sleep(100);
        
      } catch (erro) {
        console.log(`Erro na paginação: ${erro.toString()}`);
        break;
      }
    } while (cursor);
    
    return todosOrders;
  },
  
  processarOrders: function(orders, config) {
    return orders.map(order => {
      const items = order.item_list || [];
      let totalProduto = 0;
      let skus = [];
      
      items.forEach(item => {
        totalProduto += parseFloat(item.sale_price) * parseInt(item.quantity);
        if (item.seller_sku) skus.push(item.seller_sku);
      });
      
      return {
        order_id: order.order_id,
        created_time: order.create_time,
        status: order.order_status,
        skus: skus.join(', '),
        quantidade: items.reduce((sum, i) => sum + parseInt(i.quantity), 0),
        valor_produto: totalProduto,
        tarifa_tiktok: parseFloat(order.payment?.platform_commission || 0),
        frete: parseFloat(order.payment?.shipping_fee || 0),
        desconto_seller: parseFloat(order.payment?.seller_discount || 0),
        desconto_tiktok: parseFloat(order.payment?.platform_discount || 0),
        tiktok_ads: 0 // Será preenchido por Finance API
      };
    });
  },
  
  agregarPorMes: function(dados, config) {
    const agregadosPorMes = new Map();
    
    dados.forEach(item => {
      const data = Utilitarios.timestampParaData(item.created_time);
      const mesAno = Utilitarios.formatarMesAno(data);
      
      if (!agregadosPorMes.has(mesAno)) {
        agregadosPorMes.set(mesAno, {
          mesAno: mesAno,
          empresa: config.nomeEmpresa,
          conta: config.nomeConta,
          vendasTotal: 0,
          reembolsoTotal: 0,
          descontosTotal: 0,
          cancelamentoTotal: 0,
          tarifasTotal: 0,
          frete: 0,
          tiktokAds: 0
        });
      }
      
      const agregado = agregadosPorMes.get(mesAno);
      const status = (item.status || '').toLowerCase();
      
      if (status.includes('completed') || status.includes('delivered')) {
        agregado.vendasTotal += item.valor_produto;
      }
      
      if (status.includes('cancelled')) {
        agregado.cancelamentoTotal += item.valor_produto;
      }
      
      agregado.tarifasTotal += item.tarifa_tiktok;
      agregado.frete += item.frete;
      agregado.descontosTotal += item.desconto_seller + item.desconto_tiktok;
      agregado.tiktokAds += item.tiktok_ads;
    });
    
    return Array.from(agregadosPorMes.values());
  }
};