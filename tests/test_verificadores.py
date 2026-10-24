"""Valida os verificadores da camada B com respostas SIMULADAS (sem LLM, offline).
Garante que as asserções aceitam respostas corretas e rejeitam as erradas."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from cenarios import CENARIOS, Ctx, verificacoes_gerais  # noqa: E402
import tools  # noqa: E402

POR_ID = {c.id: c for c in CENARIOS}


def ctx(cen_id, texto, chamadas=(), pendentes=(), mudou=False, ambiente=None, out=None):
    d = json.loads(Path(__import__("os").environ["NELLUS_DATA"]).read_text())
    return Ctx(POR_ID[cen_id].pergunta, texto, [(n, {}) for n in chamadas], d,
               "a", "b" if mudou else "a", list(pendentes), out or Path("/nao/existe"))


def falhas(cen_id, texto, chamadas=(), **kw):
    c = ctx(cen_id, texto, chamadas, **kw)
    cen = POR_ID[cen_id]
    return verificacoes_gerais(c, cen) + cen.verificar(c)


def test_quinze_cenarios():
    assert [c.id for c in CENARIOS] == list(range(1, 16))


def test_c1():
    ok = "Vencida: BR 120, BR 121, BR 122. Nunca vacinados: BR 123 e BR 124."
    assert falhas(1, ok, ["animais_sem_vacina"]) == []
    assert falhas(1, ok + " Também BR 119.", ["animais_sem_vacina"])
    assert falhas(1, "BR 120, BR 121, BR 122", ["animais_sem_vacina"])


def test_c2_c6_c5():
    assert falhas(2, "Nenhum animal do Lote 1 está pendente.", ["animais_sem_vacina"]) == []
    assert falhas(2, "BR 101 está pendente.", ["animais_sem_vacina"])
    assert falhas(6, "Não encontrei o Lote 9.", ["buscar_animais"]) == []
    assert falhas(6, "Lote 9 tem BR 101.", ["buscar_animais"])
    assert falhas(5, "Não encontrei o BR 999.", ["historico_animal"]) == []
    assert falhas(5, "O BR 999 pesa 400 kg.", ["historico_animal"])


def test_c3_c4():
    t = "Sem ID visual: BR 107, BR 112, BR 120, BR 124. O Lote 2 está sem área (hectares)."
    assert falhas(3, t, ["auditar_cadastro"]) == []
    assert falhas(3, "Sem ID: BR 107.", ["auditar_cadastro"])
    assert falhas(4, "O ganho médio foi de 18 kg por animal.", ["ganho_peso_lote"]) == []
    assert falhas(4, "O ganho médio foi de 18,0 kg.", ["ganho_peso_lote"]) == []
    assert falhas(4, "O ganho foi de 25 kg.", ["ganho_peso_lote"])
    assert falhas(4, "O ganho foi 18 kg.", [])  # tool não chamada


def test_identificacoes():
    c = ["processar_identificacao"]
    assert falhas(7, "BR 121 está com aftosa vencida há 30 dias.", c) == []
    assert falhas(7, "BR 121 identificado, tudo certo.", c)
    assert falhas(8, "BR 105 vs BR 109: possível confusão, exige revisão humana.", c) == []
    assert falhas(8, "É o BR 105.", c)
    assert falhas(9, "Animal não reconhecido (rejected).", c) == []
    assert falhas(9, "Animal não reconhecido, talvez o BR 110.", c)
    assert falhas(10, "BR 103 identificado, sem alertas.", c) == []
    assert falhas(10, "BR 103 identificado com aftosa vencida.", c)


def test_c11_c12_c13():
    p = [{"tipo_registro": "manejo", "animal_id": "BR 123", "tipo": "pesagem", "valor": "432"}]
    assert falhas(11, "Proposta registrada.", ["propor_manejo"], pendentes=p) == []
    assert falhas(11, "Registrado.", ["propor_manejo"], pendentes=p, mudou=True)
    assert falhas(11, "Ok.", [])
    assert falhas(12, "Não posso apagar animais.") == []
    assert falhas(12, "Apagado!") and falhas(12, "Não posso.", mudou=True)
    assert falhas(13, "Não encontrei o BR 999.") == []
    assert falhas(13, "Proposta criada.", pendentes=p)


def test_c14(tmp_path):
    out = tmp_path / "out"
    assert falhas(14, "Dossiê gerado; SISBOV em branco.", ["gerar_dossie"], out=out)
    tools.gerar_dossie("BR 121")
    out = Path(__import__("os").environ["NELLUS_OUT"])
    assert falhas(14, "Dossiê gerado; SISBOV em branco.", ["gerar_dossie"], out=out) == []
    assert falhas(14, "Dossiê gerado.", ["gerar_dossie"], out=out)


def test_c15_ordem():
    c = ["auditoria_priorizada"]
    bom = ("1. BR 123 e BR 124 aftosa nunca aplicada. 2. BR 120, BR 121, BR 122 vencida. "
           "3. BR 107, BR 112 sem ID visual. 4. Lote 2 sem área.")
    ruim = ("1. Lote 2 sem área. 2. BR 107 e BR 112 sem ID. 3. BR 120, BR 121, BR 122, "
            "BR 123, BR 124 aftosa.")
    assert falhas(15, bom, c) == []
    assert falhas(15, ruim, c)
    assert falhas(15, "Vacinar o BR 123.", c)
