# Scanner para correção de provas

Pega as fotos das páginas (do celular mesmo), recorta a folha, endireita, limpa o fundo,
coloca as páginas na ordem certa e gera:

- **um PDF compacto e pesquisável** (dá para buscar e copiar o texto), em torno de 250–300 KB por página;
- **um .txt** com o texto de cada página separado, pronto para usar na correção.

Tudo com ferramentas gratuitas: Python, OpenCV, Pillow, pypdf e Tesseract.

## Instalação (uma vez só)

1. **Python 3.9 ou mais novo** — https://www.python.org/downloads/
2. **Tesseract com português**
   - Windows: instalador do UB Mannheim (https://github.com/UB-Mannheim/tesseract/wiki).
     Na instalação, marque *Portuguese* em "Additional language data" e deixe marcado "Add to PATH".
   - Mac: `brew install tesseract tesseract-lang`
   - Linux (Debian/Ubuntu): `sudo apt install tesseract-ocr tesseract-ocr-por`
   - Para OCR um pouco melhor, troque o `por.traineddata` pelo da versão *best*:
     https://github.com/tesseract-ocr/tessdata_best/blob/main/por.traineddata
3. **Bibliotecas Python**
   ```
   pip install -r requirements.txt
   ```

## Como usar

Jogue as fotos numa pasta e rode:

```
python scanner.py pasta_das_fotos -o prova_joao.pdf
```

Ou passe as fotos uma a uma:

```
python scanner.py IMG_0101.jpg IMG_0102.jpg IMG_0103.jpg -o prova_joao.pdf
```

Sai `prova_joao.pdf` e `prova_joao.txt`.

### Opções

| Opção | O que faz |
|---|---|
| `--dpi 150` | PDF menor (bom para mandar no WhatsApp/Telegram) |
| `--dpi 300` | mais nítido, arquivo maior |
| `--qualidade 60` | comprime mais o JPEG (padrão 70) |
| `--cor` | mantém as cores (útil se a correção for com caneta vermelha). Fica maior |
| `--sem-ordenar` | usa exatamente a ordem em que as fotos foram passadas |

## Como ele decide a ordem das páginas

Na ordem de prioridade:

1. **Número de página escrito** na folha ("Página 2", "2/4").
2. **Número da primeira questão** da página (3-, 4-, 5-...). Só conta número que abre linha
   e faz sequência, então "90º" ou "05/10/26" no meio do texto não confundem.
3. **Capa**: a folha com matrícula/aluno/assinatura vai antes das outras sem número.
4. Sem nenhuma pista, vale a **hora em que a foto foi tirada** (EXIF) e depois o nome do arquivo.
   Página sem pista fica grudada logo depois da que veio antes dela.

O terminal mostra a pista que encontrou em cada foto, então dá para conferir.

## Dicas para fotografar

- Folha inteira na foto, com um pouco de fundo aparecendo em volta. Fundo escuro ou colorido ajuda o recorte.
- Luz de frente, sem sombra do celular em cima da folha.
- Pode tirar torto ou de lado: ele endireita e gira sozinho.
- Fotos HEIC do iPhone funcionam com `pip install pillow-heif`
  (ou mude o iPhone para "Mais compatível" em Ajustes › Câmera › Formatos).

## O que ele faz em cada foto

1. Gira conforme o EXIF.
2. Acha a folha (região clara e sem cor; se não der, pelas bordas). Folha com canto dobrado
   ou cortada na borda da foto também funciona.
3. Corrige a perspectiva para o formato A4.
4. Apaga o que sobrou de mesa/cadeira nas bordas.
5. Uniformiza o fundo (tira sombra e amarelado) **sem binarizar**: traço fraco de lápis continua aparecendo.
6. Desvira a página se estiver de lado ou de cabeça para baixo.
7. OCR em português no modo de coluna única, que preserva os números das questões.
