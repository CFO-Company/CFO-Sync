// ====================================================================
// 01_TIKTOK_API.GS - Cliente HTTP para API TikTok Shop
// ====================================================================

const TikTokAPI = {
  
  BASE_URL: 'https://open-api.tiktokglobalshop.com',
  APP_KEY: '6ibefgifhsi1f',
  APP_SECRET: 'c1fd000906a8cdbb4beee5f829333362e36b9275',
  RATE_LIMIT_DELAY: 100, // 100ms entre requests (10 req/s)
  MAX_TENTATIVAS: 3,
  
 /**
 * Trocar CODE por tokens OAuth
 */
trocarCodePorTokens: function(code) {
  const url = 'https://auth.tiktok-shops.com/api/v2/token/get';
  
  const params = {
    app_key: this.APP_KEY,
    app_secret: this.APP_SECRET,
    auth_code: code,
    grant_type: 'authorized_code'
  };
  
  const queryString = Object.keys(params)
    .map(key => `${key}=${encodeURIComponent(params[key])}`)
    .join('&');
  
  const options = {
    method: 'get',
    muteHttpExceptions: true
  };
  
  const urlCompleta = `${url}?${queryString}`;
  
  Logger.registrar('INFO', '', '', 'Trocando code por tokens', 
    { url: url, code: code.substring(0, 10) + '...' });
  
  const response = UrlFetchApp.fetch(urlCompleta, options);
  const statusCode = response.getResponseCode();
  const resultado = JSON.parse(response.getContentText());
  
  Logger.registrar('INFO', '', '', 'Resposta API token', 
    { statusCode: statusCode, code: resultado.code });
  
  if (statusCode !== 200 || resultado.code !== 0) {
    throw new Error(`Erro OAuth TikTok: ${resultado.message}`);
  }
  
  return {
    access_token: resultado.data.access_token,
    refresh_token: resultado.data.refresh_token,
    expires_in: resultado.data.access_token_expire_in,
    seller_id: resultado.data.seller_base_region,
    shop_id: resultado.data.open_id,
    expira_em: new Date().getTime() + (resultado.data.access_token_expire_in * 1000)
  };
},
  
/**
 * Renovar access token
 */
renovarToken: function(refreshToken) {
  const url = 'https://auth.tiktok-shops.com/api/v2/token/refresh';
  
  const params = {
    app_key: this.APP_KEY,
    app_secret: this.APP_SECRET,
    refresh_token: refreshToken,
    grant_type: 'refresh_token'
  };
  
  const queryString = Object.keys(params)
    .map(key => `${key}=${encodeURIComponent(params[key])}`)
    .join('&');
  
  const options = {
    method: 'get',
    muteHttpExceptions: true
  };
  
  const urlCompleta = `${url}?${queryString}`;
  
  const response = UrlFetchApp.fetch(urlCompleta, options);
  const resultado = JSON.parse(response.getContentText());
  
  if (resultado.code !== 0) {
    throw new Error(`Erro refresh token: ${resultado.message}`);
  }
  
  return {
    access_token: resultado.data.access_token,
    refresh_token: resultado.data.refresh_token,
    expires_in: resultado.data.access_token_expire_in,
    expira_em: new Date().getTime() + (resultado.data.access_token_expire_in * 1000)
  };
},
  
/**
 * Buscar orders por período
 */
buscarOrders: function(accessToken, shopId, dataInicio, dataFim, cursor = null) {
  const url = `${this.BASE_URL}/api/orders/search`;
  
  const timestamp = Math.floor(Date.now() / 1000);
  
  const params = {
    create_time_from: Math.floor(new Date(dataInicio).getTime() / 1000),
    create_time_to: Math.floor(new Date(dataFim).getTime() / 1000),
    page_size: 50,
    sort_type: 'CREATE_TIME',
    sort_order: 'DESC'
  };
  
  if (cursor) {
    params.cursor = cursor;
  }
  
  const body = JSON.stringify(params);
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-tts-access-token': accessToken
    },
    payload: body,
    muteHttpExceptions: true
  };
  
  return this.retryComBackoff(() => {
    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();
    const resultado = JSON.parse(response.getContentText());
    
    if (statusCode !== 200 || resultado.code !== 0) {
      throw new Error(`Erro Orders API (${statusCode}): ${resultado.message}`);
    }
    
    return {
      orders: resultado.data.orders || [],
      next_cursor: resultado.data.next_page_token || null,
      more: resultado.data.more || false,
      total: resultado.data.total || 0
    };
  });
},
  
