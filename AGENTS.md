# CFO Sync - Instrucoes Para Agentes

Este arquivo define como agentes Codex devem trabalhar neste repositorio.
O projeto e um aplicativo Python desktop/servidor para orquestrar coleta de APIs,
exportacao para Google Sheets, cadastro remoto de clientes e deploy Windows/Docker.

## Contexto Do Projeto

- Linguagem principal: Python 3.11+.
- App desktop: `launcher_desktop.py` e `src/cfo_sync/ui/`.
- Core de negocio: `src/cfo_sync/core/`.
- Servidor HTTP: `src/cfo_sync/server/`.
- Conectores de plataformas: `src/cfo_sync/platforms/`.
- Scripts agendados: `scripts/task_scheduler/`.
- Deploy/infra: `settings/`, `installer/`, `tools/`, `.github/`.
- Configuracoes e credenciais reais ficam fora do controle do agente ou em `secrets/`.

## Regras Globais

1. Leia o contexto relevante antes de editar.
2. Nao reverta mudancas locais que voce nao fez.
3. Evite mexer em `secrets/` e arquivos `.env` reais.
4. Nao exponha tokens, chaves, credenciais ou dados sensiveis em respostas, logs ou commits.
5. Preserve o estilo atual do projeto: Python simples, stdlib quando possivel, comentarios curtos.
6. Use `rg`/`rg --files` para procurar arquivos e texto.
7. Antes de alterar arquivos compartilhados, coordene com os outros agentes.
8. Ao finalizar, informe arquivos alterados, comandos executados e riscos pendentes.

## Arquivos Compartilhados De Alto Risco

Combine antes de alterar:

- `launcher_desktop.py`
- `pyproject.toml`
- `requirements.txt`
- `README.md`
- `CHANGELOG.md`
- `settings/docker-compose.server.yml`
- `settings/docker/server.Dockerfile`
- `settings/setup_docker_server.ps1`
- `tools/build_windows_package.ps1`
- `installer/CFO-Sync.iss`
- qualquer arquivo dentro de `secrets/`
- qualquer arquivo de configuracao real em `settings/`

## Comandos Uteis

Executar app desktop:

```powershell
$env:PYTHONPATH = "src"; python -m cfo_sync.main
```

Executar servidor local:

```powershell
$env:PYTHONPATH = "src"; python -m cfo_sync.server.main --host 127.0.0.1 --port 8088
```

Health check local:

```powershell
irm http://127.0.0.1:8088/v1/health
```

Build Windows:

```powershell
.\tools\build_windows_package.ps1
```

Build/deploy Docker local:

```powershell
.\settings\setup_docker_server.ps1 -HostRoot "C:\srv" -Port 8088 -Workers 2
```

## Protocolo Entre Agentes

Use mensagens curtas e objetivas neste formato:

```text
[DEV -> QA]
Mudanca: ...
Arquivos principais: ...
Como testar: ...
Riscos: ...
```

```text
[QA -> DEV]
Bug: ...
Severidade: baixa|media|alta|critica
Passos para reproduzir: ...
Esperado: ...
Obtido: ...
Evidencia: ...
```

```text
[DEPLOY -> DEV/QA]
Ambiente: local|staging|producao
Build/deploy: ok|falhou
Comandos: ...
Logs relevantes: ...
Pendencias: ...
```

## Divisao Recomendada

- Dev/arquiteto: implementacao, arquitetura, refactors pequenos e correcao de bugs.
- QA/tester: reproducao de bugs, testes manuais, revisao de diffs e cobertura.
- Implantacao: build, empacotamento, Docker, servidor, tunnel, variaveis e validacao pos-deploy.

Cada agente deve seguir tambem o arquivo especifico em `agents/`.
