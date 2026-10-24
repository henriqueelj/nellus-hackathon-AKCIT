"""Testes da lógica do servidor do protótipo, com chat FALSO (sem rede, sem chave)."""
import hashlib
import json
import socket
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "prototipo"))
import servidor  # noqa: E402

ORIGINAL = RAIZ / "data" / "rebanho.json"
CHAVE_FALSA = "chave-falsa-0123456789abcdef"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class ChatFalso:
    """Imita o chat do Gemini: responde texto fixo e, se pedido, propõe via tools reais."""

    def __init__(self, tools):
        self.tools, self.recebidas, self.chamadas = tools, [], []

    def send_message(self, texto):
        self.recebidas.append(texto)
        self.chamadas = []
        if "identificação" in texto:
            self.chamadas.append(("processar_identificacao", {"identificacao_id": "ident_001"}))
            self.tools.propor_tarefa("Vacinar contra aftosa", "Lote 3", 5, "2026-10-30")
            return SimpleNamespace(text="BR 121 está com **aftosa vencida**.")
        if "pesei" in texto.lower():
            self.chamadas.append(("propor_manejo", {"animal_id": "BR 123", "tipo": "pesagem",
                                                    "valor": "440"}))
            self.tools.propor_manejo("BR 123", "pesagem", "440")
            return SimpleNamespace(text="Ganho de 8 kg. Confirma?")
        return SimpleNamespace(text="Ok.")


@pytest.fixture
def proto(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    p = servidor.Prototipo(workdir=tmp_path / "work")
    p.chats = []

    def criar_chat(chave, modelo=None):
        c = ChatFalso(p.tools)
        p.chats.append(c)
        return c, "modelo-falso"

    monkeypatch.setattr(p.agent, "criar_chat", criar_chat)
    monkeypatch.setattr(p.agent, "chamadas_do_turno", lambda resp, chat=None: list(chat.chamadas))
    return p


def test_identificacao_com_proposta_e_evento(proto):
    r = proto.identificacao("ident_001")
    assert r["evento"] == {"id": "ident_001", "animalId": "BR 121", "score": 0.91,
                           "decisao": "accepted"}
    assert r["ferramentas"][0]["nome"] == "processar_identificacao"
    assert len(r["propostas"]) == 1 and "Lote 3" in r["propostas"][0]
    assert "ident_001" in proto.chats[0].recebidas[0]
    assert "6 dias" in proto.chats[0].recebidas[0]


def test_identificacao_rejected_tem_animal_nulo(proto):
    assert proto.identificacao("ident_003")["evento"]["animalId"] is None


def test_identificacao_inexistente_e_mensagem_vazia(proto):
    with pytest.raises(servidor.ErroUsuario, match="não encontrada"):
        proto.identificacao("ident_999")
    with pytest.raises(servidor.ErroUsuario):
        proto.mensagem("   ")
    assert proto.chats == []  # nada chegou ao agente


def test_so_propostas_novas_do_turno(proto):
    proto.identificacao("ident_001")  # deixa 1 pendente
    r = proto.mensagem("pesei o BR 123 com 440 kg")
    assert r["propostas"] == ["Pesagem de BR 123: 440 kg"]
    assert "evento" not in r
    assert len(proto.tools.listar_pendentes()) == 2
    assert proto.mensagem("oi")["propostas"] == []


def test_confirmar_grava_so_na_copia(proto):
    antes_original = sha(ORIGINAL)
    antes_copia = sha(proto.copia)
    proto.mensagem("pesei o BR 123 com 440 kg")
    assert sha(proto.copia) == antes_copia  # proposta não grava
    r = proto.decidir("confirmar")
    assert "Pesagem de BR 123: 440 kg" in r["resultado"]
    assert sha(proto.copia) != antes_copia
    assert proto.tools.listar_pendentes() == []
    assert next(a for a in json.loads(proto.copia.read_text())["animals"]
                if a["id"] == "BR 123")["weightKg"] == 440
    assert sha(ORIGINAL) == antes_original


def test_descartar_nao_grava(proto):
    antes = sha(proto.copia)
    proto.mensagem("pesei o BR 123 com 440 kg")
    r = proto.decidir("descartar")
    assert "Nada foi gravado" in r["resultado"][0]
    assert sha(proto.copia) == antes and proto.tools.listar_pendentes() == []


def test_nota_do_sistema_vai_na_proxima_mensagem(proto):
    proto.mensagem("pesei o BR 123 com 440 kg")
    proto.decidir("confirmar")
    proto.mensagem("e agora?")
    chat = proto.chats[0]
    assert chat.recebidas[-1].startswith("[sistema] O produtor CONFIRMOU")
    assert chat.recebidas[-1].endswith("e agora?")
    proto.mensagem("outra")
    assert chat.recebidas[-1] == "outra"  # a nota é entregue uma vez só
    proto.mensagem("pesei de novo")
    proto.decidir("descartar")
    proto.mensagem("depois")
    assert "NÃO confirmou" in chat.recebidas[-1]


def test_decidir_sem_pendentes_e_acao_invalida(proto):
    assert proto.decidir("confirmar")["resultado"] == ["Nada pendente."]
    with pytest.raises(servidor.ErroUsuario):
        proto.decidir("apagar")


def test_reiniciar_restaura_copia_chat_e_pendencias(proto):
    original_copia = sha(proto.copia)
    proto.mensagem("pesei o BR 123 com 440 kg")
    proto.decidir("confirmar")
    proto.mensagem("pesei o BR 123 com 441 kg")  # pendente + nota
    assert sha(proto.copia) != original_copia
    proto.reiniciar()
    assert sha(proto.copia) == original_copia
    assert proto.tools.listar_pendentes() == [] and proto.chat is None and proto.notas == []


def test_original_nunca_muda_e_guarda_restaura(proto):
    antes = sha(ORIGINAL)
    proto.identificacao("ident_001")
    proto.decidir("confirmar")
    proto.reiniciar()
    assert sha(ORIGINAL) == antes
    # a guarda restaura o original se algo o alterasse (simulado numa origem temporária)
    alvo = proto.workdir / "origem.json"
    alvo.write_bytes(ORIGINAL.read_bytes())
    p2 = servidor.Prototipo(dados_origem=alvo, workdir=proto.workdir / "w2")
    alvo.write_text("corrompido")
    p2._guarda()
    assert sha(alvo) == antes


def test_aplicar_pendentes_nao_esta_exposta_ao_llm(proto):
    nomes = {f.__name__ for f in proto.tools.FERRAMENTAS_LLM}
    assert "aplicar_pendentes" not in nomes


# ---------------------------------------------------------------- HTTP
@pytest.fixture
def http(proto):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    srv = ThreadingHTTPServer(("127.0.0.1", porta), servidor.criar_handler(proto, porta))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def chamar(caminho, corpo=None, tipo="application/json", host=None):
        req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}",
                                     data=None if corpo is None else json.dumps(corpo).encode(),
                                     headers={"Content-Type": tipo})
        if host:
            req.add_unredirected_header("Host", host)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    yield chamar
    srv.shutdown()
    srv.server_close()


