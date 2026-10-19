# Qualidade

## Checagens

| O quê | Comando | Onde roda |
|---|---|---|
| Lint (pyflakes, pycodestyle, imports, bugbear, exceção engolida) | `ruff check .` | local e CI |
| Testes de regra (ordem, corte de texto do bot) | `pytest -q tests/test_ordem.py tests/test_texto_bot.py` | local e CI |
| Ponta a ponta com foto real | `pytest -q tests/test_foto_real.py` | local (com Tesseract `por`) e CI |
| Tudo | `ruff check . && pytest -q` | antes de cada commit |
| Imagem do deploy | `docker build -t scanner .` | local, quando mexer no Dockerfile |

O CI (`.github/workflows/verificar.yml`) instala o Tesseract com português e roda lint + testes em
todo push e PR. Ele não publica nada e não usa o token do bot.

## O que os testes garantem

- A foto real (`tests/fixtures/prova_pagina.jpg`) é recortada, fica com a pista `questão 3`,
  gera PDF abaixo de 400 KB, pesquisável, com o texto das questões 3, 5, 6 e 7.
- A mesma foto de cabeça para baixo ainda é lida.
- A pasta temporária `scan_*` some no sucesso e no erro.
- Regras de ordem: número de página, questão com um número faltando, número solto longe da
  sequência, capa, página sem pista, ordem natural dos nomes, EXIF.
- Bot: questão que atravessa página fica inteira, "1)" dentro de enunciado não vira questão, nenhuma
  mensagem passa do limite.

Ao corrigir bug de ordem ou OCR: primeiro um teste que falha com o texto/foto do problema, depois a correção.
Prova nova que deu problema vira fixture (só com permissão de quem fez a prova; tire nome e matrícula se der).

## Regras do lint

Adotado com zero violações; tudo como erro. Exceções pontuais só com `# noqa: REGRA - motivo`.
Hoje há quatro, todas `BLE001`: três no `bot.py` (um lote, uma foto ou um update com erro não pode
derrubar o bot; o erro é logado) e uma no `scanner.py` (EXIF corrompido; sem data a ordem usa o nome). Formatação automática (`ruff format`)
não foi adotada para não reescrever o projeto inteiro.

## Revisão de segurança

Para uma revisão de segurança (do repositório todo ou de um diff), use o bloco "Prompt" de
`docs/prompts/13-security-review.md` do Vibe Coding Toolkit
(https://github.com/soumatheusgomes/vibe-coding-toolkit, revisão `790a895` na adoção). Cole o bloco
no agente, na raiz deste projeto, e diga o intervalo de commits se for um diff. O relatório é privado,
somente leitura, sem corrigir nada automaticamente. Para atualizar, pegue o mesmo arquivo na `main`
do toolkit e registre a nova revisão aqui.

Pontos de atenção já conhecidos neste projeto:

- **Quem pode usar o bot**: sem `ALLOWED_CHAT_IDS`, qualquer um. Defina no Railway com os IDs de chat
  de quem corrige.
- **Token**: só em variável de ambiente; o cliente nunca loga a URL (que contém o token).
- **Arquivos recebidos**: até 20 MB (limite do Telegram); só entram fotos ou documentos com tipo de
  imagem. A extensão do arquivo não é confiável (desconhecida vira `.jpg`): quem decide é o Pillow, que
  recusa o que não for imagem e imagens absurdamente grandes ("bomba de descompressão").
- **Dados de aluno**: fotos e textos ficam só em pasta temporária e memória; somem em até 24 h ou no reinício.