/**
 * Buscar detalhes de order
 */
buscarOrderDetail: function(accessToken, shopId, orderIds) {
  const url = `${this.BASE_URL}/api/orders/detail/query`;
  
  // Aceita string ou array
  const idsArray = Array.isArray(orderIds) ? orderIds : [orderIds];
  
  const body = JSON.stringify({
    order_id_list: idsArray
  });
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-tts-access-token': accessToken
    },
    payload: body,
    muteHttpExceptions: true
  };
  
  return this.retryComBackoff(() => {
    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();
    const resultado = JSON.parse(response.getContentText());
    
    if (statusCode !== 200 || resultado.code !== 0) {
      throw new Error(`Erro Order Detail (${statusCode}): ${resultado.message}`);
    }
    
    return resultado.data.order_list || [];
  });
},
  
/**
 * Buscar statements financeiros
 */
buscarFinanceStatements: function(accessToken, shopId, dataInicio, dataFim) {
  const url = `${this.BASE_URL}/api/finance/statements`;
  
  const body = JSON.stringify({
    start_time: Math.floor(new Date(dataInicio).getTime() / 1000),
    end_time: Math.floor(new Date(dataFim).getTime() / 1000)
  });
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-tts-access-token': accessToken
    },
    payload: body,
    muteHttpExceptions: true
  };
  
  return this.retryComBackoff(() => {
    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();
    const resultado = JSON.parse(response.getContentText());
    
    if (statusCode !== 200 || resultado.code !== 0) {
      throw new Error(`Erro Finance Statements (${statusCode}): ${resultado.message}`);
    }
    
    return resultado.data || [];
  });
},
  
/**
 * Buscar transações financeiras
 */
buscarFinanceTransactions: function(accessToken, shopId, dataInicio, dataFim, cursor = null) {
  const url = `${this.BASE_URL}/api/finance/transactions`;
  
  const params = {
    start_time: Math.floor(new Date(dataInicio).getTime() / 1000),
    end_time: Math.floor(new Date(dataFim).getTime() / 1000),
    page_size: 100
  };
  
  if (cursor) {
    params.page_token = cursor;
  }
  
  const body = JSON.stringify(params);
  
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'x-tts-access-token': accessToken
    },
    payload: body,
    muteHttpExceptions: true
  };
  
  return this.retryComBackoff(() => {
    const response = UrlFetchApp.fetch(url, options);
    const statusCode = response.getResponseCode();
    const resultado = JSON.parse(response.getContentText());
    
    if (statusCode !== 200 || resultado.code !== 0) {
      throw new Error(`Erro Finance Transactions (${statusCode}): ${resultado.message}`);
    }
    
    return {
      transactions: resultado.data.transactions || [],
      next_cursor: resultado.data.next_page_token || null,
      more: resultado.data.more || false
    };
  });
},
   
  /**
   * Retry com backoff exponencial
   */
  retryComBackoff: function(funcao) {
    for (let tentativa = 0; tentativa < this.MAX_TENTATIVAS; tentativa++) {
      try {
        const resultado = funcao();
        Utilities.sleep(this.RATE_LIMIT_DELAY);
        return resultado;
      } catch (erro) {
        if (tentativa === this.MAX_TENTATIVAS - 1) {
          throw erro;
        }
        Utilities.sleep(Math.pow(2, tentativa) * 1000);
      }
    }
  },
  
};