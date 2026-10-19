#!/usr/bin/env python3
"""
Bot do Telegram do Scanner para Correção
-----------------------------------------
Você manda as fotos das páginas (em qualquer ordem), manda "pronto" (ou só
espera alguns segundos) e recebe de volta:
  • um PDF compacto e pesquisável, com as páginas na ordem certa;
  • um .txt com o texto lido (OCR), separado por página.

Funciona por long polling: não precisa de domínio, webhook nem banco de dados.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN   obrigatório (crie o bot com o @BotFather)
  ALLOWED_CHAT_IDS     opcional, IDs separados por vírgula (restringe quem usa)
  JANELA_SEGUNDOS      opcional, padrão 25: fecha o lote sozinho após esse tempo sem fotos
  MAX_PAGINAS          opcional, padrão 40
  DPI, QUALIDADE       opcionais, padrão 200 e 70
"""
import html
import json
import logging
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

import requests

import scanner

log = logging.getLogger("scanner-bot")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
API = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")
ALLOWED = {int(x) for x in re.findall(r"-?\d+", os.environ.get("ALLOWED_CHAT_IDS", ""))}
JANELA = int(os.environ.get("JANELA_SEGUNDOS", "25"))
MAX_PAGINAS = int(os.environ.get("MAX_PAGINAS", "40"))
DPI = int(os.environ.get("DPI", "200"))
QUALIDADE = int(os.environ.get("QUALIDADE", "70"))
MAX_ARQUIVO = 20 * 1024 * 1024  # limite de download de arquivos de bots no Telegram
TEXTO_HORAS = int(os.environ.get("TEXTO_HORAS", "24"))  # por quanto tempo o botão de copiar funciona
MAX_TEXTOS = 200  # resultados guardados em memória para o botão de copiar
MAX_GALERIAS = 30  # resultados cujas páginas tratadas ficam guardadas em disco para a galeria
CACHE = os.path.join(tempfile.gettempdir(), "scanner_cache")  # páginas tratadas, para a galeria
BLOCO = 3000      # caracteres por mensagem (folga para o escape do HTML; limite do Telegram é 4096)

PRONTO = {"pronto", "pronta", "/pronto", "/pdf", "pdf", "terminei", "fim", "ok pronto"}
CANCELAR = {"/cancelar", "cancelar"}

# ------------------------------------------------------------------ textos

INICIO = (
    "Oi! Eu transformo fotos de prova em PDF.\n\n"
    "Manda as fotos das páginas, pode ser fora de ordem. Quando terminar, manda “pronto” "
    f"(ou só espera {JANELA} segundos). Eu recorto cada folha, endireito, coloco na ordem pela numeração "
    "e te devolvo um PDF leve, com o texto pesquisável, mais um .txt com o que li.\n\n"
    "Dicas:\n"
    "• Folha inteira na foto, com um pouco de fundo aparecendo em volta.\n"
    "• Mandando como arquivo (📎 › Arquivo) a qualidade fica melhor.\n"
    "• Correção com caneta colorida? Manda /cor antes das fotos.\n"
    "• Pode mandar quantas páginas quiser (até 40): todas viram um PDF só.\n"
    "• Depois do PDF dá para copiar o texto e salvar as páginas tratadas na galeria.\n\n"
    "Comandos: /pronto, /cancelar, /cor, /pb, /ajuda"
)
TECLADO_COLETA = [[{"text": "✅ Pronto, gerar PDF", "callback_data": "fim"},
                   {"text": "✖️ Cancelar", "callback_data": "cancel"}]]
SEM_FOTOS = "Ainda não recebi nenhuma foto. Manda as páginas da prova primeiro."
CANCELADO = "Beleza, descartei as fotos desse lote. Pode mandar outras."
NADA_PRA_CANCELAR = "Não tem nenhum lote em andamento."
SO_IMAGEM = "Por aqui eu só aceito fotos ou imagens (JPG, PNG, WEBP ou HEIC)."
MUITO_GRANDE = "Esse arquivo passa de 20 MB, e o Telegram não me deixa baixar. Manda uma foto menor?"
LIMITE = f"Chegou no limite de {MAX_PAGINAS} páginas por PDF. Manda “pronto” para eu montar este."
ERRO = ("😕 Não consegui montar o PDF dessa vez. Tenta mandar as fotos de novo daqui a pouco. "
        "Se continuar, manda como arquivo (📎 › Arquivo).")
