#!/usr/bin/env python3
"""
Scanner para correção de provas
--------------------------------
Fotos das páginas  ->  recorte + correção de perspectiva  ->  limpeza
->  ordenação automática  ->  PDF compacto pesquisável (OCR)  ->  texto (.txt)

Tudo gratuito: OpenCV, Pillow e Tesseract (idioma "por").

Uso:
    python scanner.py foto1.jpg foto2.jpg ... -o prova.pdf
    python scanner.py pasta_com_fotos/ -o prova.pdf
Opções úteis:
    --dpi 200          resolução das páginas (150 = menor, 300 = mais nítido)
    --qualidade 70     qualidade do JPEG dentro do PDF (50 a 85)
    --cor              mantém cor (padrão: tons de cinza, bem menor)
    --sem-ordenar      mantém a ordem em que as fotos foram passadas
"""
import argparse
import os

os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # Tesseract fica ~3x mais rápido assim
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageOps

EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp", ".heic"}
A4_RATIO = 297 / 210


# ---------------------------------------------------------------- entrada
def listar_imagens(entradas):
    arquivos = []
    for e in entradas:
        if os.path.isdir(e):
            for n in os.listdir(e):
                if os.path.splitext(n)[1].lower() in EXTS:
                    arquivos.append(os.path.join(e, n))
        elif os.path.splitext(e)[1].lower() in EXTS:
            arquivos.append(e)
    return arquivos


def abrir_imagem(caminho):
    """Abre a foto já girada conforme o EXIF e devolve (BGR, data_da_foto)."""
    if caminho.lower().endswith(".heic"):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise ErroScanner("Para fotos .heic do iPhone: pip install pillow-heif")
    img = Image.open(caminho)
    data = None
    try:
        exif = img.getexif()
        bruto = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        if bruto:
            data = datetime.strptime(str(bruto), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    img = ImageOps.exif_transpose(img).convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR), data


# ------------------------------------------------- recorte da folha na foto
def ordenar_cantos(p):
    p = p.reshape(4, 2).astype("float32")
    s, d = p.sum(1), np.diff(p, axis=1).ravel()
    return np.array([p[np.argmin(s)], p[np.argmin(d)],
                     p[np.argmax(s)], p[np.argmax(d)]], dtype="float32")


