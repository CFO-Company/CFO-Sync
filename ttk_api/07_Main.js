// ====================================================================
// 07_MAIN.GS - Orquestração principal, menu e triggers
// ====================================================================

function onOpen() {
  const ui = SpreadsheetApp.getUi();
  
  ui.createMenu('TikTok Shop')
    .addSubMenu(ui.createMenu('Importação')
      .addItem('Atualizar Empresa Específica', 'mostrarSelecaoEmpresa')
      .addItem('Atualizar Todas Empresas', 'atualizarTodasEmpresas')
      .addItem('Pesquisa Detalhada', 'mostrarPesquisaDetalhada'))
    .addSubMenu(ui.createMenu('Gerenciar Empresas')
      .addItem('Criar Abas Empresas', 'criarAbaEmpresa')
      .addItem('Autorizar Nova Empresa', 'mostrarAutorizarEmpresa')
      .addItem('Resetar Empresa Específica', 'mostrarResetarEmpresa'))
    .addSubMenu(ui.createMenu('Sistema')
      .addItem('Mostrar Triggers', 'mostrarTriggers')
      .addItem('Limpar Logs Antigos', 'limparLogs')
      .addItem('Verificar Saúde da API', 'mostrarSaudeAPI')
      .addItem('Diagnóstico Completo', 'executarDiagnosticoCompleto'))
    .addToUi();
}

function setupInicial() {
  try {
    ConfigManager.obterAba();
    SheetManager.obterAbaLogs();
    SheetManager.obterAbaPesquisa();
    SheetManager.obterAbaLookupsSKU();
    
    configurarTriggersAutomaticos();
    
    Logger.registrar('INFO', '', '', 'Setup inicial concluído', {});
    
    SpreadsheetApp.getUi().alert(
      'Estrutura criada!\n\n' +
      'Abas criadas:\n' +
      '- Configuracao\n' +
      '- Lookups_SKU\n' +
      '- Pesquisa\n' +
      '- Logs\n\n' +
      'Triggers configurados:\n' +
      '- Sincronização: Diária às 02h\n' +
      '- Limpeza de logs: Diária às 23h'
    );
  } catch (erro) {
    Logger.registrar('ERROR', '', '', 'Erro no setup inicial', 
      { erro: erro.toString() });
  }
}

function configurarTriggersAutomaticos() {
  ScriptApp.getProjectTriggers().forEach(t => 
    ScriptApp.deleteTrigger(t)
  );
  
  ScriptApp.newTrigger('executarSincronizacaoComRelatorio')
    .timeBased()
    .atHour(2)
    .everyDays(1)
    .create();
  
  ScriptApp.newTrigger('limparLogsAutomatico')
    .timeBased()
    .atHour(23)
    .everyDays(1)
    .create();
}

function atualizarTodasEmpresas() {
  try {
    const inicio = new Date();
    const empresas = ConfigManager.lerConfiguracao()
      .filter(e => e.status !== 'PAUSADO' && e.accessToken);
    
    Logger.registrar('INFO', '', '', 
      `Iniciando sincronização: ${empresas.length} contas`, {});
    
    const resumo = {
      detalhes: [],
      totalizadores: {
        contas: empresas.length,
        sucessos: 0,
        vendas: 0,
        pedidos: 0
      },
      duracao: ''
    };
    
    empresas.forEach(config => {
      try {
        const resultado = DataProcessor.processarEmpresaOrders(config);
        
        resumo.detalhes.push({
          empresa: config.nomeEmpresa,
          conta: config.nomeConta,
          sucesso: true,
          vendas: resultado.vendas,
          pedidos: resultado.pedidos,
          mensagem: 'Processado com sucesso'
        });
        
        resumo.totalizadores.sucessos++;
        resumo.totalizadores.vendas += resultado.vendas;
        resumo.totalizadores.pedidos += resultado.pedidos;
        
      } catch (erro) {
        resumo.detalhes.push({
          empresa: config.nomeEmpresa,
          conta: config.nomeConta,
          sucesso: false,
          vendas: 0,
          pedidos: 0,
          mensagem: erro.message || erro.toString()
        });
      }
    });
    
    const duracao = Math.round((new Date() - inicio) / 60000);
    resumo.duracao = `${duracao} minuto(s)`;
    
    Logger.enviarRelatorioSincronizacao(resumo);
    Logger.registrar('SUCCESS', '', '', 'Sincronização concluída', resumo.totalizadores);
    
  } catch (erroGlobal) {
    Logger.registrar('ERROR', '', '', 'Erro crítico na sincronização', 
      { erro: erroGlobal.toString() });
    throw erroGlobal;
  }
}