NAO_AUTORIZADO = "Este bot é de uso restrito."
OPCOES = ("O que mais você quer fazer com essa prova?\n"
          "📋 Copiar o texto: mando aqui no chat, é só tocar no bloco para copiar.\n"
          "🖼️ Salvar na galeria: mando as páginas já tratadas como fotos.\n\n"
          "O PDF acima já tem todas as páginas juntas. Para guardar no celular, toque nele e use "
          "Compartilhar › Salvar em Arquivos.")
GALERIA_DICA = ("🖼️ Aí estão as páginas tratadas. Para salvar na galeria, abra a foto e use a opção de salvar "
                "(no iPhone: compartilhar › Salvar Imagem; no Android: menu ⋮ › Salvar na galeria).")
GALERIA_EXPIROU = ("As imagens dessa prova não estão mais guardadas (passou do prazo ou o bot reiniciou). "
                   "O PDF continua no chat com todas as páginas; se quiser as fotos, manda as páginas de novo.")
LOTE_JA_ENVIADO = "Esse lote já foi enviado"
TEXTO_EXPIROU = ("Esse texto não está mais guardado (passou do prazo ou o bot reiniciou). "
                 "Abre o .txt que mandei junto com o PDF, ou manda as fotos de novo.")
SEM_TEXTO = "Não encontrei texto nessa página. Pode ser que a foto esteja escura ou tremida."


def msg_recebidas(n):
    return (f"📄 {n} página(s) recebida(s). Pode mandar mais páginas ou tocar em ✅ Pronto. "
            f"Se não chegar mais nada, em {JANELA} segundos eu começo sozinho.")


def msg_fechado(n):
    return f"📄 {n} página(s) recebida(s). Começando o PDF…"


def msg_processando(n, fila):
    extra = f" Tem {fila} PDF(s) na frente, já já chega a sua vez." if fila else ""
    return f"⏳ Montando o PDF com {n} página(s). Leva uns segundos por página.{extra}"


def msg_cor(ligada):
    return ("🎨 Combinado: o próximo PDF sai colorido (fica um pouco maior)." if ligada
            else "⚫ Combinado: o próximo PDF sai em tons de cinza, mais leve.")


# ------------------------------------------------------------- Telegram API


