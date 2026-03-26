// ====================================================================
// 04_AGGREGATOR.GS - Salva dados agregados nas abas
// ====================================================================

const Aggregator = {
  
  salvarDadosAgregados: function(abaDestino, agregados) {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(abaDestino);
    
    if (!sheet) {
      sheet = SheetManager.criarAbaEmpresaSeNecessario(abaDestino);
    }
    
    const dadosExistentes = this.carregarDadosExistentes(sheet);
    
    agregados.forEach(agregado => {
      const chave = `${agregado.mesAno}_${agregado.empresa}_${agregado.conta}`;
      
      const linha = [
        agregado.mesAno,
        agregado.empresa,
        agregado.conta,
        agregado.vendasTotal,
        -agregado.reembolsoTotal,
        -agregado.descontosTotal,
        -agregado.cancelamentoTotal,
        -agregado.tarifasTotal,
        -agregado.frete,
        -agregado.tiktokAds
      ];
      
      if (dadosExistentes.has(chave)) {
        const linhaExistente = dadosExistentes.get(chave);
        sheet.getRange(linhaExistente, 1, 1, linha.length).setValues([linha]);
      } else {
        const ultimaLinha = sheet.getLastRow();
        sheet.getRange(ultimaLinha + 1, 1, 1, linha.length).setValues([linha]);
      }
    });
    
    this.formatarAba(sheet);
  },
  
  carregarDadosExistentes: function(sheet) {
    const dados = sheet.getDataRange().getValues();
    const map = new Map();
    
    for (let i = 1; i < dados.length; i++) {
      const linha = dados[i];
      let mesAno = linha[0];
      const empresa = linha[1];
      const conta = linha[2];
      
      if (mesAno instanceof Date) {
        const mes = String(mesAno.getMonth() + 1).padStart(2, '0');
        const ano = mesAno.getFullYear();
        mesAno = `${mes}/${ano}`;
      }
      
      if (mesAno && empresa && conta) {
        const chave = `${mesAno}_${empresa}_${conta}`;
        map.set(chave, i + 1);
      }
    }
    
    return map;
  },
  
  formatarAba: function(sheet) {
    const ultimaLinha = sheet.getLastRow();
    
    if (ultimaLinha > 1) {
      sheet.getRange(2, 4, ultimaLinha - 1, 7)
        .setNumberFormat('R$ #,##0.00');
      
      sheet.getRange(2, 1, ultimaLinha - 1, sheet.getLastColumn())
        .sort({column: 1, ascending: false});
    }
  }
};