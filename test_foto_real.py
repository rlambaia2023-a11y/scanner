"""Ponta a ponta com uma foto real de prova (precisa do Tesseract com português).

Mede o que importa para a correção: a página entra na ordem certa, o PDF fica leve e
pesquisável, o texto das questões sai legível, e nada fica para trás na pasta temporária."""
import glob
import os
import shutil
import subprocess
import tempfile

import pytest
from PIL import Image

import scanner

FOTO = os.path.join(os.path.dirname(__file__), "fixtures", "prova_pagina.jpg")


def tem_por():
    if not shutil.which("tesseract"):
        return False
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
    return "por" in langs.split()


pytestmark = pytest.mark.skipif(not tem_por(), reason="Tesseract com português não instalado")


@pytest.fixture(scope="module")
def resultado(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("saida")
    antes = set(glob.glob(os.path.join(tempfile.gettempdir(), "scan_*")))
    paginas = scanner.processar([FOTO], str(pasta / "prova.pdf"), silencioso=True)
    depois = set(glob.glob(os.path.join(tempfile.gettempdir(), "scan_*")))
    return pasta, paginas, depois - antes


def test_folha_recortada_e_ordem_pela_primeira_questao(resultado):
    _, paginas, _ = resultado
    assert paginas[0]["recorte"] == "ok"
    assert paginas[0]["chave"] == ("questao", 3)


def test_pdf_compacto_e_pesquisavel(resultado):
    pasta, _, _ = resultado
    pdf = pasta / "prova.pdf"
    assert pdf.stat().st_size < 400 * 1024  # uma página A4 a 200 dpi
    from pypdf import PdfReader
    texto = PdfReader(str(pdf)).pages[0].extract_text()
    assert "oclusão" in texto


def test_texto_das_questoes(resultado):
    pasta, _, _ = resultado
    txt = (pasta / "prova.txt").read_text(encoding="utf-8")
    for trecho in ("Dentro do conceito de oclusão", "mordida aberta", "moldagem odontológica",
                   "principais materiais de moldagem"):
        assert trecho in txt


def test_pasta_temporaria_apagada(resultado):
    _, _, sobras = resultado
    assert not sobras


def test_foto_de_cabeca_para_baixo(tmp_path):
    virada = tmp_path / "virada.jpg"
    Image.open(FOTO).rotate(180, expand=True).save(virada, quality=92)
    paginas = scanner.processar([str(virada)], str(tmp_path / "v.pdf"), silencioso=True)
    assert "Dentro do conceito de oclusão" in paginas[0]["texto"]


def test_pasta_temporaria_apagada_mesmo_com_erro(tmp_path, monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError("falha no meio do OCR")

    monkeypatch.setattr(scanner, "_montar", quebra)
    antes = set(glob.glob(os.path.join(tempfile.gettempdir(), "scan_*")))
    with pytest.raises(RuntimeError):
        scanner.processar([FOTO], str(tmp_path / "x.pdf"), silencioso=True)
    assert set(glob.glob(os.path.join(tempfile.gettempdir(), "scan_*"))) == antes


def test_sem_imagem_da_erro_claro(tmp_path):
    with pytest.raises(scanner.ErroScanner):
        scanner.processar([str(tmp_path)], str(tmp_path / "x.pdf"), silencioso=True)