class Telegram:
    def __init__(self, token):
        self.base = f"{API}/bot{token}"
        self.arquivos = f"{API}/file/bot{token}"
        self.s = requests.Session()

    def chamar(self, metodo, _timeout=30, files=None, **params):
        for tentativa in range(4):
            try:
                if files:
                    r = self.s.post(f"{self.base}/{metodo}", data=params, files=files, timeout=_timeout)
                else:
                    r = self.s.post(f"{self.base}/{metodo}", json=params, timeout=_timeout)
                corpo = r.json()
            except (requests.RequestException, ValueError) as e:
                espera = 2 ** tentativa
                log.warning("falha de rede em %s (%s); tentando de novo em %ss", metodo, type(e).__name__, espera)
                time.sleep(espera)
                continue
            if corpo.get("ok"):
                return corpo["result"]
            retry = (corpo.get("parameters") or {}).get("retry_after")
            if retry:
                time.sleep(int(retry) + 1)
                continue
            raise RuntimeError(f"{metodo}: {corpo.get('description')}")
        raise RuntimeError(f"{metodo}: sem resposta do Telegram")

    def enviar(self, chat_id, texto, teclado=None, html_=False):
        params = {"chat_id": chat_id, "text": texto[:4096]}
        if teclado:
            params["reply_markup"] = {"inline_keyboard": teclado}
        if html_:
            params["parse_mode"] = "HTML"
        try:
            return self.chamar("sendMessage", **params)
        except RuntimeError as e:
            log.error("não consegui enviar mensagem: %s", e)
            return None

    def editar(self, chat_id, msg_id, texto, teclado=None):
        params = {"chat_id": chat_id, "message_id": msg_id, "text": texto[:4096]}
        if teclado:
            params["reply_markup"] = {"inline_keyboard": teclado}
        try:
            self.chamar("editMessageText", **params)
        except RuntimeError as e:
            if "not modified" not in str(e):
                log.warning("não consegui editar mensagem: %s", e)

    def enviar_album(self, chat_id, fotos):
        """fotos: [(nome, bytes, legenda)]. Manda em álbuns de até 10 (limite do Telegram)."""
        for i in range(0, len(fotos), 10):
            grupo = fotos[i:i + 10]
            if len(grupo) == 1:
                nome, dados, legenda = grupo[0]
                self.chamar("sendPhoto", _timeout=120, files={"photo": (nome, dados, "image/jpeg")},
                            chat_id=str(chat_id), caption=legenda)
                continue
            media = [{"type": "photo", "media": f"attach://f{j}", "caption": leg}
                     for j, (_, _, leg) in enumerate(grupo)]
            files = {f"f{j}": (nome, dados, "image/jpeg") for j, (nome, dados, _) in enumerate(grupo)}
            self.chamar("sendMediaGroup", _timeout=180, files=files, chat_id=str(chat_id),
                        media=json.dumps(media))

    def responder_botao(self, callback_id, texto=None):
        params = {"callback_query_id": callback_id}
        if texto:
            params["text"] = texto[:200]
        try:
            self.chamar("answerCallbackQuery", **params)
        except RuntimeError:
            pass

    def enviar_arquivo(self, chat_id, nome, dados, mime, legenda=None):
        params = {"chat_id": str(chat_id)}
        if legenda:
            params["caption"] = legenda[:1024]
        return self.chamar("sendDocument", _timeout=120, files={"document": (nome, dados, mime)}, **params)

    def baixar(self, file_id, destino_sem_ext):
        info = self.chamar("getFile", file_id=file_id)
        if info.get("file_size", 0) > MAX_ARQUIVO:
            raise ValueError("arquivo grande demais")
        caminho = info["file_path"]
        ext = os.path.splitext(caminho)[1].lower()
        if ext not in scanner.EXTS:  # .jfif e afins: o Pillow reconhece pelo conteúdo
            ext = ".jpg"
        destino = destino_sem_ext + ext
        try:
            with self.s.get(f"{self.arquivos}/{caminho}", stream=True, timeout=120) as r:
                if r.status_code != 200:
                    raise ValueError(f"download falhou (HTTP {r.status_code})")
                with open(destino, "wb") as f:
                    for parte in r.iter_content(64 * 1024):
                        f.write(parte)
        except requests.RequestException as e:
            # a mensagem original traz a URL, que contém o token: não propaga
            raise ValueError(f"falha de rede no download ({type(e).__name__})") from None
        return destino


# ------------------------------------------------------------------- lotes


@dataclass
class Lote:
    fotos: list = field(default_factory=list)  # file_id na ordem de envio
    ultimo: float = 0.0
    cor: bool = False
    msg_id: int | None = None  # mensagem "N página(s) recebida(s)", atualizada a cada foto
    mostrado: int = 0


