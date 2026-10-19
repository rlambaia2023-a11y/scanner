# Scanner para correção

Fotos de prova (celular) → folha recortada e endireitada → páginas na ordem certa → PDF compacto
com texto pesquisável (OCR em português) + `.txt`. Roda pela linha de comando (`scanner.py`) e como
bot do Telegram (`bot.py`, long polling, publicado no Railway).

## Onde está cada coisa

- O que o produto faz e para quem: `PRODUCT.md`
- Como o código se divide e por quê: `docs/architecture.md`
- Mensagens e botões do bot: `docs/design.md`
- Preparar a máquina: `docs/onboarding.md` (instalação do Tesseract no `LEIAME.md`)
- Checagens, testes e revisão de segurança: `docs/quality.md`
- Estado da configuração do toolkit e pendências: `docs/setup.md`

## Comandos

- Instalar: `pip install -r requirements-dev.txt` (+ Tesseract com `por`, ver `LEIAME.md`)
- Rodar o CLI: `python scanner.py pasta_das_fotos -o prova.pdf`
- Rodar o bot: `TELEGRAM_BOT_TOKEN=... python bot.py`
- Lint: `ruff check .`
- Testes: `pytest -q` (os de foto real são pulados se o Tesseract `por` não estiver instalado)
- Verificar tudo: `ruff check . && pytest -q`
- Build: `docker build -t scanner .` (é o que o Railway usa)
- Tipos e formatação automática: não adotados. Não rode `ruff format` no projeto todo.

## Combinados

- Leia o código e estes docs antes de mexer. Separe o que você viu do que está supondo.
- Mudança mínima que resolve. Sem dependência nova, serviço pago ou framework sem pedido.
- Só ferramentas gratuitas: OpenCV, Pillow, pypdf, Tesseract. Nada de OCR em nuvem.
- Mexeu em ordenação, recorte, limpeza ou OCR? Rode `pytest` com o Tesseract `por` instalado.
  A foto em `tests/fixtures/` é o teste de verdade; regra nova de ordem ganha teste em `tests/test_ordem.py`.
- Bug corrigido vem com teste que falha antes e passa depois.
- Não suba a qualidade do JPEG, o DPI ou a cor por padrão sem medir o tamanho do PDF (meta: ~250–300 KB por página).
- O token do bot nunca aparece em log, mensagem de erro, commit ou URL de exemplo.
- Publicar no Railway, mandar mensagem pelo bot ou mudar variáveis de produção pede autorização explícita.
- Mudou comportamento, comando ou variável de ambiente? Atualize o doc responsável no mesmo commit
  (README para o usuário do bot, LEIAME para o CLI).
- Trabalho que vai atravessar sessões: anote objetivo, estado verificado, pendências e próximo passo
  em `docs/handoff.md` e confira os arquivos reais antes de confiar nele. Apague quando terminar.
