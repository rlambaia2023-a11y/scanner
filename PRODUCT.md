# Produto

## Para quem e para quê

Para quem corrige provas impressas e recebe as páginas como foto de celular. A pessoa manda as fotos
em qualquer ordem e recebe um PDF só, leve, com as páginas na ordem da prova e o texto pesquisável,
mais o texto lido (OCR) para usar na correção.

## O que já funciona

- Recorte da folha na foto (fundo colorido ou escuro, canto dobrado, folha cortada na borda), correção
  de perspectiva para A4 e limpeza de sombra e amarelado sem apagar traço fraco de lápis.
- Página fotografada de lado ou de cabeça para baixo é desvirada (OSD do Tesseract).
- Ordem das páginas, nesta prioridade: número de página escrito → primeira questão da página
  (tolera um número que o OCR perdeu) → folha de capa (matrícula/aluno/assinatura) → hora da foto (CLI)
  ou ordem de envio (bot).
- PDF com o JPEG embutido e o texto invisível por cima; ~250–300 KB por página a 200 dpi.
- `.txt` separado por página, com limpeza da sujeira de borda pela confiança do OCR.
- Bot do Telegram: lotes de até 40 fotos, botão "Pronto", fechamento automático após 25 s,
  copiar texto por questão, devolver as páginas tratadas como fotos, modo colorido.
- CLI: `python scanner.py fotos/ -o prova.pdf` com `--dpi`, `--qualidade`, `--cor`, `--sem-ordenar`.

## Limites conhecidos

- Questão cujo número o OCR não leu e que é a única da página: a página fica sem pista e gruda na anterior.
- Os botões do bot guardam texto e imagens em memória/disco temporário: somem após 24 h ou num reinício.
- Uma cópia do bot por token (long polling). Sem banco de dados.
- Sem `ALLOWED_CHAT_IDS`, qualquer pessoa que achar o bot pode usá-lo.

## Fora do escopo

Correção automática das respostas, OCR de letra cursiva, serviços pagos ou OCR em nuvem.
