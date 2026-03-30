## [1.0.18] - 30-03-2026

### Added
- Novo remapeamento de cliente no scheduler da Omie 2026 para executar `Umbrella` no lugar de `Attracione`, com deduplicação de processamento.

### Changed
- Ajuste de resolução de conta corrente na Omie para priorizar o endpoint `geral/contacorrente` com `ListarContasCorrentes`.

### Fixed
- Correção na leitura de lançamentos de conta corrente para aceitar variações de payload (`ListarLancCC`, `listaLancamentos`, `lancamentos`) sem zerar exportações.
- Fallback de `nCodCC` para evitar campo vazio quando a descrição da conta não estiver disponível.

## [1.0.17] - 20-03-2026

### Added
- Integração de coleta do Google Ads com credenciais, conector, API e insights para exportação no pipeline.
- Script dedicado de automação para execução diária de Google Ads (`scripts/task_scheduler/google_ads_dia_atual_e_anterior.py`).

### Changed
- Exportação para Google Sheets ajustada para suportar o novo fluxo de dados do Google Ads.
- README atualizado com orientações de uso do módulo Google Ads.

### Fixed
- 

## [1.0.16] - 19-03-2026

### Added
- Montagem dinâmica de argumentos do PyInstaller no script de build para incluir `--add-data` apenas quando `templates/` e `sounds/` existirem no checkout.

### Changed
- Build Windows no CI passou a depender de uma única lógica no `tools/build_windows_package.ps1`, com fallback robusto para ambientes sem diretórios opcionais.

### Fixed
- Falha do workflow de release por ausência da pasta `templates` no GitHub Actions (`Unable to find ...\\templates`).

## [1.0.15] - 19-03-2026

### Added
- Fallback de build Windows para gerar `CFO-Sync-Setup.exe` único (`PyInstaller --onefile`) quando o Inno Setup não estiver disponível.

### Changed
- Pipeline de release passou a publicar apenas o asset `CFO-Sync-Setup.exe`.
- Etapa de build da release no GitHub Actions foi centralizada no script `tools/build_windows_package.ps1`.

### Fixed
- Removida a publicação de executável solto que causava erro de runtime por dependências ausentes (`python311.dll`/`_internal`).
- Fluxo de atualização do app no Windows ajustado para abrir corretamente tanto instalador real quanto `.exe` único.

## [1.0.14] - 18-03-2026

### Added
- Extração da versão da tag no workflow de release adaptada para PowerShell (`GITHUB_REF_NAME`) em runners Windows.

### Changed
- Etapa `Build Release Notes From CHANGELOG` padronizada para shell PowerShell no pipeline de release.

### Fixed
- Falha no `changelog_extract.py` por versão vazia (uso de sintaxe bash `${GITHUB_REF_NAME#v}` em runner Windows).

## [1.0.13] - 18-03-2026

### Added
- Criação automática dos diretórios `templates`/`templates/secrets` e `sounds` no CI quando ausentes.

### Changed
- Build do PyInstaller no workflow passou a montar os argumentos de `--add-data` dinamicamente conforme existência dos diretórios.

### Fixed
- Erro de build no GitHub Actions por ausência de `templates` no checkout da tag (`Unable to find ...\\templates`).

## [1.0.12] - 18-03-2026

### Added
- Build do executável Windows executado diretamente no workflow (`python -m PyInstaller`) com comandos explícitos.

### Changed
- Pipeline de release deixou de depender da execução do script `tools/build_windows_package.ps1` no GitHub Actions.

### Fixed
- Falha recorrente na etapa de build em CI por execução indireta via script PowerShell.

## [1.0.11] - 18-03-2026

### Added
- Release passa a anexar sempre o executável Windows `CFO-Sync.exe`.
- Asset `CFO-Sync-Setup.exe` gerado automaticamente a partir do executável para manter compatibilidade de atualização.

### Changed
- Workflow de release simplificado para build Windows sem dependência do Inno Setup no runner.

### Fixed
- Falhas repetidas na etapa de geração de instalador que impediam publicar o `.exe` na release.

## [1.0.10] - 18-03-2026

### Added
- Chamada explícita do `ISCC.exe` no workflow de release para gerar `CFO-Sync-Setup.exe` com versão da tag.

### Changed
- Build Windows da release foi separado em duas etapas:
  1. `PyInstaller` (`-SkipInstaller`)
  2. Inno Setup via `ISCC.exe` detectado no runner.

### Fixed
- Falhas intermitentes na geração do instalador por detecção indireta do Inno Setup no script de build.

## [1.0.9] - 18-03-2026

### Added
- Validação explícita do `ISCC.exe` no pipeline de release para garantir geração do instalador Windows.

### Changed
- Workflow de release ajustado para Python `3.11` no runner Windows, aumentando compatibilidade de build.

### Fixed
- Falha da `v1.0.8` na etapa de build do executável/instalador corrigida com detecção robusta do Inno Setup no runner.

## [1.0.8] - 18-03-2026

### Added
- Assets Windows anexados automaticamente na release: `CFO-Sync-Setup.exe` e `CFO-Sync.exe`.

### Changed
- Pipeline de release migrado para `windows-latest` com build real do executável via PyInstaller.
- Build da release passa a instalar Inno Setup no runner para gerar o instalador oficial do Windows.

### Fixed
- Release sem `.exe` corrigida: tags novas agora publicam a release com executável e instalador.

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
