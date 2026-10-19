# Interface

Não há interface gráfica nem web: critérios visuais de tela (layout, contraste, componentes) não se
aplicam. A interface é a conversa do bot no Telegram e a saída do CLI no terminal.

## Bot

- Tom: português do Brasil, frases curtas, como uma pessoa falaria. Todos os textos ficam no topo do
  `bot.py` (`INICIO`, `ERRO`, `OPCOES`…); mude lá, não espalhe strings pelo código.
- Sempre dizer o que acontece em seguida ("em 25 segundos eu começo sozinho", "tem 2 PDFs na frente").
- Erro para o usuário diz o que fazer ("manda como arquivo"), nunca mostra detalhe técnico ou exceção.
- Botões inline: `✅ Pronto, gerar PDF` / `✖️ Cancelar` na coleta; `📋 Copiar…` e `🖼️ Salvar…` depois do PDF.
- Mensagem do Telegram tem limite de 4.096 caracteres; o texto é cortado por questão inteira (`BLOCO = 3000`).
- Nome do arquivo entregue: `prova_AAAA-MM-DD_HHMM.pdf` / `.txt`.

## PDF entregue

- A4, uma folha por página, fundo branco uniforme, tons de cinza por padrão (`/cor` ou `--cor` para manter
  caneta colorida da correção).
- O texto do OCR fica invisível por cima da imagem: dá para buscar e copiar sem mudar a aparência.
