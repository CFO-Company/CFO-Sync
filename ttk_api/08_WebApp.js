// ====================================================================
// 08_WEBAPP.GS - Endpoint OAuth redirect handler
// ====================================================================

function doGet(e) {
  try {
    Logger.registrar('INFO', '', '', 'OAuth callback recebido', 
      { params: JSON.stringify(e.parameter) });
    
    const code = e.parameter.code;
    const state = e.parameter.state;
    
    if (!code) {
      Logger.registrar('ERROR', '', '', 'CODE ausente no callback', 
        { params: JSON.stringify(e.parameter) });
      return criarPaginaErro('CODE não recebido. URL de callback incorreta.');
    }
    
    if (!state) {
      Logger.registrar('ERROR', '', '', 'STATE ausente no callback', 
        { params: JSON.stringify(e.parameter) });
      return criarPaginaErro('STATE não recebido. URL inválida.');
    }
    
    // Parse do state
    const partes = state.split('_');
    const nomeConta = partes[partes.length - 1].replace(/_/g, ' ');
    const nomeEmpresa = partes.slice(0, -1).join('_').replace(/_/g, ' ');
    
    Logger.registrar('INFO', nomeEmpresa, nomeConta,
      'Processando autorização', { code: code.substring(0, 10) + '...' });
    
    // Trocar code por tokens
    const tokens = TikTokAPI.trocarCodePorTokens(code);
    
    // Salvar tokens
    ConfigManager.salvarTokens(nomeEmpresa, nomeConta, tokens);
    
    // Enviar email
    Logger.enviarEmailNovaAutorizacao(nomeEmpresa, nomeConta, tokens.shop_id);
    
    Logger.registrar('SUCCESS', nomeEmpresa, nomeConta,
      'Autorização concluída', { shop_id: tokens.shop_id });
    
    return criarPaginaSucesso(nomeEmpresa, nomeConta, tokens.shop_id);
    
  } catch (erro) {
    Logger.registrar('ERROR', '', '', 
      'Falha no OAuth callback', 
      { erro: erro.toString(), stack: erro.stack });
    
    return criarPaginaErro(`Erro ao processar autorização: ${erro.message}`);
  }
}

function criarPaginaSucesso(nomeEmpresa, nomeConta, shopId) {
  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
          font-family: 'Arial', sans-serif;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
          padding: 20px;
        }
        .card {
          background: white;
          border-radius: 20px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          padding: 40px;
          max-width: 500px;
          width: 100%;
          text-align: center;
          animation: slideUp 0.5s ease;
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(30px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .icon { font-size: 80px; margin-bottom: 20px; }
        h1 { color: #2d3748; font-size: 28px; margin-bottom: 15px; }
        .info {
          background: #f7fafc;
          border-radius: 10px;
          padding: 20px;
          margin: 20px 0;
          text-align: left;
        }
        .info-row {
          display: flex;
          justify-content: space-between;
          margin-bottom: 10px;
          padding-bottom: 10px;
          border-bottom: 1px solid #e2e8f0;
        }
        .info-label { font-weight: bold; color: #4a5568; }
        .info-value { color: #2d3748; }
        .close-btn {
          margin-top: 30px;
          padding: 12px 30px;
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          border: none;
          border-radius: 25px;
          font-size: 16px;
          cursor: pointer;
        }
      </style>
    </head>
    <body>
      <div class="card">
        <div class="icon">✅</div>
        <h1>Autorização Concluída!</h1>
        <div class="info">
          <div class="info-row">
            <span class="info-label">Empresa:</span>
            <span class="info-value">${nomeEmpresa}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Conta:</span>
            <span class="info-value">${nomeConta}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Shop ID:</span>
            <span class="info-value">${shopId}</span>
          </div>
        </div>
        <button class="close-btn" onclick="window.close()">Fechar Janela</button>
      </div>
    </body>
    </html>
  `;
  
  return HtmlService.createHtmlOutput(html).setTitle('Autorização Concluída');
}

function criarPaginaErro(mensagem) {
  const html = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <style>
        body {
          font-family: Arial;
          background: #f8f9fa;
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 100vh;
        }
        .error-container {
          background: white;
          padding: 40px;
          border-radius: 10px;
          box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
          text-align: center;
          max-width: 500px;
        }
        .error-icon { font-size: 48px; color: #e74c3c; margin-bottom: 20px; }
        .close-btn {
          background: #e74c3c;
          color: white;
          border: none;
          padding: 12px 24px;
          border-radius: 5px;
          cursor: pointer;
          font-size: 16px;
        }
      </style>
    </head>
    <body>
      <div class="error-container">
        <div class="error-icon">❌</div>
        <h1>Erro na Autorização</h1>
        <p>${mensagem}</p>
        <button class="close-btn" onclick="window.close()">Fechar Janela</button>
      </div>
    </body>
    </html>
  `;
  
  return HtmlService.createHtmlOutput(html).setTitle('Erro na Autorização');
}