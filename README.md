# CFO Sync (Estrutura Inicial)

Base estrutural em Python para um app local usado por analistas.

## Objetivo

- UI unica para operacao diaria.
- Cada plataforma em arquivos separados para evitar conflitos.
- Banco local SQLite no computador do analista.
- Exportacao para Google Sheets por botao.
- Crescimento por configuracao: novos clientes/plataformas entram via arquivo versionado.

## Estrutura

- `launcher_desktop.py`: app desktop (Tkinter) principal.
- `src/cfo_sync/core`: configuracao, pipeline, banco local, exportacao.
- `src/cfo_sync/platforms`: conectores separados por plataforma.
- `secrets/app_config.json`: clientes, recursos e mapeamentos de campos.
- `secrets/`: credenciais locais (API keys e Google).
- `data/`: banco local SQLite.

## Como rodar

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set PYTHONPATH=src
python launcher_desktop.py
```

## Abrir com 2 cliques (Windows)

1. Dê duplo clique em `Abrir_CFO_Sync.bat`.
2. O script prepara o ambiente automaticamente e abre o app desktop.
3. No app, use os botões de `Coletar`, `Exportar` ou `Executar completo`.

## Como atualizar para os analistas (rapido)

1. Voce gera uma nova versao do projeto com `secrets/app_config.json` atualizado.
2. Analista substitui a pasta antiga pela nova.
3. Analista mantem a pasta `secrets/` local dele com credenciais.
4. Analista abre o app e ja enxerga novos clientes/plataformas da configuracao.

## Uso no app

1. Em `Plataforma`, selecione diretamente:
`Yampi Financeiro`, `Yampi Estoque`, `Mercado Livre`, `TikTok ADS`, `Meta ADS`.
2. Em `Cliente`, selecione o cliente.
3. Em `Filial / Alias`, selecione uma opcao especifica ou `Todas`.
4. Defina o periodo e execute.

## Google Sheets (service account)

1. Colocar o JSON da conta de servico em `secrets/google_service_account.json`.
2. Compartilhar a planilha com o e-mail da conta de servico como Editor.
3. Configurar `spreadsheet_id` e `client_tabs` com `gid` em `secrets/app_config.json`.
4. Regra do projeto: toda identificacao de aba e feita por `gid` (sheetId). `tab_name` e opcional e apenas informativo.

## Yampi (credenciais por empresa/alias)

1. Colocar as credenciais em `secrets/yampi_credentials.json`.
2. Configurar no `secrets/app_config.json`:
`"yampi": { "credentials_file": "yampi_credentials.json" }`.
3. O conector Yampi usa o nome do cliente selecionado para buscar os aliases da empresa.
4. Yampi Financeiro esta funcional:
busca pedidos por periodo na API, deduplica por ID e agrega por mes.
5. Campos de saida do financeiro:
`Data`, `Nome Empresa`, `Alias`, `Vendas de Produto`, `Descontos concedidos`, `Juros de Venda`.
6. Valores sao enviados como numero (sem `R$`), a formatacao fica na planilha.

## Meta Ads (credenciais compartilhadas + contas)

1. Colocar as credenciais em `secrets/meta_ads_credentials.json`.
2. Configurar no `secrets/app_config.json`:
`"meta_ads": { "credentials_file": "meta_ads_credentials.json" }`.
3. O arquivo guarda:
access token/app id/app secret compartilhados e lista de contas por empresa.

## Como adicionar cliente novo

Editar `secrets/app_config.json` e/ou credenciais:

- Adicionar nome do cliente em `platforms[].clients`.
- Se necessario, ajustar `resources[].field_map`.
- Para `Yampi`, adicionar empresa/aliases em `secrets/yampi_credentials.json`.
- Para `Meta Ads`, adicionar empresa/contas em `secrets/meta_ads_credentials.json`.

## Como adicionar plataforma nova

1. Criar pasta em `src/cfo_sync/platforms/nova_plataforma`.
2. Criar `connector.py` da nova plataforma.
3. Registrar no arquivo `src/cfo_sync/platforms/registry.py`.
4. Adicionar bloco da plataforma no `secrets/app_config.json`.

## Observacao importante

O exportador de Google Sheets ja escreve via API oficial. O Yampi Financeiro ja esta com coleta funcional; as demais plataformas ainda estao com conectores de exemplo.
