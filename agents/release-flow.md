# Fluxo De Release CFO Sync

Este fluxo descreve a rotina antes de entregar uma nova versao do CFO Sync para
os analistas de dados.

## Ordem Padrao

1. Turing implementa ajustes na branch de desenvolvimento.
2. Turing atualiza todos os pontos do codigo que declaram a versao da release.
3. Curie revisa seguranca antes de tag/release.
4. Huygens valida funcionalmente os cenarios impactados.
5. Planck valida impacto de build, Docker, instalador e deploy.
6. Felipe autoriza criacao da tag e release.
7. No servidor, e feito `git pull`.
8. No servidor, a build Docker do CFO Sync e gerada novamente.
9. Gauss gera relatorio do servidor pos-atualizacao.
10. Huygens/Planck conferem smoke test final com base no relatorio do Gauss.

## Pontos De Versao

Antes da tag, Turing deve procurar e atualizar todos os pontos onde a versao do
CFO Sync aparece, incluindo quando aplicavel:

- `pyproject.toml`
- `src/cfo_sync/version.py`
- `README.md`
- `CHANGELOG.md`
- `installer/CFO-Sync.iss`
- workflows/release notes
- qualquer tela, endpoint ou metadata que exponha a versao

## Gate De Seguranca

Curie deve revisar antes de tag/release:

- diff completo da release;
- arquivos novos;
- logs e exemplos;
- configs Docker/env;
- GitHub Actions;
- instalador;
- permissoes/RBAC;
- relatorios do Gauss quando usados como evidencia.

Se Curie marcar `bloqueado`, a tag/release nao deve ser criada ate Turing
corrigir ou Felipe aceitar formalmente o risco.

## Handoff De Release Esperado

```text
Release:
- versao:
- branch:
- commit:
- tag proposta:

Alterado:
- arquivos e resumo

Versao atualizada em:
- arquivos

Verificado por Turing:
- comandos/resultados

Seguranca Curie:
- status e achados

QA Huygens:
- status e cenarios

Deploy Planck:
- status e impacto

Servidor/Gauss:
- relatorio usado
- health/versao/commit pos-deploy

Riscos:
- pendencias conhecidas
```
