# Scanner para correção

Bot do Telegram que transforma fotos de prova em **PDF compacto e pesquisável**, com as páginas
**na ordem certa** e o **texto do OCR** num .txt. Também funciona pela linha de comando.

Só ferramentas gratuitas: Python, OpenCV, Pillow, pypdf e Tesseract (português).

## Como usar o bot

1. Mande as fotos das páginas, em qualquer ordem. Pode ser em álbum ou como arquivo (📎 › Arquivo, fica com mais qualidade).
2. Mande **pronto**, ou só espere: 25 segundos depois da última foto ele começa sozinho.
3. O bot responde com `prova_AAAA-MM-DD_HHMM.pdf` e `.txt`.
4. Logo abaixo vem o botão **📋 Copiar todo o texto** (e um por página). O texto chega no chat em bloco: um toque copia tudo. Se a prova for longa e não couber numa mensagem (limite de 4.096 caracteres do Telegram), o texto vem **separado por questão, em ordem pela numeração**, em partes numeradas (ex.: “Parte 2/4 · Questões 11 a 20”). Nenhuma questão é cortada entre duas partes, e questão que começa numa página e termina na outra vem inteira. O botão funciona por 24 h (variável `TEXTO_HORAS`) ou até o bot reiniciar.

| Comando | O que faz |
|---|---|
| `/start`, `/ajuda` | explica como usar |
| `pronto` ou `/pronto` | monta o PDF agora |
| `/cancelar` | descarta as fotos do lote atual |
| `/cor` / `/pb` | próximo PDF colorido / em tons de cinza (padrão, mais leve) |

## Publicar no Railway

1. Crie o bot no Telegram: fale com **@BotFather** → `/newbot` → copie o token.
2. No Railway: *New Service* → *GitHub Repo* → este repositório. O `railway.json` já manda usar o `Dockerfile`.
3. Em *Variables*, crie `TELEGRAM_BOT_TOKEN` com o token.
4. Pronto. Não precisa de domínio, banco de dados nem webhook (o bot usa *long polling*).
   Rode **uma cópia só** por token; duas ao mesmo tempo brigam pelas mensagens.

Variáveis opcionais:

| Variável | Padrão | Para quê |
|---|---|---|
| `ALLOWED_CHAT_IDS` | (vazio = todos) | IDs de chat autorizados, separados por vírgula |
| `JANELA_SEGUNDOS` | 25 | tempo sem foto nova para fechar o lote sozinho |
| `MAX_PAGINAS` | 40 | páginas por PDF |
| `DPI` | 200 | 150 = menor, 300 = mais nítido |
| `QUALIDADE` | 70 | qualidade do JPEG dentro do PDF (50–85) |
| `TEXTO_HORAS` | 24 | por quanto tempo o botão de copiar texto funciona |

## Rodar no computador

Veja o [LEIAME.md](LEIAME.md) para instalar o Tesseract. Depois:

```
pip install -r requirements.txt
python scanner.py pasta_das_fotos -o prova.pdf            # linha de comando
TELEGRAM_BOT_TOKEN=... python bot.py                        # bot
```

## Arquivos

- `scanner.py` — recorte da folha, correção de perspectiva, limpeza, ordem das páginas, PDF + OCR
- `bot.py` — bot do Telegram
- `Dockerfile`, `railway.json`, `requirements.txt` — deploy
- `exemplo_prova.pdf` / `.txt` — exemplo gerado a partir de uma foto real
