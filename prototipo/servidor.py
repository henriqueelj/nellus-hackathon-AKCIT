"""Servidor local do protótipo da tela do assistente (só biblioteca padrão).

Conversa com o agente REAL (agent/agent.py: Gemini + function calling) sobre uma CÓPIA dos dados
SINTÉTICOS. O app Flutter NÃO tem esta tela nem esta integração; a identificação (ident_*) é MOCK.

Uso:
    export GEMINI_API_KEY=...        # só do ambiente; nunca vai para a página, arquivos ou logs
    python prototipo/servidor.py     # http://127.0.0.1:8000  (PORTA muda a porta)
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINA = Path(__file__).resolve().parent / "index.html"
LIMITE_CORPO = 64 * 1024
HOJE_PADRAO = "2026-10-24"
PRAZO_VACINA_DIAS = 6

# Padrões montados por partes: este arquivo não pode casar com scripts/verificar_ip.py.
_PADROES_CHAVE = [re.compile("AI" + r"za[0-9A-Za-z_\-]{20,}"),
                  re.compile(r"(?i)\b(?:api[_-]?)?key=[^&\s'\"]+")]


class ErroUsuario(Exception):
    """Entrada inválida (status 400)."""


def redigir(texto) -> str:
    """Remove a chave de qualquer texto de erro (valor do ambiente e padrões conhecidos)."""
    texto = str(texto)
    chave = os.environ.get("GEMINI_API_KEY")
    if chave:
        texto = texto.replace(chave, "[chave removida]")
    for p in _PADROES_CHAVE:
        texto = p.sub("[chave removida]", texto)
    return texto


def _sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _jsonavel(valor):
    return json.loads(json.dumps(valor, default=str))


class Prototipo:
    """Estado e lógica do protótipo. Uma conversa por vez (lock global)."""

    def __init__(self, dados_origem: Path | None = None, workdir: Path | None = None):
        self.origem = Path(dados_origem or RAIZ / "data" / "rebanho.json")
        self._tmp = None if workdir else tempfile.TemporaryDirectory(prefix="nellus_proto_")
        self.workdir = Path(workdir or self._tmp.name)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.copia = self.workdir / "rebanho.json"
        self.saida = self.workdir / "out"
        self._bytes_origem = self.origem.read_bytes()
        # Tools leem estas variáveis a cada chamada; apontar para a CÓPIA antes de usá-las.
        os.environ["NELLUS_DATA"] = str(self.copia)
        os.environ["NELLUS_OUT"] = str(self.saida)
        os.environ.setdefault("NELLUS_HOJE", HOJE_PADRAO)
        sys.path.insert(0, str(RAIZ / "agent"))
        import agent
        import tools
        self.agent, self.tools = agent, tools
        self.lock = threading.Lock()
        self.chat = None
        self.modelo = os.environ.get("GEMINI_MODEL", agent.MODELO_PADRAO)
        self.notas: list[str] = []
        self._restaurar_copia()

    # ------------------------------------------------------------ proteção
    def _restaurar_copia(self):
        shutil.copyfile(self.origem, self.copia)
        shutil.rmtree(self.saida, ignore_errors=True)
        self.tools.PENDENTES.clear()

    def _guarda(self):
        """Se o original mudou, restaura os bytes e avisa. Nunca deveria acontecer."""
        if self.origem.read_bytes() != self._bytes_origem:
            self.origem.write_bytes(self._bytes_origem)
            print("AVISO: data/rebanho.json foi alterado e foi RESTAURADO.", file=sys.stderr)

    # ------------------------------------------------------------ API
    def estado(self) -> dict:
        return {"tem_chave": bool(os.environ.get("GEMINI_API_KEY")), "modelo": self.modelo}

    def identificacao(self, ident_id) -> dict:
        ident_id = str(ident_id or "").strip()
        dados = json.loads(self.copia.read_text(encoding="utf-8"))
        ident = next((i for i in dados.get("identificacoes", [])
                      if i["id"].lower() == ident_id.lower()), None)
        if not ident:
            raise ErroUsuario(f"Identificação '{ident_id}' não encontrada.")
        texto = (f"O celular acabou de registrar a identificação {ident['id']}. Analise e diga ao "
                 "produtor o que ele precisa saber e fazer agora. Se houver vacina pendente, "
                 f"proponha a tarefa de vacinação do lote com prazo de {PRAZO_VACINA_DIAS} dias.")
        r = self._turno(texto)
        r["evento"] = {"id": ident["id"], "animalId": ident.get("animalId"),
                       "score": ident["score"], "decisao": ident["decisao"]}
        return r

    def mensagem(self, texto) -> dict:
        texto = str(texto or "").strip()
        if not texto:
            raise ErroUsuario("Mensagem vazia.")
        return self._turno(texto)

    def decidir(self, acao) -> dict:
        if acao not in ("confirmar", "descartar"):
            raise ErroUsuario("acao deve ser 'confirmar' ou 'descartar'.")
        pend = self.tools.listar_pendentes()
        if not pend:
            return {"resultado": ["Nada pendente."]}
        resumos = "; ".join(p["resumo"] for p in pend)
        if acao == "confirmar":
            res = self.tools.aplicar_pendentes()
            self._guarda()
            linhas = list(res.get("itens", [])) + [f"Falha: {f}" for f in res.get("falhas", [])]
            if res.get("erro"):
                linhas.append(f"Erro: {res['erro']}")
            self.notas.append(f"[sistema] O produtor CONFIRMOU: {resumos}. "
                              f"Resultado da gravação: {res}.")
            return {"resultado": linhas or ["Nada foi aplicado."]}
        n = self.tools.descartar_pendentes()
        self.notas.append(f"[sistema] O produtor NÃO confirmou; {n} proposta(s) descartada(s) "
                          f"({resumos}), nada foi gravado.")
        return {"resultado": [f"Descartado. Nada foi gravado ({n} proposta(s))."]}

    def reiniciar(self) -> dict:
        self._restaurar_copia()
        self.chat = None
        self.notas.clear()
        self._guarda()
        return {"ok": True}

    # ------------------------------------------------------------ núcleo
    def _turno(self, texto: str) -> dict:
        if self.chat is None:
            chave = os.environ.get("GEMINI_API_KEY")
            if not chave:
                raise RuntimeError("GEMINI_API_KEY ausente no ambiente do servidor.")
            self.chat, self.modelo = self.agent.criar_chat(chave)
        mensagem = "\n".join(self.notas + [texto]) if self.notas else texto
        antes = len(self.tools.PENDENTES)
        resp = self.chat.send_message(mensagem)
        self.notas.clear()  # só depois de o agente receber a nota
        chamadas = self.agent.chamadas_do_turno(resp, self.chat)
        self._guarda()
        descrever = getattr(self.tools, "descrever", None)
        novas = self.tools.PENDENTES[antes:]
        return {"resposta": resp.text or "(sem texto)",
                "ferramentas": [{"nome": n, "args": _jsonavel(a)} for n, a in chamadas],
                "propostas": [descrever(p) if descrever else p["resumo"] for p in novas]}


def criar_handler(proto: Prototipo, porta: int):
    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}"}
    rotas = {"/api/identificacao": lambda b: proto.identificacao(b.get("id")),
             "/api/mensagem": lambda b: proto.mensagem(b.get("texto")),
             "/api/decidir": lambda b: proto.decidir(b.get("acao")),
             "/api/reiniciar": lambda b: proto.reiniciar()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, formato, *args):  # só método e caminho; nunca corpo
            print(f"{self.command} {self.path.split('?')[0]}", file=sys.stderr)

        def _enviar(self, status, corpo: bytes, tipo="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, status, obj):
            self._enviar(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") in hosts:
                return True
            self._json(403, {"erro": "Host não permitido."})
            return False

        def do_GET(self):
            if not self._host_ok():
                return
            caminho = self.path.split("?")[0]
            if caminho in ("/", "/index.html"):
                self._enviar(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
            elif caminho == "/api/estado":
                self._json(200, proto.estado())
            else:
                self._json(404, {"erro": "Não encontrado."})

        def do_POST(self):
            if not self._host_ok():
                return
            rota = rotas.get(self.path.split("?")[0])
            if rota is None:
                return self._json(404, {"erro": "Não encontrado."})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"erro": "Use Content-Type: application/json."})
            try:
                tamanho = int(self.headers.get("Content-Length") or 0)
                if tamanho > LIMITE_CORPO:
                    return self._json(413, {"erro": "Corpo grande demais."})
                corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                if not isinstance(corpo, dict):
                    raise ValueError
            except ValueError:
                return self._json(400, {"erro": "JSON inválido."})
            try:
                with proto.lock:
                    resultado = rota(corpo)
                self._json(200, resultado)
            except ErroUsuario as e:
                self._json(400, {"erro": str(e)})
            except Exception as e:  # Gemini/rede/cota: mensagem curta, sem a chave
                self._json(500, {"erro": redigir(f"{type(e).__name__}: {e}")[:300]})

    return Handler


def main():
    porta = int(os.environ.get("PORTA", "8000"))
    proto = Prototipo()
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), criar_handler(proto, porta))
    estado = "chave presente" if proto.estado()["tem_chave"] else "SEM GEMINI_API_KEY"
    print(f"Protótipo em http://127.0.0.1:{porta} | {estado} | dados SINTÉTICOS (cópia temporária)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
