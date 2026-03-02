/**
 * CFO Company - DataProcessor Otimizado
 * 
 * Processa e transforma dados do Meta Ads com classificação R/A inteligente
 * COMPATÍVEL com todos os scripts do projeto
 */

const DataProcessor = {
  
  // ====================================================================
  // TRANSFORMAÇÃO PRINCIPAL - OTIMIZADA
  // ====================================================================
  transformMetaData(metaData, accountConfig) {
  const startTime = new Date();
  
  // ✅ LOG ÚNICO - apenas início
  Logger.logInfo(`Transformando ${metaData.length} registros`, { 
    account: accountConfig.nome_empresa 
  });

  if (!metaData || metaData.length === 0) {
    return [];
  }

  const processedData = [];
  let errors = 0;

  // ❌ SEM LOGS NO LOOP
  for (let i = 0; i < metaData.length; i++) {
    try {
      const transformedRecord = this.transformSingleRecord(metaData[i], accountConfig, i);
      
      if (transformedRecord) {
        processedData.push(transformedRecord);
      }

    } catch (error) {
      errors++;
      // Log apenas se >10% de erros
      if (errors > metaData.length * 0.1) {
        Logger.logError(`Muitos erros na transformação: ${errors}`);
        break;
      }
    }
  }

  const duration = new Date() - startTime;
  
  // ✅ LOG ÚNICO - apenas fim
  Logger.logInfo(`Transformação concluída: ${processedData.length} registros em ${duration}ms`);
  
  return processedData;
},

  // ====================================================================
  // TRANSFORMAÇÃO DE REGISTRO INDIVIDUAL - ROBUSTA
  // ====================================================================
  transformSingleRecord(rawRecord, accountConfig, index = 0) {
  try {
    // Validação básica
    if (!rawRecord || typeof rawRecord !== 'object') {
      throw new Error('Registro inválido ou vazio');
    }

    // Extração de valores com fallbacks
    const accountName = this.extractValue(rawRecord, 'account_name') || accountConfig.nome_ca || 'N/A';
    const campaignName = this.extractValue(rawRecord, 'campaign_name') || 'N/A';
    const adsetName = this.extractValue(rawRecord, 'adset_name') || 'N/A';
    const adName = this.extractValue(rawRecord, 'ad_name') || 'N/A';

    // Parse de valores numéricos e data
    const spendValue = this.parseSpend(rawRecord.spend);
    const date = this.parseDate(rawRecord.date_start);
    
    if (!date) {
      throw new Error(`Data inválida: ${rawRecord.date_start}`);
    }

    // Geração de chave única
    const uniqueKey = this.generateUniqueKey({
      accountId: accountConfig.account_id,
      campaignName,
      adsetName,
      adName,
      date
    });

    // Classificação R/A (usar função original que funciona)
    const classificacao = this.classifyRetentionAcquisitionOptimized(
      accountConfig.nome_ca,
      adName,
      campaignName,
      accountConfig.nome_bm,
      index === 0
    );

    // Montagem do registro processado
    return {
      nome_empresa: accountConfig.nome_empresa || 'N/A',
      nome_bm: accountConfig.nome_bm || 'N/A', 
      nome_ca: accountConfig.nome_ca || 'N/A',
      nome_anuncio: adName,
      valor_gasto: spendValue,
      data: date,
      centro_custo: accountConfig.centro_custo || 'N/A',
      tipo_ra: classificacao,
      unique_key: uniqueKey,
      account_id: accountConfig.account_id,
      raw_campaign_name: campaignName,
      raw_adset_name: adsetName,
      raw_date_start: rawRecord.date_start
    };
    
  } catch (error) {
    Logger.logError('Erro ao transformar registro individual', error, {
      index: index,
      hasRecord: !!rawRecord
    });
    return null;
  }
},

  // ====================================================================
  // CLASSIFICAÇÃO R/A OTIMIZADA - CÓDIGOS DO CLIENTE
  // ====================================================================
  classifyRetentionAcquisitionOptimized(nomeCA, nomeAnuncio, nomeCampanha, nomeBM, shouldLog = false) {
  try {
    // Cache global estático
    if (!this._globalClassificationCache) {
      this._globalClassificationCache = new Map();
    }
    
    // Chave de cache simples
    const cacheKey = `${nomeAnuncio}_${nomeCampanha}`.substring(0, 80);
    
    if (this._globalClassificationCache.has(cacheKey)) {
      return this._globalClassificationCache.get(cacheKey);
    }
    
    const texto = `${nomeAnuncio} ${nomeCampanha}`.toUpperCase();
    
    let result;
    
    // Verificações ultra rápidas
    if (texto.includes('[R]')) {
      result = 'Retenção';
    } else if (texto.includes('[A]')) {
      result = 'Aquisição';
    } else if (/RMKT|RTG|RET|CART|VISIT/i.test(texto)) {
      result = 'Retenção';
    } else if (/CONV|ACQ|LEAD|PROSP/i.test(texto)) {
      result = 'Aquisição';
    } else {
      result = 'Não Classificado';
    }
    
    // Cache resultado
    this._globalClassificationCache.set(cacheKey, result);
    
    return result;
    
  } catch (error) {
    return 'Não Classificado';
  }
},
  
  // ====================================================================
  // HELPERS DE EXTRAÇÃO E PARSE - ROBUSTOS
  // ====================================================================
  extractValue(record, fieldName) {
    try {
      if (!record || typeof record !== 'object') return null;
      
      // Tentar acesso direto
      if (record[fieldName] !== undefined && record[fieldName] !== null) {
        const value = String(record[fieldName]).trim();
        return value === '' ? null : value;
      }
      
      // Tentar acesso via data (para estruturas aninhadas)
      if (record.data && record.data[fieldName] !== undefined && record.data[fieldName] !== null) {
        const value = String(record.data[fieldName]).trim();
        return value === '' ? null : value;
      }
      
      return null;
      
    } catch (error) {
      Logger.logError(`Erro ao extrair campo ${fieldName}`, error);
      return null;
    }
  },
  
  parseSpend(spendValue) {
    try {
      if (spendValue === null || spendValue === undefined || spendValue === '') {
        return 0;
      }

      // Limpar string de moeda e converter para número
      const cleanSpend = String(spendValue)
        .replace(/[R$\s]/g, '') // Remover R$, espaços
        .replace(/,/g, '.'); // Trocar vírgula por ponto
        
      const parsed = parseFloat(cleanSpend);
      
      if (isNaN(parsed)) {
        Logger.logWarn(`Valor de spend inválido: ${spendValue}`);
        return 0;
      }
      
      // Garantir que não seja negativo
      return Math.max(0, parsed);
      
    } catch (error) {
      Logger.logError('Erro ao converter spend', error, { spendValue });
      return 0;
    }
  },
  
  parseDate(dateValue) {
    try {
      if (!dateValue) return null;
      
      // Se já é uma data válida
      if (dateValue instanceof Date && !isNaN(dateValue.getTime())) {
        return dateValue;
      }
      
      // Parse de string no formato YYYY-MM-DD (padrão Meta API)
      if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(dateValue)) {
        const [year, month, day] = dateValue.split('-').map(Number);
        const date = new Date(year, month - 1, day); // month é 0-indexed
        
        if (!isNaN(date.getTime())) {
          return date;
        }
      }
      
      // Tentativa genérica de parse
      const date = new Date(dateValue);
      if (!isNaN(date.getTime())) {
        return date;
      }
      
      throw new Error(`Formato de data não reconhecido: ${dateValue}`);
      
    } catch (error) {
      Logger.logError('Erro ao converter data', error, { dateValue });
      return null;
    }
  },
  
  // ====================================================================
  // GERAÇÃO DE CHAVE ÚNICA - OTIMIZADA
  // ====================================================================
  generateUniqueKey({ accountId, campaignName, adsetName, adName, date }) {
    try {
      // Converter data para string consistente
      const dateStr = date instanceof Date ? 
        date.toISOString().split('T')[0] : // YYYY-MM-DD
        String(date).split('T')[0];
      
      // Limpar nomes para evitar caracteres especiais
      const cleanCampaign = this.sanitizeForKey(campaignName);
      const cleanAdset = this.sanitizeForKey(adsetName); 
      const cleanAd = this.sanitizeForKey(adName);
      
      // Montar chave única
      const components = [
        accountId,
        cleanCampaign,
        cleanAdset,
        cleanAd,
        dateStr
      ];
      
      const uniqueKey = components.join('_');
      
      // Garantir tamanho máximo (importante para performance do Sheets)
      if (uniqueKey.length > 255) {
        // Usar hash para chaves muito longas
        return `${accountId}_${dateStr}_${Utilities.computeDigest(
          Utilities.DigestAlgorithm.MD5, 
          uniqueKey
        ).slice(0, 16)}`;
      }
      
      return uniqueKey;
      
    } catch (error) {
      Logger.logError('Erro ao gerar chave única', error);
      // Fallback para chave simples
      return `${accountId}_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
    }
  },
  
  sanitizeForKey(text) {
    if (!text) return 'N_A';
    
    return String(text)
      .trim()
      .replace(/[^a-zA-Z0-9]/g, '_') // Substituir caracteres especiais por underscore
      .replace(/_+/g, '_') // Remover underscores duplicados
      .substring(0, 50); // Limitar tamanho
  },

  // ====================================================================
  // VALIDAÇÕES E ESTATÍSTICAS - ÚTEIS PARA DEBUG
  // ====================================================================
  validateProcessedData(processedData) {
    if (!Array.isArray(processedData)) {
      throw new Error('Dados processados devem ser um array');
    }

    const requiredFields = [
      'nome_empresa', 'nome_bm', 'nome_ca', 'nome_anuncio', 
      'valor_gasto', 'data', 'centro_custo', 'tipo_ra', 'unique_key'
    ];

    let validCount = 0;
    let invalidCount = 0;

    processedData.forEach((record, index) => {
      try {
        requiredFields.forEach(field => {
          if (record[field] === undefined || record[field] === null) {
            throw new Error(`Campo obrigatório ausente: ${field}`);
          }
        });
        
        if (!(record.data instanceof Date)) {
          throw new Error('Campo data deve ser do tipo Date');
        }
        
        if (typeof record.valor_gasto !== 'number' || record.valor_gasto < 0) {
          throw new Error('Campo valor_gasto deve ser número positivo');
        }
        
        validCount++;
        
      } catch (error) {
        invalidCount++;
        if (invalidCount <= 5) { // Log apenas os primeiros 5 erros
          Logger.logError(`Registro inválido no índice ${index}`, error);
        }
      }
    });

    Logger.logInfo(`Validação concluída: ${validCount} válidos, ${invalidCount} inválidos`);
    return { validCount, invalidCount, isValid: invalidCount === 0 };
  },

  getProcessingStats(processedData) {
    if (!Array.isArray(processedData) || processedData.length === 0) {
      return { totalRecords: 0 };
    }

    const stats = {
      totalRecords: processedData.length,
      totalSpend: 0,
      dateRange: { min: null, max: null },
      classifications: { 'Aquisição': 0, 'Retenção': 0, 'Não Classificado': 0, 'Erro Classificação': 0 },
      avgSpend: 0
    };

    processedData.forEach(record => {
      // Soma total de spend
      if (typeof record.valor_gasto === 'number') {
        stats.totalSpend += record.valor_gasto;
      }

      // Range de datas
      if (record.data instanceof Date) {
        if (!stats.dateRange.min || record.data < stats.dateRange.min) {
          stats.dateRange.min = record.data;
        }
        if (!stats.dateRange.max || record.data > stats.dateRange.max) {
          stats.dateRange.max = record.data;
        }
      }

      // Contagem de classificações
      const classification = record.tipo_ra || 'Não Classificado';
      if (stats.classifications.hasOwnProperty(classification)) {
        stats.classifications[classification]++;
      }
    });

    stats.avgSpend = stats.totalRecords > 0 ? stats.totalSpend / stats.totalRecords : 0;

    return stats;
  }
};

// ✅ CLASSIFICAÇÃO ULTRA OTIMIZADA
function classifyRetentionAcquisitionUltraFast(adName, campaignName) {
  // Cache estático para evitar recomputações
  if (!this._ultraCache) {
    this._ultraCache = new Map();
  }
  
  const key = (adName + campaignName).substring(0, 50);
  
  if (this._ultraCache.has(key)) {
    return this._ultraCache.get(key);
  }
  
  const text = (adName + ' ' + campaignName).toUpperCase();
  
  let result;
  
  // ✅ VERIFICAÇÕES MÍNIMAS E RÁPIDAS
  if (text.includes('[R]')) {
    result = 'Retenção';
  } else if (text.includes('[A]')) {
    result = 'Aquisição'; 
  } else if (/\b(RMK|RTG|RET|CART|VISIT)\b/.test(text)) {
    result = 'Retenção';
  } else if (/\b(CONV|ACQ|NEW|LEAD|PROSP)\b/.test(text)) {
    result = 'Aquisição';
  } else {
    result = 'Não Classificado';
  }
  
  // Cache resultado
  this._ultraCache.set(key, result);
  
  // Limpar cache se muito grande
  if (this._ultraCache.size > 500) {
    this._ultraCache.clear();
  }
  
  return result;
};