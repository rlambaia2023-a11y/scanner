# Configuração do toolkit

Adoção do [Vibe Coding Toolkit](https://github.com/soumatheusgomes/vibe-coding-toolkit), prompt 12
("set up an existing project"), revisão **`790a895`**, feita em **19/10/2026** numa sessão do Claude
(nuvem, com acesso só de leitura ao GitHub). Entregue como patch para aplicar à mão.

## Antes e depois

| | Antes (`d77279d`) | Depois |
|---|---|---|
| Testes | nenhum | 27 (`pytest`), 7 com a foto real |
| Lint | nenhum | `ruff check .`, 0 violações |
| CI | nenhum | GitHub Actions: lint + testes com Tesseract `por` |
| Instruções para agentes | nenhuma | `AGENTS.md`, `CLAUDE.md` |
| Docs | README, LEIAME | + PRODUCT, docs/architecture, design, onboarding, quality, setup |
| Foto de teste: pista de ordem | `questão 5` (errado) | `questão 3` |
| Foto de teste: PDF | 288 KB, ~4 s | igual (nada mudou no tratamento da imagem) |
| Pasta temporária se o OCR falhar | ficava no disco | apagada |

## Mudanças no código

- `chave_da_pagina` aceita um número de questão faltando na sequência (o OCR perdeu o "4-" sublinhado
  da foto de teste e o 3 era descartado). O salto só vale encostado numa sequência real, para itens
  "1." e "3." dentro de um enunciado não virarem a primeira questão (achado da revisão independente). Teste de regressão em `tests/test_ordem.py` e `tests/test_foto_real.py`.
- `processar` agora apaga a pasta `scan_*` em `finally` (o trabalho foi para `_montar`).
- Lint: rename de variável `l` → `lote` no `bot.py`, lambda virou função, `raise ... from None` no HEIC,
  `noqa` justificado no EXIF. Sem mudança de comportamento.

## Matriz de cobertura do toolkit

Legenda: **feito** = aplicado e verificado aqui · **equivalente** = coberto por outra ferramenta ·
**n/a** = não se aplica (motivo) · **pendente** = depende de ação sua.

| Componente | Situação | Motivo / como verificar |
|---|---|---|
| AGENTS.md / CLAUDE.md | feito | curtos; `CLAUDE.md` importa o `AGENTS.md` |
| 9 docs do manifesto | feito | README e LEIAME continuam canônicos para o usuário; demais criados |
| Testes + regressão | feito | `pytest -q` → 27 passam; no código antigo, 2 falham pelo bug de ordem (o 3º só porque `_montar` não existia) |
| Quality gates (ESLint/Biome) | equivalente | projeto sem JS: `ruff` com E, F, W, I, B, BLE |
| Limite de 350 linhas | adiado | `bot.py` tem ~700; divisão fora do escopo escolhido (ver architecture.md) |
| CI | feito (não executado) | sintaxe do YAML validada; roda no primeiro push ao GitHub |
| Revisão de segurança (prompt 13) | feito | fonte e uso registrados em `docs/quality.md`; revisão manual do diff feita |
| differential-review | n/a | não instalado neste cliente; revisão manual |
| Superpowers | pendente | plugin não disponível nesta sessão; o brainstorming seguiu o protocolo à mão. Instale no seu Claude Code se quiser |
| Ponytail / Caveman | pendente | plugins do cliente; instale no seu Claude Code se quiser. Não afetam o projeto |
| RTK | pendente | proxy de comandos instalado na máquina; nada no repositório |
| Context7 | pendente | indisponível nesta sessão; nenhuma API de biblioteca mudou, então não fez falta |
| Graphify | n/a | 2 arquivos de código; um grafo não ajuda mais que ler os arquivos |
| Memória | feito | memória do Project "Sistema De Scanner Para Correção" no claude.ai + estes docs versionados. Nenhum vault externo |
| Obsidian | n/a | sem necessidade nem destino autorizado |
| Hooks | n/a | nenhum hook necessário; nada de Git hook |
| Subagentes | política | delegar só busca/leitura ou revisão independente; nesta adoção um revisor independente (somente leitura) revisou o diff: 1 achado médio corrigido, 4 baixos tratados |
| agent-browser / Chrome DevTools MCP | n/a | não há interface web |
| Vercel skills, Next.js, shadcn | n/a | não é projeto Next/React |
| PostgreSQL skills | n/a | sem banco de dados |
| gh-fix-ci | pendente | útil quando o CI rodar e falhar; exige `gh` autenticado |
| Sentry MCP | n/a | sem Sentry; logs do Railway bastam no tamanho atual |
| Anthropic skills (artefatos, criar skill) | n/a | nenhuma tarefa recorrente que justifique skill própria |
| Codex | n/a | cliente não usado |
| Harness2 / avaliação do harness (doc 07, prompt 14) | não executado | precisa de sessão limpa do seu cliente para medir; próximo passo sugerido |
| Handoff entre sessões | feito | regra no `AGENTS.md` (`docs/handoff.md` só quando houver trabalho aberto) |

## O que não foi validado aqui

- O CI em si (não houve push). O YAML foi checado e os mesmos comandos passaram localmente.
- `docker build` (sem Docker nesta sessão). O Dockerfile não mudou.
- O bot rodando contra o Telegram (sem token de teste; não mexi no fluxo do bot além do rename verificado pelo lint).
- Python 3.12 do Docker: os testes rodaram em 3.13 com Tesseract 5.3.4 e o modelo `por` *fast*.

## Riscos que ficam

- Os testes de foto real conferem texto exato do OCR: trocar o modelo `por` (fast → best) ou a versão
  do Tesseract pode exigir ajustar os trechos esperados.
- O teste de pasta temporária olha `scan_*` na pasta temporária do sistema; duas execuções de teste
  simultâneas na mesma máquina podem dar falso alarme.

## Como repetir ou manter

- Verificar: `ruff check . && pytest -q`.
- Atualizar dependências: `pip install -U -r requirements.txt`, rodar a verificação e medir o tamanho do PDF da foto de teste.
- Repetir esta adoção: rode o prompt 12 do toolkit de novo; ele deve atualizar esta página e a matriz sem
  duplicar arquivos. Revise quando: o bot ganhar interface web, banco de dados ou Sentry; o `bot.py`
  crescer mais; ou o toolkit lançar componente novo para Python.
