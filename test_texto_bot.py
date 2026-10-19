"""Como o bot corta o texto para o botão de copiar (limite de mensagem do Telegram)."""
import bot


def test_separa_questoes_e_junta_a_que_atravessa_a_pagina():
    paginas = ["Aluno(a): Fulano\n1- Primeira pergunta\nA- alternativa",
               "continuação da 1\n2- Segunda pergunta\nfaz 90º com o braço"]
    cabecalho, questoes = bot.separar_questoes(paginas)
    assert cabecalho == "Aluno(a): Fulano"
    assert [n for n, _ in questoes] == [1, 2]
    assert "continuação da 1" in questoes[0][1]
    assert "90º" in questoes[1][1]


def test_numero_menor_dentro_do_enunciado_nao_abre_questao():
    _, questoes = bot.separar_questoes(["5- Liste:\n1) Primeiro item\n6- Outra"])
    assert [n for n, _ in questoes] == [5, 6]


def test_agrupar_nunca_corta_questao_que_cabe():
    questoes = [(n, "x" * 1000) for n in range(1, 8)]
    for parte in bot.agrupar_questoes(questoes, limite=3000):
        assert sum(len(t) + 2 for _, t in parte) <= 3000
    numeros = [n for parte in bot.agrupar_questoes(questoes, limite=3000) for n, _ in parte]
    assert numeros == list(range(1, 8))


def test_dividir_respeita_o_limite():
    blocos = bot.dividir("linha\n" * 2000 + "y" * 7000, limite=3000)
    assert all(len(b) <= 3000 for b in blocos)
    assert "".join(blocos).count("y") == 7000


def test_limpar_texto_tira_sujeira_de_borda():
    assert bot.limpar_texto("| \nTexto bom\n\n\n.\nOutro") == "Texto bom\n\nOutro"