class Bot:
    def __init__(self, tg):
        self.tg = tg
        self.lotes = {}           # chat_id -> Lote em coleta
        self.cor = {}             # chat_id -> preferência de cor para o próximo lote
        self.trava = threading.Lock()
        self.fila = queue.Queue()
        self.textos = OrderedDict()  # id curto -> {"chat", "paginas": [str], "quando"}

    # ---------------------------------------------------------- entrada
    def tratar(self, update):
        if update.get("callback_query"):
            self.tratar_botao(update["callback_query"])
            return
        msg = update.get("message") or update.get("edited_message")
        if not msg:
            return
        chat = msg["chat"]
        chat_id = chat["id"]
        if chat.get("type") != "private":
            return
        if ALLOWED and chat_id not in ALLOWED:
            self.tg.enviar(chat_id, NAO_AUTORIZADO)
            return

        file_id = None
        if msg.get("photo"):
            file_id = max(msg["photo"], key=lambda p: p.get("width", 0) * p.get("height", 0))["file_id"]
        elif msg.get("document"):
            doc = msg["document"]
            mime = (doc.get("mime_type") or "").lower()
            nome = (doc.get("file_name") or "").lower()
            if not (mime.startswith("image/") or nome.endswith((".heic", ".heif"))):
                self.tg.enviar(chat_id, SO_IMAGEM)
                return
            if doc.get("file_size", 0) > MAX_ARQUIVO:
                self.tg.enviar(chat_id, MUITO_GRANDE)
                return
            file_id = doc["file_id"]

        if file_id:
            self.receber_foto(chat_id, file_id)
            return

        texto = (msg.get("text") or "").strip()
        cmd = texto.split("@")[0].lower() if texto else ""
        if cmd in {"/start", "/ajuda", "/help"}:
            self.tg.enviar(chat_id, INICIO)
        elif cmd in PRONTO:
            if not self.fechar(chat_id):
                self.tg.enviar(chat_id, SEM_FOTOS)
        elif cmd in CANCELAR:
            with self.trava:
                lote = self.lotes.pop(chat_id, None)
            if lote and lote.msg_id:
                self.tg.editar(chat_id, lote.msg_id, "✖️ " + CANCELADO)
            self.tg.enviar(chat_id, CANCELADO if lote else NADA_PRA_CANCELAR)
        elif cmd in {"/cor", "/pb"}:
            ligada = cmd == "/cor"
            with self.trava:
                self.cor[chat_id] = ligada
                if chat_id in self.lotes:
                    self.lotes[chat_id].cor = ligada
            self.tg.enviar(chat_id, msg_cor(ligada))
        else:
            self.tg.enviar(chat_id, "Manda as fotos das páginas da prova, ou /ajuda para ver como funciona.")

    def receber_foto(self, chat_id, file_id):
        with self.trava:
            lote = self.lotes.get(chat_id)
            primeira = lote is None
            if primeira:
                lote = self.lotes[chat_id] = Lote(cor=self.cor.get(chat_id, False))
            if len(lote.fotos) >= MAX_PAGINAS:
                cheio = True
            else:
                cheio = False
                lote.fotos.append(file_id)
                lote.ultimo = time.monotonic()
        if cheio:
            self.tg.enviar(chat_id, LIMITE)
        elif primeira:
            res = self.tg.enviar(chat_id, msg_recebidas(1), teclado=TECLADO_COLETA)
            with self.trava:
                lote.msg_id, lote.mostrado = (res or {}).get("message_id"), 1

    def fechar(self, chat_id):
        with self.trava:
            lote = self.lotes.pop(chat_id, None)
        if not lote or not lote.fotos:
            return False
        if lote.msg_id:  # tira os botões para não fecharem o lote duas vezes
            self.tg.editar(chat_id, lote.msg_id, msg_fechado(len(lote.fotos)))
        self.tg.enviar(chat_id, msg_processando(len(lote.fotos), self.fila.qsize()))
        self.fila.put((chat_id, lote))
        return True

    def vigiar_janelas(self):
        """Atualiza o contador de páginas, fecha sozinho os lotes que ficaram JANELA segundos
        sem foto nova e apaga os resultados vencidos."""
        ultima_limpeza = time.monotonic()
        while True:
            time.sleep(2)
            agora = time.monotonic()
            with self.trava:
                vencidos = [c for c, lote in self.lotes.items() if lote.fotos and agora - lote.ultimo >= JANELA]
                contadores = []
                for c, lote in self.lotes.items():
                    if lote.msg_id and c not in vencidos and len(lote.fotos) != lote.mostrado:
                        lote.mostrado = len(lote.fotos)
                        contadores.append((c, lote.msg_id, lote.mostrado))
            for chat_id, msg_id, n in contadores:
                self.tg.editar(chat_id, msg_id, msg_recebidas(n), teclado=TECLADO_COLETA)
            for chat_id in vencidos:
                self.fechar(chat_id)
            if agora - ultima_limpeza > 600:
                ultima_limpeza = agora
                self.limpar_resultados()

    # ---------------------------------------------------------- trabalho
    def trabalhar(self):
        while True:
            chat_id, lote = self.fila.get()
            try:
                self.montar_pdf(chat_id, lote)
            except Exception:  # noqa: BLE001 — nunca derruba o bot por causa de um lote
                log.exception("falha ao montar o PDF")
                self.tg.enviar(chat_id, ERRO)
            finally:
                self.fila.task_done()

    def montar_pdf(self, chat_id, lote):
        pasta = tempfile.mkdtemp(prefix="lote_")
        antigo_tmp = tempfile.tempdir
        try:
            tempfile.tempdir = pasta  # temporários do scanner também somem no fim
            fotos, puladas = [], []
            for i, file_id in enumerate(lote.fotos, 1):
                try:
                    fotos.append(self.tg.baixar(file_id, os.path.join(pasta, f"foto_{i:03d}")))
                except Exception as e:  # noqa: BLE001
                    log.warning("foto %s não baixou: %s", i, e)
                    puladas.append(i)
            if not fotos:
                self.tg.enviar(chat_id, ERRO)
                return

            inicio = time.monotonic()
            saida = os.path.join(pasta, "prova.pdf")
            tid = uuid.uuid4().hex[:10]
            pasta_galeria = os.path.join(CACHE, tid)
            paginas = scanner.processar(fotos, saida, dpi=DPI, qualidade=QUALIDADE, cor=lote.cor,
                                        usar_exif=False, silencioso=True, pasta_imagens=pasta_galeria)
            with open(saida, "rb") as f:
                pdf = f.read()
            with open(os.path.join(pasta, "prova.txt"), "rb") as f:
                txt = f.read()
            log.info("PDF pronto: %d pág., %d KB, %.0fs", len(paginas), len(pdf) // 1024,
                     time.monotonic() - inicio)

            nome = time.strftime("prova_%Y-%m-%d_%H%M")
            self.tg.enviar_arquivo(chat_id, f"{nome}.pdf", pdf, "application/pdf",
                                   legenda=legenda(paginas, len(pdf), puladas))
            self.tg.enviar_arquivo(chat_id, f"{nome}.txt", txt, "text/plain")
            self.oferecer_opcoes(chat_id, tid, [p["texto"] for p in paginas], pasta_galeria)
        finally:
            tempfile.tempdir = antigo_tmp
            shutil.rmtree(pasta, ignore_errors=True)

    # ------------------------------------------------------- copiar texto
    def guardar_resultado(self, tid, chat_id, paginas, pasta):
        apagar = []
        with self.trava:
            self.textos[tid] = {"chat": chat_id, "paginas": paginas, "pasta": pasta, "quando": time.monotonic()}
            while len(self.textos) > MAX_TEXTOS:
                apagar.append(self.textos.popitem(last=False)[1].get("pasta"))
            com_imagens = [v for v in self.textos.values() if v.get("pasta")]
            for v in com_imagens[:max(0, len(com_imagens) - MAX_GALERIAS)]:
                apagar.append(v["pasta"])
                v["pasta"] = None
        for pasta in apagar:
            if pasta:
                shutil.rmtree(pasta, ignore_errors=True)

    def limpar_resultados(self):
        limite = TEXTO_HORAS * 3600
        with self.trava:
            velhos = [t for t, v in self.textos.items() if time.monotonic() - v["quando"] > limite]
            pastas = [self.textos.pop(t).get("pasta") for t in velhos]
        for pasta in pastas:
            if pasta:
                shutil.rmtree(pasta, ignore_errors=True)

    def oferecer_opcoes(self, chat_id, tid, paginas, pasta):
        self.guardar_resultado(tid, chat_id, paginas, pasta)
        teclado = [[{"text": "📋 Copiar todo o texto", "callback_data": f"cp:{tid}:all"}],
                   [{"text": "🖼️ Salvar páginas na galeria", "callback_data": f"gl:{tid}"}]]
        if len(paginas) > 1:
            botoes = [{"text": f"📋 {i}", "callback_data": f"cp:{tid}:{i}"}
                      for i in range(1, min(len(paginas), 40) + 1)]
            teclado += [botoes[i:i + 5] for i in range(0, len(botoes), 5)]
        self.tg.enviar(chat_id, OPCOES, teclado=teclado)

    def buscar_resultado(self, tid, chat_id):
        with self.trava:
            item = self.textos.get(tid)
        if not item or item["chat"] != chat_id or time.monotonic() - item["quando"] > TEXTO_HORAS * 3600:
            return None
        return item

    def tratar_galeria(self, cb, chat_id, tid):
        item = self.buscar_resultado(tid, chat_id)
        pasta = item and item.get("pasta")
        if not pasta or not os.path.isdir(pasta):
            self.tg.responder_botao(cb["id"], "Essas imagens expiraram")
            self.tg.enviar(chat_id, GALERIA_EXPIROU)
            return
        self.tg.responder_botao(cb["id"], "Enviando as páginas…")
        nomes = sorted(n for n in os.listdir(pasta) if n.endswith(".jpg"))
        fotos = []
        for i, nome in enumerate(nomes, 1):
            with open(os.path.join(pasta, nome), "rb") as f:
                fotos.append((nome, f.read(), f"Página {i} de {len(nomes)}"))
        try:
            self.tg.enviar_album(chat_id, fotos)
        except RuntimeError as e:
            log.error("falha ao mandar a galeria: %s", e)
            self.tg.enviar(chat_id, ERRO)
            return
        self.tg.enviar(chat_id, GALERIA_DICA)

    def tratar_botao(self, cb):
        chat_id = (cb.get("message") or {}).get("chat", {}).get("id")
        dado = cb.get("data") or ""
        if chat_id is None or (ALLOWED and chat_id not in ALLOWED):
            self.tg.responder_botao(cb["id"])
            return
        if dado == "fim":
            ok = self.fechar(chat_id)
            self.tg.responder_botao(cb["id"], None if ok else LOTE_JA_ENVIADO)
            return
        if dado == "cancel":
            with self.trava:
                lote = self.lotes.pop(chat_id, None)
            self.tg.responder_botao(cb["id"], None if lote else LOTE_JA_ENVIADO)
            if lote and lote.msg_id:
                self.tg.editar(chat_id, lote.msg_id, "✖️ " + CANCELADO)
            return
        partes = dado.split(":")
        if len(partes) == 2 and partes[0] == "gl":
            self.tratar_galeria(cb, chat_id, partes[1])
            return
        if len(partes) != 3 or partes[0] != "cp":
            self.tg.responder_botao(cb["id"])
            return
        _, tid, qual = partes
        item = self.buscar_resultado(tid, chat_id)
        if not item:
            self.tg.responder_botao(cb["id"], "Esse texto expirou")
            self.tg.enviar(chat_id, TEXTO_EXPIROU)
            return
        paginas = item["paginas"]
        if qual == "all":
            escolhidas = list(enumerate(paginas, 1))
        elif qual.isdigit() and 1 <= int(qual) <= len(paginas):
            escolhidas = [(int(qual), paginas[int(qual) - 1])]
        else:
            self.tg.responder_botao(cb["id"])
            return
        self.tg.responder_botao(cb["id"], "Enviando o texto…")
        if qual == "all":
            # o .txt inteiro, juntando as páginas, no menor número de blocos possível
            if len(paginas) > 1:
                corpo = "\n\n".join(f"===== Página {n} =====\n{limpar_texto(t)}" for n, t in escolhidas)
            else:
                corpo = limpar_texto(paginas[0])
            if len(dividir(corpo)) > 1:
                # não cabe numa mensagem: separa por questão, em ordem, sem cortar questão no meio
                if self.mandar_por_questoes(chat_id, [t for _, t in escolhidas]):
                    return
            self.mandar_blocos(chat_id, "Texto completo", corpo)
        else:
            n, texto = escolhidas[0]
            self.mandar_blocos(chat_id, f"Página {n}", limpar_texto(texto))

    def mandar_por_questoes(self, chat_id, paginas):
        """Devolve False se não achou questões (aí o chamador manda por blocos simples)."""
        cabecalho, questoes = separar_questoes(paginas)
        if len(questoes) < 2:
            return False
        partes = agrupar_questoes(questoes)
        total = len(partes) + (1 if cabecalho else 0)
        primeira, ultima = questoes[0][0], questoes[-1][0]
        self.tg.enviar(chat_id, f"A prova é longa, então separei por questão ({primeira} a {ultima}, "
                                f"em ordem) e mandei em {total} partes. Toque em cada bloco para copiar.")
        n = 0
        if cabecalho:
            n += 1
            self.tg.enviar(chat_id, f"<b>Parte {n}/{total} · Cabeçalho</b>\n<pre>{html.escape(cabecalho)}</pre>",
                           html_=True)
        for grupo in partes:
            n += 1
            nums = [q for q, _ in grupo]
            faixa = f"Questão {nums[0]}" if len(nums) == 1 else f"Questões {nums[0]} a {nums[-1]}"
            corpo = "\n\n".join(t for _, t in grupo)
            self.tg.enviar(chat_id, f"<b>Parte {n}/{total} · {faixa}</b>\n<pre>{html.escape(corpo)}</pre>",
                           html_=True)
        return True

    def mandar_blocos(self, chat_id, titulo, texto):
        blocos = dividir(texto)
        if not blocos:
            self.tg.enviar(chat_id, f"<b>{titulo}</b>\n{SEM_TEXTO}", html_=True)
            return
        if len(blocos) > 1:
            self.tg.enviar(chat_id, f"O texto é grande, então veio em {len(blocos)} partes. "
                                    "Toque em cada bloco, na ordem, para copiar.")
        for i, bloco in enumerate(blocos, 1):
            sufixo = f" ({i}/{len(blocos)})" if len(blocos) > 1 else ""
            self.tg.enviar(chat_id, f"<b>{titulo}{sufixo}</b>\n<pre>{html.escape(bloco)}</pre>", html_=True)

    # ------------------------------------------------------------- laço
    def rodar(self):
        shutil.rmtree(CACHE, ignore_errors=True)
        os.makedirs(CACHE, exist_ok=True)
        threading.Thread(target=self.vigiar_janelas, daemon=True).start()
        threading.Thread(target=self.trabalhar, daemon=True).start()
        self.tg.chamar("deleteWebhook")  # long polling não convive com webhook
        eu = self.tg.chamar("getMe")
        log.info("bot @%s no ar (janela %ss, até %s páginas)", eu.get("username"), JANELA, MAX_PAGINAS)
        offset = None
        while True:
            try:
                params = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                updates = self.tg.chamar("getUpdates", _timeout=70, **params)
            except RuntimeError as e:
                # 409 = outra cópia do bot está rodando com o mesmo token
                log.error("getUpdates falhou: %s", e)
                time.sleep(5)
                continue
            for u in updates:
                offset = u["update_id"] + 1
                try:
                    self.tratar(u)
                except Exception:  # noqa: BLE001
                    log.exception("erro tratando update")


