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
  JANELA_SEGUNDOS      opcional, padrão 30: fecha o lote sozinho após esse tempo sem fotos
  MAX_PAGINAS          opcional, padrão 40
  DPI, QUALIDADE       opcionais, padrão 200 e 70
"""
import html
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
JANELA = int(os.environ.get("JANELA_SEGUNDOS", "30"))
MAX_PAGINAS = int(os.environ.get("MAX_PAGINAS", "40"))
DPI = int(os.environ.get("DPI", "200"))
QUALIDADE = int(os.environ.get("QUALIDADE", "70"))
MAX_ARQUIVO = 20 * 1024 * 1024  # limite de download de arquivos de bots no Telegram
TEXTO_HORAS = int(os.environ.get("TEXTO_HORAS", "24"))  # por quanto tempo o botão de copiar funciona
MAX_TEXTOS = 200  # resultados guardados em memória para o botão de copiar
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
    "• Depois do PDF aparece o botão 📋 Copiar texto: o texto vem aqui no chat, pronto para copiar.\n\n"
    "Comandos: /pronto, /cancelar, /cor, /pb, /ajuda"
)
PRIMEIRA_FOTO = "📄 Recebi. Pode mandar as outras páginas e depois “pronto”."
SEM_FOTOS = "Ainda não recebi nenhuma foto. Manda as páginas da prova primeiro."
CANCELADO = "Beleza, descartei as fotos desse lote. Pode mandar outras."
NADA_PRA_CANCELAR = "Não tem nenhum lote em andamento."
SO_IMAGEM = "Por aqui eu só aceito fotos ou imagens (JPG, PNG, WEBP ou HEIC)."
MUITO_GRANDE = "Esse arquivo passa de 20 MB, e o Telegram não me deixa baixar. Manda uma foto menor?"
LIMITE = f"Chegou no limite de {MAX_PAGINAS} páginas por PDF. Manda “pronto” para eu montar este."
ERRO = ("😕 Não consegui montar o PDF dessa vez. Tenta mandar as fotos de novo daqui a pouco. "
        "Se continuar, manda como arquivo (📎 › Arquivo).")
NAO_AUTORIZADO = "Este bot é de uso restrito."
COPIAR_CONVITE = ("📋 Quer copiar o texto? Toque em “Copiar todo o texto” e eu mando aqui embaixo. "
                  "Depois é só tocar no bloco que ele copia inteiro.")
TEXTO_EXPIROU = ("Esse texto não está mais guardado (passou do prazo ou o bot reiniciou). "
                 "Abre o .txt que mandei junto com o PDF, ou manda as fotos de novo.")
SEM_TEXTO = "Não encontrei texto nessa página. Pode ser que a foto esteja escura ou tremida."


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
            self.chamar("sendMessage", **params)
        except RuntimeError as e:
            log.error("não consegui enviar mensagem: %s", e)

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
            self.tg.enviar(chat_id, PRIMEIRA_FOTO)

    def fechar(self, chat_id):
        with self.trava:
            lote = self.lotes.pop(chat_id, None)
        if not lote or not lote.fotos:
            return False
        self.tg.enviar(chat_id, msg_processando(len(lote.fotos), self.fila.qsize()))
        self.fila.put((chat_id, lote))
        return True

    def vigiar_janelas(self):
        """Fecha sozinho os lotes que ficaram JANELA segundos sem foto nova."""
        while True:
            time.sleep(2)
            agora = time.monotonic()
            with self.trava:
                vencidos = [c for c, l in self.lotes.items() if l.fotos and agora - l.ultimo >= JANELA]
            for chat_id in vencidos:
                self.fechar(chat_id)

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
            paginas = scanner.processar(fotos, saida, dpi=DPI, qualidade=QUALIDADE, cor=lote.cor,
                                        usar_exif=False, silencioso=True)
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
            self.oferecer_copia(chat_id, [p["texto"] for p in paginas])
        finally:
            tempfile.tempdir = antigo_tmp
            shutil.rmtree(pasta, ignore_errors=True)

    # ------------------------------------------------------- copiar texto
    def guardar_texto(self, chat_id, paginas):
        tid = uuid.uuid4().hex[:10]
        with self.trava:
            self.textos[tid] = {"chat": chat_id, "paginas": paginas, "quando": time.monotonic()}
            while len(self.textos) > MAX_TEXTOS:
                self.textos.popitem(last=False)
        return tid

    def oferecer_copia(self, chat_id, paginas):
        tid = self.guardar_texto(chat_id, paginas)
        teclado = [[{"text": "📋 Copiar todo o texto", "callback_data": f"cp:{tid}:all"}]]
        if len(paginas) > 1:
            botoes = [{"text": f"Pág. {i}", "callback_data": f"cp:{tid}:{i}"}
                      for i in range(1, min(len(paginas), 40) + 1)]
            teclado += [botoes[i:i + 5] for i in range(0, len(botoes), 5)]
        self.tg.enviar(chat_id, COPIAR_CONVITE, teclado=teclado)

    def tratar_botao(self, cb):
        chat_id = (cb.get("message") or {}).get("chat", {}).get("id")
        partes = (cb.get("data") or "").split(":")
        if chat_id is None or len(partes) != 3 or partes[0] != "cp":
            self.tg.responder_botao(cb["id"])
            return
        _, tid, qual = partes
        with self.trava:
            item = self.textos.get(tid)
        vencido = item and time.monotonic() - item["quando"] > TEXTO_HORAS * 3600
        if not item or vencido or item["chat"] != chat_id:
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
            self.mandar_blocos(chat_id, "Texto completo", corpo)
        else:
            n, texto = escolhidas[0]
            self.mandar_blocos(chat_id, f"Página {n}", limpar_texto(texto))

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