def achar_folha(bgr):
    """Procura o contorno de 4 lados da folha. Tenta duas estratégias:
    1) papel = região clara e pouco saturada (funciona bem em mesa/cadeira colorida)
    2) bordas (Canny) como reserva."""
    h, w = bgr.shape[:2]
    esc = 1000 / max(h, w)
    peq = cv2.resize(bgr, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
    area_min = 0.20 * peq.shape[0] * peq.shape[1]

    hsv = cv2.cvtColor(peq, cv2.COLOR_BGR2HSV)
    papel = cv2.inRange(hsv, (0, 0, 150), (180, 60, 255))
    papel = cv2.morphologyEx(papel, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    papel = cv2.morphologyEx(papel, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))

    cinza = cv2.GaussianBlur(cv2.cvtColor(peq, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    bordas = cv2.dilate(cv2.Canny(cinza, 50, 150), np.ones((5, 5), np.uint8))

    for mascara in (papel, bordas):
        conts, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(conts, key=cv2.contourArea, reverse=True)[:5]:
            if cv2.contourArea(c) < area_min:
                break
            hull = cv2.convexHull(c)
            return melhor_quadrilatero(hull, peq.shape[:2]) / esc
    return None


def melhor_quadrilatero(hull, forma):
    """Folha com canto dobrado ou cortada pela borda da foto não vira um
    quadrilátero perfeito. Gera vários candidatos e fica com o que mais
    coincide (IoU) com a área real do papel."""
    pts = hull.reshape(-1, 2).astype("float32")
    s, d = pts.sum(1), pts[:, 0] - pts[:, 1]
    candidatos = [np.array([pts[np.argmin(s)], pts[np.argmax(d)],
                            pts[np.argmax(s)], pts[np.argmin(d)]])]
    peri = cv2.arcLength(hull, True)
    for eps in (0.01, 0.02, 0.03, 0.05):
        ap = cv2.approxPolyDP(hull, eps * peri, True)
        if len(ap) == 4:
            candidatos.append(ap.reshape(4, 2))
    candidatos.append(cv2.boxPoints(cv2.minAreaRect(hull)))

    alvo = np.zeros(forma, np.uint8)
    cv2.fillConvexPoly(alvo, hull.astype(np.int32), 1)

    def iou(q):
        m = np.zeros(forma, np.uint8)
        cv2.fillConvexPoly(m, ordenar_cantos(q).astype(np.int32), 1)
        return (m & alvo).sum() / max((m | alvo).sum(), 1)

    return ordenar_cantos(max(candidatos, key=iou))


def endireitar(bgr, cantos, largura):
    altura = int(round(largura * A4_RATIO))
    destino = np.array([[0, 0], [largura - 1, 0], [largura - 1, altura - 1],
                        [0, altura - 1]], dtype="float32")
    m = cv2.getPerspectiveTransform(cantos, destino)
    return cv2.warpPerspective(bgr, m, (largura, altura),
                               flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


# ------------------------------------------------------------- limpeza
def apagar_fundo(bgr):
    """Depois de endireitar, o que sobrou de mesa/cadeira nas bordas vira branco."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    papel = cv2.inRange(hsv, (0, 0, 140), (180, 70, 255))
    papel = cv2.morphologyEx(papel, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    n, rot, stats, _ = cv2.connectedComponentsWithStats(papel)
    if n < 2:
        return bgr
    maior = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    conts, _ = cv2.findContours((rot == maior).astype(np.uint8), cv2.RETR_EXTERNAL,
                                cv2.CHAIN_APPROX_SIMPLE)
    mascara = np.zeros(papel.shape, np.uint8)
    cv2.drawContours(mascara, [max(conts, key=cv2.contourArea)], -1, 255, cv2.FILLED)
    if mascara.mean() < 255 * 0.6:   # algo deu errado: não mexe
        return bgr
    out = bgr.copy()
    out[mascara == 0] = 255
    # restos coloridos (celular, tecido) só numa faixa estreita da borda;
    # no miolo da folha a cor fica, porque pode ser caneta de correção
    h, w = papel.shape
    faixa = np.zeros_like(papel)
    b = int(0.04 * w)
    faixa[:, :b] = faixa[:, -b:] = faixa[:b, :] = faixa[-b:, :] = 1
    out[(faixa == 1) & (hsv[..., 1] > 80)] = 255
    return out


def limpar(bgr, cor=False):
    """Deixa o fundo branco e uniforme (tira sombra e amarelado), mas preserva
    traços fracos de lápis/caneta — importante para a correção."""
    def normalizar(canal):
        fundo = cv2.morphologyEx(canal, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
        fundo = cv2.medianBlur(fundo, 31)
        out = cv2.divide(canal, fundo, scale=255)
        # estica o contraste: quase-branco vira branco, preto fica preto
        lut = np.clip((np.arange(256) - 40) * 255.0 / (235 - 40), 0, 255).astype(np.uint8)
        return cv2.LUT(out, lut)

    if cor:
        return cv2.merge([normalizar(c) for c in cv2.split(bgr)])
    return normalizar(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))


def corrigir_rotacao(img, tmpdir):
    """Usa o OSD do Tesseract para desvirar páginas fotografadas de lado/cabeça p/ baixo."""
    p = os.path.join(tmpdir, "_osd.png")
    cv2.imwrite(p, img)
    r = subprocess.run(["tesseract", p, "-", "--psm", "0"], capture_output=True, text=True)
    m = re.search(r"Rotate: (\d+)", r.stdout)
    conf = re.search(r"Orientation confidence: ([\d.]+)", r.stdout)
    if m and conf and float(conf.group(1)) > 2:
        giro = int(m.group(1))
        if giro == 90:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        if giro == 180:
            return cv2.rotate(img, cv2.ROTATE_180)
        if giro == 270:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


# ------------------------------------------------------------ ordenação
RE_PAGINA = re.compile(r"(?:p[áa]g(?:ina)?\.?\s*(\d{1,3})(?:\s*(?:de|/)\s*\d{1,3})?)"
                       r"|(?:^\s*(\d{1,3})\s*/\s*\d{1,3}\s*$)", re.I | re.M)
# início de linha: "3- Dentro", "4) O estudo", "Questão 5 - Em"... (até 3 sujeirinhas antes)
RE_QUESTAO = re.compile(r"^\W{0,3}(?:[^\W\d]\W{1,2})?(?:quest[ãa]o\s*)?(\d{1,3})\s*[-–—.)]\s*[A-ZÀ-Ú\"“(]",
                        re.I | re.M)

# --psm 4 = "uma coluna de texto de tamanhos variados". Em provas lê os
# números das questões; o modo padrão costuma descartá-los como ruído.
PSM = "4"


def chave_da_pagina(texto):
    """Devolve (tipo, número) que diz onde a página entra na prova:
    - número de página escrito ("Página 2", "2/4") se existir;
    - senão, a primeira questão que abre linha, considerando só números que
      formam sequência (3, 4, 5...) — "90º" ou um ano solto não atrapalham;
    - senão, ("capa", 0) se for a folha com nome/matrícula/assinatura."""
    m = RE_PAGINA.search(texto)
    if m:
        return ("pagina", int(m.group(1) or m.group(2)))
    nums = sorted({int(n) for n in RE_QUESTAO.findall(texto) if 0 < int(n) < 200})
    em_sequencia = [n for n in nums if n + 1 in nums or n - 1 in nums]
    if em_sequencia or nums:
        return ("questao", (em_sequencia or nums)[0])
    if re.search(r"matr[íi]cula|aluno\(a\)|assinatura", texto, re.I):
        return ("capa", 0)
    return None


def ordenar(paginas, usar_exif=True):
    """Ordem base = data da foto (EXIF) ou nome do arquivo.
    Se as páginas tiverem número de página ou de questão, reordena por isso;
    páginas sem pista ficam logo depois da vizinha que veio antes delas."""
    def natural(s):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

    if usar_exif:
        base = sorted(paginas, key=lambda p: (p["data"] or datetime.max, natural(p["nome"])))
    else:
        base = sorted(paginas, key=lambda p: natural(p["nome"]))
    usa_pagina = sum(1 for p in base if p["chave"] and p["chave"][0] == "pagina") >= len(base) / 2
    ultima = -1.0
    for p in base:
        k = p["chave"]
        if k and ((k[0] == "pagina") == usa_pagina or k[0] == "capa"):
            p["ordem"] = float(k[1])
        else:
            p["ordem"] = ultima + 0.001  # sem pista: gruda na anterior
        ultima = p["ordem"]
    return sorted(base, key=lambda p: p["ordem"])


# ------------------------------------------------------------- principal
class ErroScanner(Exception):
    """Problema que impede gerar o PDF (sem Tesseract, sem imagens...)."""


def processar(entradas, saida, dpi=200, qualidade=70, cor=False, ordenar_auto=True, usar_exif=True,
              silencioso=False):
    """Gera o PDF e o .txt. ``usar_exif=False`` usa a ordem dos nomes dos arquivos como base
    (o bot nomeia as fotos pela ordem de envio). Devolve a lista de páginas na ordem final."""
    if not shutil.which("tesseract"):
        raise ErroScanner("Tesseract não encontrado. Veja o LEIAME.md para instalar.")
    arquivos = listar_imagens(entradas)
    if not arquivos:
        raise ErroScanner("Nenhuma imagem encontrada.")
    log = (lambda *a, **k: None) if silencioso else print

    largura = int(round(210 / 25.4 * dpi))  # largura A4 na resolução pedida
    tmp = tempfile.mkdtemp(prefix="scan_")
    paginas = []

    for i, arq in enumerate(arquivos):
        bgr, data = abrir_imagem(arq)
        cantos = achar_folha(bgr)
        if cantos is not None:
            folha = apagar_fundo(endireitar(bgr, cantos, largura))
            recorte = "ok"
        else:
            h, w = bgr.shape[:2]
            folha = cv2.resize(bgr, (largura, int(largura * h / w)), interpolation=cv2.INTER_CUBIC)
            recorte = "folha não detectada, usei a foto inteira"
        img = limpar(folha, cor)
        img = corrigir_rotacao(img, tmp)

        jpg = os.path.join(tmp, f"p{i:03d}.jpg")
        Image.fromarray(img if not cor else cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(
            jpg, "JPEG", quality=qualidade, optimize=True, progressive=True, dpi=(dpi, dpi))

        # OCR uma vez por página: sai o PDF da página (o JPEG vai embutido como
        # está, sem recomprimir, com o texto invisível por cima) e o .txt
        saida_pg = os.path.join(tmp, f"p{i:03d}")
        subprocess.run(["tesseract", jpg, saida_pg, "-l", "por", "--psm", PSM,
                        "--dpi", str(dpi), "pdf", "txt"], check=True, capture_output=True)
        with open(saida_pg + ".txt", encoding="utf-8") as f:
            texto = f.read()
        chave = chave_da_pagina(texto) if ordenar_auto else None
        paginas.append({"nome": os.path.basename(arq), "data": data, "pdf": saida_pg + ".pdf",
                        "texto": texto, "chave": chave, "recorte": recorte})
        log(f"  [{i + 1}/{len(arquivos)}] {os.path.basename(arq)}: recorte {recorte}; "
              f"pista de ordem = {chave}")

    if ordenar_auto:
        paginas = ordenar(paginas, usar_exif)

    # junta as páginas na ordem final
    from pypdf import PdfWriter
    pdf = PdfWriter()
    for p in paginas:
        pdf.append(p["pdf"])
    try:
        pdf.compress_identical_objects()  # a fonte invisível do OCR entra uma vez só
    except AttributeError:
        pass
    with open(saida, "wb") as f:
        pdf.write(f)

    # texto separado por página, mais fácil de usar na correção
    base = os.path.splitext(saida)[0]
    with open(base + ".txt", "w", encoding="utf-8") as f:
        for n, p in enumerate(paginas, 1):
            f.write(f"===== Página {n} ({p['nome']}) =====\n{p['texto'].strip()}\n\n")

    shutil.rmtree(tmp, ignore_errors=True)
    kb = os.path.getsize(saida) / 1024
    log(f"\nOrdem final: {[p['nome'] for p in paginas]}")
    log(f"PDF: {saida} ({kb:.0f} KB, {len(paginas)} pág.)  |  Texto: {base}.txt")
    return paginas


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scanner de provas: ordena, gera PDF compacto e faz OCR.")
    ap.add_argument("entradas", nargs="+", help="fotos ou pastas com fotos")
    ap.add_argument("-o", "--saida", default="prova_escaneada.pdf")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--qualidade", type=int, default=70)
    ap.add_argument("--cor", action="store_true")
    ap.add_argument("--sem-ordenar", action="store_true")
    a = ap.parse_args()
    try:
        processar(a.entradas, a.saida, a.dpi, a.qualidade, a.cor, not a.sem_ordenar)
    except ErroScanner as e:
        sys.exit(str(e))
