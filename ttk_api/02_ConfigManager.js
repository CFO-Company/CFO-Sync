// ====================================================================
// 02_CONFIG_MANAGER.GS - Gerencia aba Configuracao
// ====================================================================

const ConfigManager = {
  
  /**
   * Obter aba Configuracao (cria se não existir)
   */
  obterAba: function() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName('Configuracao');
    
    if (!sheet) {
      sheet = ss.insertSheet('Configuracao', 0);
      
      const headers = [
        'Nome Empresa', 'Nome Conta', 'APP_KEY', 'APP_SECRET',
        'ACCESS_TOKEN', 'REFRESH_TOKEN', 'EXPIRA_EM', 
        'SHOP_ID', 'SELLER_ID', 'Aba Destino', 'Última Data', 'Status'
      ];
      
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.getRange(1, 1, 1, headers.length)
        .setFontWeight('bold')
        .setBackground('#4a86e8')
        .setFontColor('#ffffff');
      sheet.setFrozenRows(1);
      
      // Larguras otimizadas
      const larguras = [150, 150, 180, 200, 250, 200, 150, 120, 120, 150, 120, 120];
      larguras.forEach((largura, i) => {
        sheet.setColumnWidth(i + 1, largura);
      });
    }
    
    return sheet;
  },
  
  /**
   * Ler todas configurações
   */
  lerConfiguracao: function() {
    const sheet = this.obterAba();
    const dados = sheet.getDataRange().getValues();
    const configs = [];
    
    for (let i = 1; i < dados.length; i++) {
      const linha = dados[i];
      
      if (!linha[0]) continue; // Pula linhas vazias
      
      configs.push({
        linha: i + 1,
        nomeEmpresa: linha[0],
        nomeConta: linha[1],
        appKey: linha[2] || TikTokAPI.APP_KEY,
        appSecret: linha[3] || TikTokAPI.APP_SECRET,
        accessToken: linha[4],
        refreshToken: linha[5],
        expiraEm: linha[6],
        shopId: linha[7],
        sellerId: linha[8],
        abaDestino: linha[9],
        ultimaData: linha[10] ? Utilitarios.formatarData(linha[10]) : '2025-01-01',
        status: linha[11] || 'PENDENTE'
      });
    }
    
    return configs;
  },
  
  /**
   * Salvar tokens OAuth
   */
  salvarTokens: function(nomeEmpresa, nomeConta, tokens) {
    const sheet = this.obterAba();
    const configs = this.lerConfiguracao();
    
    const config = configs.find(c => 
      c.nomeEmpresa === nomeEmpresa && c.nomeConta === nomeConta
    );
    
    if (!config) {
      throw new Error(`Empresa/Conta não encontrada: ${nomeEmpresa} - ${nomeConta}`);
    }
    
    const linha = config.linha;
    
    sheet.getRange(linha, 5).setValue(tokens.access_token);
    sheet.getRange(linha, 6).setValue(tokens.refresh_token);
    sheet.getRange(linha, 7).setValue(new Date(tokens.expira_em));
    sheet.getRange(linha, 8).setValue(tokens.shop_id);
    sheet.getRange(linha, 9).setValue(tokens.seller_id);
    
    Logger.registrar('SUCCESS', nomeEmpresa, nomeConta, 
      'Tokens salvos com sucesso', { shop_id: tokens.shop_id });
  },
  
  /**
   * Verificar e renovar token se expirado
   */
  verificarERenovarToken: function(config) {
    const agora = new Date().getTime();
    const expiraEm = config.expiraEm instanceof Date 
      ? config.expiraEm.getTime() 
      : new Date(config.expiraEm).getTime();
    
    // Se falta menos de 10 min para expirar, renova
    if (expiraEm - agora < 600000) {
      Logger.registrar('INFO', config.nomeEmpresa, config.nomeConta,
        'Renovando token expirado', {});
      
      const novosTokens = TikTokAPI.renovarToken(config.refreshToken);
      this.salvarTokens(config.nomeEmpresa, config.nomeConta, novosTokens);
      
      config.accessToken = novosTokens.access_token;
      config.refreshToken = novosTokens.refresh_token;
      config.expiraEm = novosTokens.expira_em;
      
      Logger.registrar('SUCCESS', config.nomeEmpresa, config.nomeConta,
        'Token renovado', {});
    }
    
    return config;
  },
  
  /**
   * Atualizar status e data
   */
  atualizarStatus: function(nomeEmpresa, nomeConta, novoStatus, novaData = null) {
    const sheet = this.obterAba();
    const configs = this.lerConfiguracao();
    
    const config = configs.find(c => 
      c.nomeEmpresa === nomeEmpresa && c.nomeConta === nomeConta
    );
    
    if (!config) return;
    
    const linha = config.linha;
    
    if (novaData) {
      sheet.getRange(linha, 11).setValue(novaData);
    }
    
    sheet.getRange(linha, 12).setValue(novoStatus);
  },
  
  /**
   * Adicionar nova empresa
   */
  adicionarEmpresa: function(nomeEmpresa, nomeConta) {
    const sheet = this.obterAba();
    const ultimaLinha = sheet.getLastRow();
    
    const abaDestino = nomeConta === 'Conta Principal' 
      ? nomeEmpresa 
      : `${nomeEmpresa} - ${nomeConta}`;
    
    const novaLinha = [
      nomeEmpresa,
      nomeConta,
      TikTokAPI.APP_KEY,
      TikTokAPI.APP_SECRET,
      '', // ACCESS_TOKEN
      '', // REFRESH_TOKEN
      '', // EXPIRA_EM
      '', // SHOP_ID
      '', // SELLER_ID
      Utilitarios.sanitizarNomeAba(abaDestino),
      '2025-01-01',
      'PENDENTE'
    ];
    
    sheet.getRange(ultimaLinha + 1, 1, 1, novaLinha.length).setValues([novaLinha]);
    
    Logger.registrar('INFO', nomeEmpresa, nomeConta,
      'Empresa adicionada à configuração', {});
    
    return abaDestino;
  },
  
  /**
   * Obter empresas agrupadas (para seleção)
   */
  obterEmpresasAgrupadas: function() {
    const empresas = this.lerConfiguracao()
      .filter(e => e.accessToken);
    
    const empresasUnicas = new Map();
    
    empresas.forEach(e => {
      if (!empresasUnicas.has(e.nomeEmpresa)) {
        empresasUnicas.set(e.nomeEmpresa, {
          nomeEmpresa: e.nomeEmpresa,
          contas: [],
          status: e.status
        });
      }
      empresasUnicas.get(e.nomeEmpresa).contas.push(e.nomeConta);
    });
    
    return Array.from(empresasUnicas.values()).map(e => ({
      nomeEmpresa: e.nomeEmpresa,
      status: e.status,
      totalContas: e.contas.length
    }));
  }
};