function executarSincronizacaoComRelatorio() {
  atualizarTodasEmpresas();
}

function limparLogsAutomatico() {
  SheetManager.limparLogs();
}

function mostrarSelecaoEmpresa() {
  const html = HtmlService.createHtmlOutputFromFile('Interface_Selecao_Empresa')
    .setWidth(650).setHeight(700);
  SpreadsheetApp.getUi().showModalDialog(html, 'TikTok Shop Automation');
}

function mostrarAutorizarEmpresa() {
  const html = HtmlService.createHtmlOutputFromFile('Interface_Autorizar_Empresa')
    .setWidth(650).setHeight(700);
  SpreadsheetApp.getUi().showModalDialog(html, 'TikTok Shop Automation');
}

function getEmpresasParaSelecao() {
  return ConfigManager.obterEmpresasAgrupadas();
}

function gerarURLAutorizacao(nomeEmpresa, nomeConta) {
  const state = `${nomeEmpresa.replace(/\s/g, '_')}_${nomeConta.replace(/\s/g, '_')}`;
  
  // URL CORRETA para autorização de SELLERS
  const url = `https://services.tiktokshop.com/open/authorize?service_id=${TikTokAPI.APP_KEY}&state=${encodeURIComponent(state)}`;
  
  const existe = ConfigManager.lerConfiguracao().find(e => 
    e.nomeEmpresa === nomeEmpresa && e.nomeConta === nomeConta
  );
  
  if (!existe) {
    ConfigManager.adicionarEmpresa(nomeEmpresa, nomeConta);
  }
  
  Logger.registrar('INFO', nomeEmpresa, nomeConta, 
    'URL de autorização gerada', { url: url });
  
  return url;
}

function executarDiagnosticoCompleto() {
  const ui = SpreadsheetApp.getUi();
  let relatorio = 'DIAGNÓSTICO COMPLETO\n\n';
  
  const configs = ConfigManager.lerConfiguracao();
  relatorio += `Total de empresas: ${configs.length}\n`;
  relatorio += `Empresas ativas: ${configs.filter(c => c.accessToken).length}\n\n`;
  
  const triggers = ScriptApp.getProjectTriggers();
  relatorio += `Triggers configurados: ${triggers.length}\n`;
  triggers.forEach(t => {
    relatorio += `- ${t.getHandlerFunction()}\n`;
  });
  
  ui.alert(relatorio);
}

function criarAbaEmpresa() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const configs = ConfigManager.lerConfiguracao();
  
  let criadas = 0;
  configs.forEach(config => {
    if (!ss.getSheetByName(config.abaDestino)) {
      SheetManager.criarAbaEmpresaSeNecessario(config.abaDestino);
      criadas++;
    }
  });
  
  SpreadsheetApp.getUi().alert(`${criadas} abas criadas!`);
}

/**
 * Testar conexão (health check)
 */
function testarConexao (accessToken, shopId) {
  try {
    const url = `${this.BASE_URL}/api/shop/get_authorized_shop`;
    
    const options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'x-tts-access-token': accessToken
      },
      payload: JSON.stringify({}),
      muteHttpExceptions: true
    };
    
    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();
    const resultado = JSON.parse(response.getContentText());
    
    return {
      sucesso: statusCode === 200 && resultado.code === 0,
      statusCode: statusCode,
      mensagem: resultado.code === 0 ? 'Conectado' : resultado.message,
      shopName: resultado.data?.shop_name || '',
      shopId: resultado.data?.shop_id || ''
    };
  } catch (erro) {
    return {
      sucesso: false,
      statusCode: 0,
      mensagem: erro.toString()
    };
  }
}