def test_http_estado_sem_chave(http, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    status, corpo = http("/api/estado")
    assert status == 200 and json.loads(corpo)["tem_chave"] is False


def test_http_estado_com_chave_nao_vaza_valor(http):
    status, corpo = http("/api/estado")
    assert json.loads(corpo)["tem_chave"] is True and CHAVE_FALSA not in corpo


def test_http_pagina_e_fluxo_basico(http):
    status, corpo = http("/")
    assert status == 200 and "Assistente Nellus" in corpo
    status, corpo = http("/api/mensagem", {"texto": "pesei o BR 123 com 440 kg"})
    assert status == 200 and json.loads(corpo)["propostas"] == ["Pesagem de BR 123: 440 kg"]
    status, corpo = http("/api/decidir", {"acao": "confirmar"})
    assert status == 200 and json.loads(corpo)["resultado"]
    assert http("/api/reiniciar", {})[0] == 200


def test_http_erros_nao_vazam_a_chave(http, proto, monkeypatch):
    def quebrar(chave, modelo=None):
        raise RuntimeError(f"falha 429 em https://x/?key={chave} e {chave}")

    monkeypatch.setattr(proto.agent, "criar_chat", quebrar)
    status, corpo = http("/api/mensagem", {"texto": "oi"})
    assert status == 500 and CHAVE_FALSA not in corpo and "[chave removida]" in corpo
    status, corpo = http("/api/identificacao", {"id": "ident_999"})
    assert status == 400 and "não encontrada" in corpo and CHAVE_FALSA not in corpo
    assert http("/api/mensagem", {"texto": ""})[0] == 400


def test_http_exige_json_e_host_local(http):
    assert http("/api/mensagem", {"texto": "oi"}, tipo="text/plain")[0] == 415
    assert http("/api/estado", host="evil.example")[0] == 403


def test_redigir_remove_chave_do_ambiente(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    assert CHAVE_FALSA not in servidor.redigir(f"erro com {CHAVE_FALSA} dentro")
