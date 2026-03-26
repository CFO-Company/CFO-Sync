// ====================================================================
// 06_LOGGER.GS - Sistema de logs e notificações
// ====================================================================

const CONFIG_EMAIL = {
  admin: 'bi2@cfocompany.com.br',
  enviarRelatorioAutomatico: true,
  enviarErros: true
};

const Logger = {
  
  /**
   * Registrar log
   */
  registrar: function(tipo, empresa, conta, mensagem, detalhes = {}) {
    try {
      const sheet = SheetManager.obterAbaLogs();
      const timestamp = new Date();
      
      const linha = [
        timestamp,
        tipo,
        empresa,
        conta,
        mensagem,
        JSON.stringify(detalhes)
      ];
      
      const ultimaLinha = sheet.getLastRow();
      sheet.getRange(ultimaLinha + 1, 1, 1, linha.length).setValues([linha]);
      
      // Aplicar cor por tipo
      const range = sheet.getRange(ultimaLinha + 1, 1, 1, linha.length);
      switch(tipo) {
        case 'SUCCESS':
          range.setBackground('#d4edda');
          break;
        case 'ERROR':
          range.setBackground('#f8d7da');
          break;
        case 'WARN':
          range.setBackground('#fff3cd');
          break;
        default:
          range.setBackground('#ffffff');
      }
      
    } catch (erro) {
      console.error('Erro ao registrar log:', erro);
    }
  },
  
  /**
   * Enviar relatório de sincronização
   */
  enviarRelatorioSincronizacao: function(resumo) {
    if (!CONFIG_EMAIL.enviarRelatorioAutomatico) return;
    
    const temErros = resumo.detalhes.some(d => !d.sucesso);
    const temDados = resumo.totalizadores.pedidos > 0;
    
    let assunto, corpo;
    
    if (temErros) {
      assunto = `Sincronização TikTok Shop - Erros detectados`;
      corpo = `SINCRONIZAÇÃO COM ERROS\n\n` +
        `RESUMO:\n` +
        `- Contas processadas: ${resumo.totalizadores.contas}\n` +
        `- Sucessos: ${resumo.totalizadores.sucessos}\n` +
        `- Erros: ${resumo.totalizadores.contas - resumo.totalizadores.sucessos}\n` +
        `- Pedidos importados: ${resumo.totalizadores.pedidos}\n` +
        `- Duração: ${resumo.duracao}\n\n` +
        `CONTAS COM ERRO:\n` +
        resumo.detalhes
          .filter(d => !d.sucesso)
          .map(d => `- ${d.empresa} - ${d.conta}\n  Erro: ${d.mensagem}`)
          .join('\n\n') + `\n\n` +
        `Ver logs: ${SpreadsheetApp.getActiveSpreadsheet().getUrl()}`;
      
    } else if (temDados) {
      assunto = `Sincronização TikTok Shop - ${resumo.totalizadores.pedidos} pedidos importados`;
      corpo = `SINCRONIZAÇÃO CONCLUÍDA!\n\n` +
        `RESUMO:\n` +
        `- Contas processadas: ${resumo.totalizadores.contas}\n` +
        `- Pedidos importados: ${resumo.totalizadores.pedidos}\n` +
        `- Vendas totais: R$ ${resumo.totalizadores.vendas.toLocaleString('pt-BR', {minimumFractionDigits: 2})}\n` +
        `- Duração: ${resumo.duracao}\n\n` +
        `CONTAS ATUALIZADAS:\n` +
        resumo.detalhes
          .filter(d => d.sucesso)
          .map(d => `- ${d.empresa} - ${d.conta}\n  ${d.pedidos} pedidos (R$ ${d.vendas.toLocaleString('pt-BR', {minimumFractionDigits: 2})})`)
          .join('\n\n') + `\n\n` +
        `Abrir planilha: ${SpreadsheetApp.getActiveSpreadsheet().getUrl()}`;
    } else {
      assunto = `Sincronização TikTok Shop - Nenhum dado encontrado`;
      corpo = `SINCRONIZAÇÃO SEM DADOS\n\n` +
        `A sincronização foi executada mas não encontrou novos pedidos.\n\n` +
        `RESUMO:\n` +
        `- Contas processadas: ${resumo.totalizadores.contas}\n` +
        `- Duração: ${resumo.duracao}\n\n` +
        `Verificar: ${SpreadsheetApp.getActiveSpreadsheet().getUrl()}`;
    }
    
    try {
      MailApp.sendEmail({
        to: CONFIG_EMAIL.admin,
        subject: assunto,
        body: corpo
      });
      
      this.registrar('INFO', '', '', 'Relatório enviado por e-mail', { para: CONFIG_EMAIL.admin });
    } catch (erro) {
      this.registrar('ERROR', '', '', 'Erro ao enviar e-mail', { erro: erro.toString() });
    }
  },
  
  /**
   * Enviar e-mail de nova autorização
   */
  enviarEmailNovaAutorizacao: function(nomeEmpresa, nomeConta, shopId) {
    if (!CONFIG_EMAIL.enviarRelatorioAutomatico) return;
    
    const corpo = `NOVA CONTA AUTORIZADA\n\n` +
      `Empresa:  ${nomeEmpresa}\n` +
      `Conta:    ${nomeConta}\n` +
      `Shop ID:  ${shopId}\n` +
      `Data:     ${new Date().toLocaleString('pt-BR')}\n\n` +
      `Status: Pronta para sincronizar\n\n` +
      `A primeira sincronização automática ocorrerá hoje às 02:00.`;
    
    try {
      MailApp.sendEmail({
        to: CONFIG_EMAIL.admin,
        subject: 'Nova conta TikTok Shop autorizada',
        body: corpo
      });
    } catch (erro) {
      this.registrar('ERROR', '', '', 
        'Falha ao enviar e-mail de autorização', 
        { erro: erro.toString() });
    }
  }
};