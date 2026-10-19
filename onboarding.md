# Preparar o ambiente

1. Python 3.10 ou mais novo (o Docker usa 3.12).
2. Tesseract com português: instruções por sistema no `LEIAME.md`. Confira com
   `tesseract --list-langs` (tem que aparecer `por`).
3. `pip install -r requirements-dev.txt` (bibliotecas do projeto + pytest e ruff).
4. `ruff check . && pytest -q`. Se aparecer `skipped` nos testes de foto real, falta o `por` do Tesseract.

## Rodando

- CLI: `python scanner.py tests/fixtures/prova_pagina.jpg -o /tmp/prova.pdf` (o terminal mostra a pista
  de ordem achada em cada foto).
- Bot local: crie um bot de teste no @BotFather (não use o token do bot de produção ao mesmo tempo que o
  Railway: duas cópias brigam pelas mensagens) e rode `TELEGRAM_BOT_TOKEN=... python bot.py`.
  `LOG_LEVEL=DEBUG` mostra mais detalhes.
- Docker, igual ao Railway: `docker build -t scanner . && docker run -e TELEGRAM_BOT_TOKEN=... scanner`.

## Diagnóstico rápido

| Sintoma | Onde olhar |
|---|---|
| Página fora de ordem | saída do CLI: `pista de ordem = …` de cada foto; regras em `chave_da_pagina` |
| "folha não detectada" | foto sem fundo visível em volta da folha; `achar_folha` |
| Texto ruim | foto escura/tremida; teste com `--dpi 300`; troque `por.traineddata` pelo *best* |
| Bot não responde | logs do Railway; outra cópia rodando com o mesmo token; `TELEGRAM_BOT_TOKEN` faltando |
