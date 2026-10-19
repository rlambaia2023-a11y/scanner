"""Regras de ordem das páginas (sem OCR: rápido e roda em qualquer máquina)."""
from datetime import datetime

import scanner


def pg(nome, chave, data=None):
    return {"nome": nome, "chave": chave, "data": data}


class TestChaveDaPagina:
    def test_numero_de_pagina_escrito_ganha(self):
        assert scanner.chave_da_pagina("Página 2 de 4\n3- Dentro do conceito") == ("pagina", 2)

    def test_formato_barra(self):
        assert scanner.chave_da_pagina("texto\n 3/5 \n") == ("pagina", 3)

    def test_primeira_questao_da_sequencia(self):
        assert scanner.chave_da_pagina("8- Assinale\n9- Marque\n10- Explique") == ("questao", 8)

    def test_tolera_uma_questao_que_o_ocr_perdeu(self):
        # caso real da foto de teste: o "4-" sublinhado some e sobra 3, 5, 6, 7
        texto = "3- Dentro do conceito\nO estudo da cinesiologia\n5- Em relação\n6- A moldagem\n7- Temos"
        assert scanner.chave_da_pagina(texto) == ("questao", 3)

    def test_numero_solto_longe_da_sequencia_nao_atrapalha(self):
        texto = "1- Ano da prova\n12- Questão doze\n13- Questão treze"
        assert scanner.chave_da_pagina(texto) == ("questao", 12)

    def test_itens_com_salto_dentro_do_enunciado_nao_viram_primeira_questao(self):
        texto = "15- Considere\n1. Afirmativa\n3. Afirmativa\n16- Próxima\n17- Outra"
        assert scanner.chave_da_pagina(texto) == ("questao", 15)

    def test_duas_questoes_com_uma_perdida_no_meio(self):
        assert scanner.chave_da_pagina("3- Dentro\n5- Em relação") == ("questao", 3)

    def test_capa_sem_questao(self):
        assert scanner.chave_da_pagina("Número de matrícula:\nAluno(a):") == ("capa", 0)

    def test_sem_pista(self):
        assert scanner.chave_da_pagina("texto qualquer sem número") is None


class TestOrdenar:
    def test_reordena_pela_questao(self):
        paginas = [pg("a1.jpg", ("questao", 8)), pg("a2.jpg", ("questao", 1)), pg("a3.jpg", ("questao", 4))]
        assert [p["nome"] for p in scanner.ordenar(paginas)] == ["a2.jpg", "a3.jpg", "a1.jpg"]

    def test_capa_vem_antes(self):
        paginas = [pg("a1.jpg", ("questao", 1)), pg("a2.jpg", ("capa", 0))]
        assert [p["nome"] for p in scanner.ordenar(paginas)] == ["a2.jpg", "a1.jpg"]

    def test_pagina_sem_pista_gruda_na_anterior(self):
        paginas = [pg("f1.jpg", ("questao", 5)), pg("f2.jpg", None), pg("f3.jpg", ("questao", 1))]
        assert [p["nome"] for p in scanner.ordenar(paginas)] == ["f3.jpg", "f1.jpg", "f2.jpg"]

    def test_nome_em_ordem_natural(self):
        paginas = [pg("foto10.jpg", None), pg("foto2.jpg", None), pg("foto1.jpg", None)]
        assert [p["nome"] for p in scanner.ordenar(paginas)] == ["foto1.jpg", "foto2.jpg", "foto10.jpg"]

    def test_exif_define_a_base(self):
        paginas = [pg("b.jpg", None, datetime(2026, 10, 5, 10, 2)), pg("a.jpg", None, datetime(2026, 10, 5, 10, 1))]
        assert [p["nome"] for p in scanner.ordenar(paginas)] == ["a.jpg", "b.jpg"]
        assert [p["nome"] for p in scanner.ordenar(paginas, usar_exif=False)] == ["a.jpg", "b.jpg"]

    def test_numero_de_pagina_prevalece_quando_a_maioria_tem(self):
        paginas = [pg("x1.jpg", ("pagina", 2)), pg("x2.jpg", ("pagina", 1)), pg("x3.jpg", ("questao", 1))]
        ordem = [p["nome"] for p in scanner.ordenar(paginas)]
        assert ordem.index("x2.jpg") < ordem.index("x1.jpg")
