# Arquitetura

Dois arquivos Python e nenhum serviço externo além da API do Telegram.

```
fotos ──► scanner.processar() ──► por foto: abrir (EXIF) → achar_folha → endireitar → apagar_fundo
                                            → limpar → corrigir_rotacao → JPEG
                                            → tesseract (pdf + tsv) → texto_limpo → chave_da_pagina
                              ──► ordenar() ──► pypdf junta os PDFs de página ──► prova.pdf + prova.txt
```

## scanner.py

- **Entrada**: `listar_imagens`, `abrir_imagem` (gira pelo EXIF, lê a data da foto, HEIC via `pillow-heif`).
- **Recorte**: `achar_folha` procura o papel como região clara e pouco saturada; se falhar, usa bordas
  (Canny). `melhor_quadrilatero` escolhe, entre vários candidatos, o que mais coincide com o papel.
- **Limpeza**: `apagar_fundo` branqueia restos de mesa nas bordas; `limpar` divide pelo fundo estimado
  (tira sombra) e estica o contraste. Não binariza, para preservar lápis fraco.
- **OCR**: uma chamada do Tesseract por página gera o PDF da página (JPEG sem recompressão + texto
  invisível) e o TSV. `--psm 4` porque o modo padrão costuma descartar o número da questão.
- **Ordem**: `chave_da_pagina` devolve `("pagina", n)`, `("questao", n)`, `("capa", 0)` ou `None`;
  `ordenar` aplica por cima da ordem base (EXIF + nome natural, ou só o nome).
- **Temporários**: `processar` cria a pasta `scan_*` e `_montar` faz o trabalho; a pasta é apagada em
  `finally`, mesmo quando o OCR falha.

## bot.py

- `Telegram`: cliente mínimo com `requests` (retry com backoff, respeita `retry_after`). O token fica
  só na URL base; erros de rede são logados sem a URL.
- `Bot`: uma thread lê updates (long polling), outra fecha lotes por tempo (`vigiar_janelas`), outra
  processa a fila (`trabalhar`) uma prova por vez. Estado só em memória (`lotes`, `textos`), protegido
  por `trava`.
- Texto para copiar: `separar_questoes` corta por questão (só aceita número que segue o anterior),
  `agrupar_questoes`/`dividir` montam mensagens abaixo do limite do Telegram.
- Imagens tratadas para a galeria ficam em `$TMP/scanner_cache/<id>` com limite de quantidade e prazo.

## Decisões

- **Tesseract local e gratuito** em vez de OCR em nuvem: custo zero, sem mandar prova de aluno para fora.
- **JPEG em tons de cinza a 200 dpi, qualidade 70**: equilíbrio entre nitidez para corrigir e ~250–300 KB/página.
- **Long polling, sem banco**: deploy simples no Railway; a contrapartida é perder os botões num reinício.
- **Python 3.12 no Docker**. O projeto exige 3.10+ (`pyproject.toml`) porque o `bot.py` usa `int | None`
  em dataclass. O `scanner.py` sozinho ainda roda em 3.9, como diz o LEIAME.
- `bot.py` tem ~700 linhas, acima da referência de 350 do toolkit. Divisão adiada de propósito
  (decisão de 19/10/2026); se for feita, separar `telegram.py`, `texto.py` (corte por questão) e `bot.py`.