def limpar_texto(texto):
    """Tira as linhas de sujeira que o OCR pega nas bordas (só símbolos soltos) e
    excesso de linhas em branco, para o texto copiado ficar limpo."""
    linhas = []
    for linha in texto.replace("\f", "").splitlines():
        linha = linha.rstrip()
        if linha and sum(c.isalnum() for c in linha) < 2:
            continue
        if not linha and (not linhas or not linhas[-1]):
            continue
        linhas.append(linha)
    return "\n".join(linhas).strip()


RE_INICIO_QUESTAO = re.compile(
    r"^\W{0,3}(?:[^\W\d]\W{1,2})?(?:quest[ãa]o\s*)?(\d{1,3})\s*[-–—.)]\s*[A-ZÀ-Ú\"“(]", re.I)


def separar_questoes(paginas):
    """Junta as páginas (já na ordem) e corta o texto em questões.

    Uma linha só abre questão se o número vier logo depois da anterior (até 5 à frente),
    assim "90º", datas ou itens numerados dentro do enunciado não viram questão falsa.
    Questão que começa numa página e termina na outra fica inteira.
    Devolve (cabeçalho, [(número, texto), ...]) em ordem crescente de número."""
    linhas = []  # (linha, é a 1ª questão possível da página?)
    for t in paginas:
        linhas += [(ln, i == 0) for i, ln in enumerate(limpar_texto(t).splitlines())]
    cabecalho, questoes, atual, ultimo = [], {}, None, None
    inicio_pagina = False
    for linha, nova_pagina in linhas:
        if nova_pagina:
            inicio_pagina = True
        m = RE_INICIO_QUESTAO.match(linha)
        n = int(m.group(1)) if m else None
        # no começo de cada página aceita um salto maior para frente (página do meio faltando);
        # número menor que o anterior nunca abre questão ("1) item" dentro de um enunciado)
        abre = n is not None and 0 < n < 200 and n not in questoes and (
            ultimo is None or (ultimo < n and (inicio_pagina or n <= ultimo + 5)))
        if abre:
            inicio_pagina = False
            atual, ultimo = n, n
            questoes[n] = [linha[m.start(1):]]  # tira a sujeira antes do número
        elif atual is None:
            cabecalho.append(linha)
        else:
            questoes[atual].append(linha)
    def limpa(ls):
        return re.sub(r"\n{3,}", "\n\n", "\n".join(ls)).strip()

    return limpa(cabecalho), [(n, limpa(questoes[n])) for n in sorted(questoes)]


