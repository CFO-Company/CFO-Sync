// ====================================================================
// 05_SHEET_MANAGER.GS - Gerencia abas da planilha
// ====================================================================

const SheetManager = {
  
  /**
   * Obter aba Logs
   */
  obterAbaLogs: function() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName('Logs');
    
    if (!sheet) {
      sheet = ss.insertSheet('Logs');
      
      const headers = [
        'Timestamp', 'Tipo', 'Empresa', 'Conta', 'Mensagem', 'Detalhes'
      ];
      
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
      sheet.setFrozenRows(1);
      
      // Larguras
      sheet.setColumnWidth(1, 150); // Timestamp
      sheet.setColumnWidth(2, 100); // Tipo
      sheet.setColumnWidth(3, 150); // Empresa
      sheet.setColumnWidth(4, 150); // Conta
      sheet.setColumnWidth(5, 300); // Mensagem
      sheet.setColumnWidth(6, 250); // Detalhes
    }
    
    return sheet;
  },
  
  /**
   * Obter aba Pesquisa
   */
  obterAbaPesquisa: function() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName('Pesquisa');
    
    if (!sheet) {
      sheet = ss.insertSheet('Pesquisa');
      
      const headers = [
        'Order ID', 'Data', 'Status', 'SKU', 'Quantidade',
        'Valor Produto', 'Tarifa TikTok', 'Frete',
        'Desconto Seller', 'Desconto TikTok', 'TikTok Ads', 'Cliente'
      ];
      
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
      sheet.setFrozenRows(1);
    }
    
    return sheet;
  },
  
  /**
   * Obter aba Lookups_SKU
   */
  obterAbaLookupsSKU: function() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName('Lookups_SKU');
    
    if (!sheet) {
      sheet = ss.insertSheet('Lookups_SKU');
      
      const headers = [
        'Nome Empresa', 'Nome Conta', 'SKU', 'Custo Unitário', 'Operação'
      ];
      
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.getRange(1, 1, 1, headers.length).setFontWeight('bold');
      sheet.setFrozenRows(1);
      
      // Exemplo
      const exemplo = [
        'Empresa A', 'Conta Principal', 'SKU001', 50.00, 'TikTok Shop'
      ];
      sheet.getRange(2, 1, 1, exemplo.length).setValues([exemplo]);
    }
    
    return sheet;
  },
  
  /**
   * Criar aba de empresa se não existir
   */
  criarAbaEmpresaSeNecessario: function(nomeAba) {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(nomeAba);
    
    if (!sheet) {
      sheet = ss.insertSheet(nomeAba);
      
      const headers = [
        'Mês/Ano', 'Empresa', 'Conta', 'Vendas Total',
        'Reembolso Total', 'Descontos Total', 'Cancelamento Total',
        'Tarifas Total', 'Frete', 'TikTok Ads'
      ];
      
      sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      sheet.getRange(1, 1, 1, headers.length)
        .setFontWeight('bold')
        .setBackground('#4a86e8')
        .setFontColor('#ffffff');
      sheet.setFrozenRows(1);
      
      // Ajustar larguras
      sheet.setColumnWidth(1, 100);  
      sheet.setColumnWidth(2, 150);  
      sheet.setColumnWidth(3, 150);  
      
      for (let i = 4; i <= 10; i++) {
        sheet.setColumnWidth(i, 120);
      }
      
      Logger.registrar('INFO', '', '', 
        `Aba "${nomeAba}" criada automaticamente`, {});
    }
    
    return sheet;
  },
  
  /**
   * Limpar aba Pesquisa
   */
  limparAbaPesquisa: function() {
    const sheet = this.obterAbaPesquisa();
    const lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      sheet.deleteRows(2, lastRow - 1);
    }
  },
  
  /**
   * Resetar todas as abas de empresas
   */
  resetarTodasAbas: function() {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const configs = ConfigManager.lerConfiguracao();
    let contadorReset = 0;
    
    configs.forEach(config => {
      const sheet = ss.getSheetByName(config.abaDestino);
      if (sheet) {
        const lastRow = sheet.getLastRow();
        if (lastRow > 1) {
          sheet.deleteRows(2, lastRow - 1);
          contadorReset++;
        }
      }
    });
    
    Logger.registrar('SUCCESS', '', '', 
      `${contadorReset} abas resetadas`, {});
    
    return contadorReset;
  },
  
  /**
   * Limpar logs mantendo apenas 1000 últimas linhas
   */
  limparLogs: function() {
    const sheet = this.obterAbaLogs();
    const ultimaLinha = sheet.getLastRow();
    
    if (ultimaLinha > 1001) {
      const linhasRemover = ultimaLinha - 1001;
      sheet.deleteRows(2, linhasRemover);
      
      Logger.registrar('INFO', '', '', 
        `${linhasRemover} logs antigos removidos`, {});
    }
  }
};