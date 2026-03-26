//Conta para teste
//dados.guava@ecfo.com.br
//Dados@157029

// ====================================================================
// 00_UTILITARIOS.GS - Funções auxiliares base
// ====================================================================

const Utilitarios = {
  
  /**
   * Formata data para padrão YYYY-MM-DD
   */
  formatarData: function(data) {
    if (!(data instanceof Date)) {
      data = new Date(data);
    }
    const ano = data.getFullYear();
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const dia = String(data.getDate()).padStart(2, '0');
    return `${ano}-${mes}-${dia}`;
  },
  
  /**
   * Formata data para padrão MM/YYYY
   */
  formatarMesAno: function(data) {
    if (!(data instanceof Date)) {
      data = new Date(data);
    }
    const mes = String(data.getMonth() + 1).padStart(2, '0');
    const ano = data.getFullYear();
    return `${mes}/${ano}`;
  },
  
  /**
   * Verifica se data é do mês atual
   */
  ehMesAtual: function(data) {
    const hoje = new Date();
    const dataVerificar = new Date(data);
    return dataVerificar.getMonth() === hoje.getMonth() && 
           dataVerificar.getFullYear() === hoje.getFullYear();
  },
  
  /**
   * Converte timestamp Unix (segundos) para Date
   */
  timestampParaData: function(timestamp) {
    return new Date(timestamp * 1000);
  },
  
  /**
   * Lookup triplo: Empresa + Conta + SKU → Custo
   */
  lookupCustoSKU: function(nomeEmpresa, nomeConta, sku) {
    try {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName('Lookups_SKU');
      
      if (!sheet) return 0;
      
      const dados = sheet.getDataRange().getValues();
      
      for (let i = 1; i < dados.length; i++) {
        if (dados[i][0] === nomeEmpresa && 
            dados[i][1] === nomeConta && 
            dados[i][2] === sku) {
          return parseFloat(dados[i][3]) || 0;
        }
      }
      
      return 0;
    } catch (erro) {
      Logger.registrar('ERROR', nomeEmpresa, nomeConta, 
        'Erro no lookup SKU', { sku, erro: erro.toString() });
      return 0;
    }
  },
  
  /**
   * Gerar HMAC SHA256 para assinatura TikTok
   */
  gerarAssinaturaTikTok: function(appSecret, params) {
    const sortedKeys = Object.keys(params).sort();
    let signString = '';
    
    sortedKeys.forEach(key => {
      signString += key + params[key];
    });
    
    const signature = Utilities.computeHmacSha256Signature(
      signString, 
      appSecret
    );
    
    return Utilities.base64Encode(signature);
  },
  
  /**
   * Determinar estratégia de fracionamento baseado em volume
   */
  determinarFracionamento: function(totalOrders) {
    if (totalOrders <= 5000) {
      return { tipo: 'MENSAL', dias: 30 };
    } else if (totalOrders <= 15000) {
      return { tipo: 'QUINZENAL', dias: 15 };
    } else if (totalOrders <= 30000) {
      return { tipo: 'SEMANAL', dias: 7 };
    } else {
      return { tipo: 'DIARIO', dias: 1 };
    }
  },
  
  /**
   * Classificar tipo de tarifa TikTok
   */
  classificarTarifaTikTok: function(feeType) {
    const mapeamento = {
      'Commission Fee': 'Tarifas de Marketplace',
      'Service Fee': 'Tarifas de Marketplace',
      'Transaction Fee': 'Tarifas de Marketplace',
      'Payment Processing Fee': 'Tarifas de Marketplace',
      'Affiliate Commission': 'Tarifas de Marketplace',
      'Affiliate Partner Commission': 'Tarifas de Marketplace',
      'Shipping Fee': 'Frete',
      'Logistics Fee': 'Frete',
      'Advertising Fee': 'TikTok Ads',
      'Promotion Fee': 'Descontos'
    };
    
    return mapeamento[feeType] || 'Outras';
  },
  
  /**
   * Validar formato de shop_id TikTok
   */
  validarShopId: function(shopId) {
    return shopId && /^\d+$/.test(shopId.toString());
  },
  
  /**
   * Calcular diferença em dias entre datas
   */
  calcularDiferencaDias: function(dataInicio, dataFim) {
    const inicio = new Date(dataInicio);
    const fim = new Date(dataFim);
    const diff = Math.abs(fim - inicio);
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
  },
  
  /**
   * Gerar períodos fracionados
   */
  gerarPeriodos: function(dataInicio, dataFim, diasPorPeriodo) {
    const periodos = [];
    let inicioAtual = new Date(dataInicio);
    const fimTotal = new Date(dataFim);
    
    while (inicioAtual <= fimTotal) {
      const fimAtual = new Date(inicioAtual);
      fimAtual.setDate(fimAtual.getDate() + diasPorPeriodo - 1);
      
      if (fimAtual > fimTotal) {
        fimAtual.setTime(fimTotal.getTime());
      }
      
      periodos.push({
        inicio: this.formatarData(inicioAtual),
        fim: this.formatarData(fimAtual)
      });
      
      inicioAtual.setDate(inicioAtual.getDate() + diasPorPeriodo);
    }
    
    return periodos;
  },
  
  /**
   * Sanitizar nome de empresa/conta para aba
   */
  sanitizarNomeAba: function(nome) {
    return nome
      .replace(/[\/\\?*\[\]]/g, '') // Remove caracteres inválidos
      .substring(0, 100); // Limite de 100 caracteres
  },
  
  /**
   * Formatar moeda BRL
   */
  formatarMoeda: function(valor) {
    return `R$ ${parseFloat(valor).toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })}`;
  }
};