def agrupar_questoes(questoes, limite=BLOCO):
    """Junta questões inteiras em partes que cabem numa mensagem.
    Só divide uma questão se ela sozinha passar do limite."""
    partes, atual, tamanho = [], [], 0
    for n, texto in questoes:
        pedacos = dividir(texto, limite) if len(texto) > limite else [texto]
        for i, pedaco in enumerate(pedacos):
            extra = len(pedaco) + 2
            if atual and tamanho + extra > limite:
                partes.append(atual)
                atual, tamanho = [], 0
            atual.append((n, pedaco))
            tamanho += extra
            if len(pedacos) > 1 and i < len(pedacos) - 1:  # questão gigante: cada pedaço em sua parte
                partes.append(atual)
                atual, tamanho = [], 0
    if atual:
        partes.append(atual)
    return partes


def dividir(texto, limite=BLOCO):
    """Quebra o texto em blocos que cabem numa mensagem, sem cortar linhas no meio."""
    blocos, atual = [], ""
    for linha in texto.splitlines():
        while len(linha) > limite:  # linha gigante (raro): corta à força
            if atual:
                blocos.append(atual)
                atual = ""
            blocos.append(linha[:limite])
            linha = linha[limite:]
        if len(atual) + len(linha) + 1 > limite:
            blocos.append(atual)
            atual = linha
        else:
            atual = f"{atual}\n{linha}" if atual else linha
    if atual.strip():
        blocos.append(atual)
    return [b for b in blocos if b.strip()]


