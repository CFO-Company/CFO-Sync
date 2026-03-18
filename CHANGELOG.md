## [1.0.7] - 18-03-2026

### Added
- Runners Python dedicados para automação no servidor em `scripts/task_scheduler`:
  `omie_2025_ano_completo.py`, `omie_2026_ano_atual.py`, `yampi_mes_atual_3_anteriores.py`,
  `mercado_livre_mes_atual_3_anteriores.py` e `meta_ads_dia_atual_e_anterior.py`.
- Novo cliente `Mariana Amaral` no Meta Ads com credenciais e mapeamento de aba/GID para exportação.

### Changed
- Fluxo de automação orientado para execução por scripts Python por plataforma (Task Scheduler), com logs centralizados em `logs/automation`.
- Mercado Livre: ajuste de mapeamento de colunas para alinhar nomenclaturas da planilha (`Vendas de Produto`, `Descontos Concedidos`).

### Fixed
- Exportação para Google Sheets com resolução de colunas mais robusta (normalização de cabeçalhos) para evitar criação de colunas duplicadas por variações de nome.
- Períodos dinâmicos de coleta alinhados por plataforma:
  - Omie 2025 ano completo;
  - Omie 2026 de `01/01/2026` até a data atual;
  - Yampi e Mercado Livre mês atual + 3 anteriores;
  - Meta Ads dia atual e dia anterior.

## [1.0.6] - 18-03-2026

### Added
- 

### Changed
- Workflow de release simplificado para publicar release diretamente pela tag, sem etapa de build de artefatos.

### Fixed
- Publicação de release desbloqueada após falhas recorrentes no job de build Windows.

## [1.0.5] - 18-03-2026

### Added
- 

### Changed
- Workflow de release ajustado com tentativas de retry no build Windows para reduzir falhas transitórias de ambiente/rede.
- Build da release no GitHub Actions alinhado para Python `3.14`.

### Fixed
- Continuidade da publicação automática de release após falha no run da tag `v1.0.4`.

## [1.0.4] - 18-03-2026

### Added
- 

### Changed
- Pipeline de release no GitHub ajustado para build e publicação apenas de pacote Windows.
- Documentação de build/release atualizada para fluxo Windows-only.

### Fixed
- Falha da release automática em tags novas causada por etapa de build macOS não utilizada.

## [1.0.3] - 18-03-2026

### Added
- Scripts dedicados por plataforma em `scripts/task_scheduler` para execução via Task Scheduler (Omie ano atual/anterior, Yampi, Mercado Livre, Meta Ads e Google Ads).
- Fluxos agregadores para agendas de execução 3x ao dia e 1x ao dia.

### Changed
- Cadastro de plataformas separado para `OMIE 2025` e `OMIE 2026`, mantendo a mesma lógica de coleta/exportação e alterando apenas os destinos de planilha.
- Ajustes de layout no calendário e nos campos de período para melhorar alinhamento e aproveitamento de espaço na tela de Pedidos.

### Fixed
- Padronização do carregamento de credenciais/segredos no formato JSON conforme o padrão do projeto.
- Inclusão de logs operacionais para automação (execução, erros, itens não encontrados e tempo).

## [1.0.2] - 12-03-2026

### Added
- 

### Changed
- Exportacao para Google Sheets passou a substituir os meses selecionados no periodo: remove primeiro os registros existentes desses meses e depois reinsere os dados novos.

### Fixed
- Regra de comparacao para substituicao mensal padronizada por `mes + ano`, cobrindo selecao de um ou varios meses no app sem manter residuos de periodos anteriores.

## [1.0.1] - 10-03-2026

### Added
- 

### Changed
- Meta Ads: recurso `contas` passou a usar coleta via API de insights no lugar do stub local.
- Meta Ads: mapeamento de colunas alinhado para exportar Nome Empresa, Nome BM, Nome CA, Nome Anúncio, Valor Gasto, Data, Centro Custo e Tipo R/A.
- Launcher Desktop: calendário de período (data inicial/final no mesmo seletor) recebeu melhorias de usabilidade com atalhos rápidos, navegação aprimorada e seleção mais fluida de intervalo.

### Fixed
- Exportação para Sheets agora resolve nomes de cliente com variações de acentuação/codificação (ex.: `Jur?dico` vs `Jurídico`).

## [1.0.0] - 10-03-2026

### Added
- 

### Changed
- 

### Fixed
- 