def legenda(paginas, tamanho, puladas):
    partes = [f"📄 Pronto: {len(paginas)} página(s), {max(1, tamanho // 1024)} KB, com texto pesquisável."]
    ordem = [int(re.search(r"(\d+)", p["nome"]).group(1)) for p in paginas]
    if ordem != sorted(ordem):
        partes.append("Reorganizei pela numeração: fotos " + ", ".join(map(str, ordem)) + ".")
    sem_recorte = [str(int(re.search(r"(\d+)", p["nome"]).group(1))) for p in paginas if p["recorte"] != "ok"]
    if sem_recorte:
        partes.append(f"Não achei a borda da folha na(s) foto(s) {', '.join(sem_recorte)}; usei a foto inteira.")
    if puladas:
        partes.append(f"⚠️ Não consegui baixar a(s) foto(s) {', '.join(map(str, puladas))}. Manda de novo se precisar.")
    return "\n".join(partes)


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if not TOKEN:
        raise SystemExit("Falta a variável TELEGRAM_BOT_TOKEN (crie o bot no @BotFather).")
    if not shutil.which("tesseract"):
        raise SystemExit("Tesseract não encontrado. Use o Dockerfile ou instale tesseract-ocr-por.")
    Bot(Telegram(TOKEN)).rodar()


if __name__ == "__main__":
    main()
