"""Camada A: tools contra o dataset determinístico (NELLUS_HOJE=2026-10-24). Sem LLM, offline.
Valores esperados congelados a partir de data/rebanho.json (dados SINTÉTICOS)."""
import hashlib
import json

import pytest

import tools


def ids(lista, campo="id"):
    return [x[campo] for x in lista]


def test_buscar_animais():
    assert tools.buscar_animais()["total"] == 24
    assert tools.buscar_animais(categoria="vaca")["total"] == 6
    assert ids(tools.buscar_animais(lote="2")["animais"]) == [f"BR {n}" for n in range(109, 117)]
    assert ids(tools.buscar_animais(sem_id_visual=True)["animais"]) == [
        "BR 107", "BR 112", "BR 120", "BR 124"]
    assert ids(tools.buscar_animais(texto="105")["animais"]) == ["BR 105"]
    assert tools.buscar_animais(lote="9")["ok"] is False


@pytest.mark.parametrize("entrada", ["BR 105", "br105", " Br  105 "])
def test_brinco_normalizado(entrada):
    r = tools.historico_animal(entrada)
    assert r["ok"] and r["animal"]["id"] == "BR 105" and r["animal"]["peso_kg"] == 416


def test_historico():
    r = tools.historico_animal("BR 101")
    assert [e["tipo"] for e in r["eventos"]] == ["registration", "weight", "vaccine", "weight", "weight"]
    assert tools.historico_animal("BR 999")["ok"] is False
    t110 = [e for e in tools.historico_animal("BR 110")["eventos"] if e["tipo"] == "transfer"]
    assert t110 == [{"data": "2026-10-04", "tipo": "transfer", "titulo": "Transferencia registrada",
                     "detalhe": "De Lote 1 para Lote 2"}]


def test_aftosa_lote3():
    r = tools.animais_sem_vacina("Aftosa", "3")
    assert {a["id"]: a["situacao"] for a in r["animais"]} == {
        "BR 120": "vencida", "BR 121": "vencida", "BR 122": "vencida",
        "BR 123": "nunca_vacinado", "BR 124": "nunca_vacinado"}
    assert {a["dias_vencida"] for a in r["animais"] if a["situacao"] == "vencida"} == {30}


def test_aftosa_lotes_1_e_2_sem_pendencias():
    assert tools.animais_sem_vacina("Aftosa", "Lote 1")["total"] == 0
    assert tools.animais_sem_vacina("aftosa", "2")["total"] == 0
    assert tools.animais_sem_vacina("Aftosa")["total"] == 5


def test_aftosa_validade_configuravel():
    # BR 101-116 vacinados há 60 dias, 117-119 há 45: com validade de 50 dias, 101-116 vencem
    assert tools.animais_sem_vacina("Aftosa", "1", dias_validade=50)["total"] == 8


def test_ganho_peso():
    assert tools.ganho_peso_lote("1")["ganho_medio_kg"] == 17.75
    r = tools.ganho_peso_lote("2")
    assert (r["ganho_total_kg"], r["ganho_medio_kg"], r["animais_com_dados"]) == (144.0, 18.0, 8)
    assert tools.ganho_peso_lote("3")["ganho_medio_kg"] == 18.25
    assert tools.ganho_peso_lote("2", 90)["ganho_medio_kg"] == 34.5
    assert tools.ganho_peso_lote("2", 10)["ganho_medio_kg"] is None
    assert tools.ganho_peso_lote("9")["ok"] is False


def test_auditar_cadastro():
    r = tools.auditar_cadastro()
    assert r["sem_id_visual"] == ["BR 107", "BR 112", "BR 120", "BR 124"]
    assert r["lotes_sem_area"] == ["Lote 2"]
    assert r["sisbov_vazio"]["total"] == 24


def test_identificacoes():
    assert ids(tools.identificacoes_recentes()["identificacoes"]) == [
        "ident_001", "ident_002", "ident_003", "ident_004"]
    assert tools.identificacoes_recentes()["origem"].startswith("MOCK")


def alertas(i):
    return " | ".join(tools.processar_identificacao(i)["alertas"])


def test_processar_identificacao():
    assert "BR 121" in alertas("ident_001") and "VENCIDA" in alertas("ident_001")
    assert "CONFUSÃO" in alertas("ident_002") and "BR 109" in alertas("ident_002")
    r3 = tools.processar_identificacao("ident_003")
    assert r3["reconhecido"] is False and r3["animal"] is None and "NÃO reconhecido" in alertas("ident_003")
    assert tools.processar_identificacao("ident_004")["alertas"] == []
    assert tools.processar_identificacao("ident_999")["ok"] is False


def test_dossie(tmp_path):
    r = tools.gerar_dossie("BR 121")
    texto = open(r["arquivo"], encoding="utf-8").read()
    assert r["pendencias"] == ["SISBOV em branco", "Aftosa vencida há 30 dias"]
    assert "SINTÉTICOS" in texto and "SISBOV: (em branco)" in texto
    assert "| 2026-10-21 | 404 |" in texto
    assert tools.gerar_dossie("BR 999")["ok"] is False


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_propostas_nao_gravam(ambiente):
    antes = sha(ambiente)
    assert tools.propor_manejo("BR 123", "pesagem", "432")["ok"]
    assert tools.propor_manejo("BR 101", "vacina", "2 ml", "Aftosa")["ok"]
    assert tools.propor_manejo("BR 101", "transferencia", "Lote 3")["ok"]
    assert tools.propor_tarefa("Pesar lote", "1", 8, "2026-11-10")["ok"]
    assert len(tools.PENDENTES) == 4
    assert sha(ambiente) == antes


@pytest.mark.parametrize("args", [
    ("BR 999", "pesagem", "400"), ("BR 101", "pesagem", "abc"), ("BR 101", "pesagem", "-5"),
    ("BR 101", "venda", "1"), ("BR 101", "transferencia", "Lote 9"),
    ("BR 101", "transferencia", "Lote 1"), ("BR 101", "vacina", "", "")])
def test_propostas_invalidas(args):
    assert tools.propor_manejo(*args)["ok"] is False
    assert tools.PENDENTES == []


def test_tarefa_invalida():
    assert tools.propor_tarefa("x", "9", 1, "2026-11-10")["ok"] is False
    assert tools.propor_tarefa("x", "1", 1, "10/11")["ok"] is False
    assert tools.propor_tarefa("x", "1", 0, "2026-11-10")["ok"] is False


def test_aplicar_pendentes_grava_so_apos_chamada(ambiente):
    tools.propor_manejo("BR 123", "pesagem", "440")
    tools.propor_manejo("BR 101", "transferencia", "Lote 3")
    r = tools.aplicar_pendentes()
    assert r["ok"] and r["aplicados"] == 2 and tools.PENDENTES == []
    d = json.loads(ambiente.read_text())
    a123 = next(a for a in d["animals"] if a["id"] == "BR 123")
    assert (a123["weightKg"], a123["gain30d"]) == (440, 8)
    assert next(a for a in d["animals"] if a["id"] == "BR 101")["lot"] == "Lote 3"


def test_aplicar_nao_exposta_ao_llm():
    nomes = {f.__name__ for f in tools.FERRAMENTAS_LLM}
    assert not nomes & {"aplicar_pendentes", "listar_pendentes", "descartar_pendentes"}
    assert {"propor_manejo", "propor_tarefa"} <= nomes


def test_tools_nao_levantam_excecao_sem_dados(monkeypatch, tmp_path):
    monkeypatch.setenv("NELLUS_DATA", str(tmp_path / "nao_existe.json"))
    assert tools.auditar_cadastro()["ok"] is False
    assert tools.historico_animal("BR 101")["ok"] is False


def test_ident_003_rejected_tem_animal_id_nulo():
    ident = next(i for i in tools.identificacoes_recentes()["identificacoes"] if i["id"] == "ident_003")
    assert ident["animalId"] is None and ident["decisao"] == "rejected" and ident["score"] == 0.52
    r = tools.processar_identificacao("ident_003")
    assert r["reconhecido"] is False and r["animal"] is None
    assert "BR 103" not in json.dumps(r, ensure_ascii=False)  # não vaza o 2º candidato


def test_animal_id_nulo_nao_levanta_excecao(ambiente):
    d = json.loads(ambiente.read_text())
    d["identificacoes"].append({"id": "ident_nulo", "data": "2026-10-23T10:00:00", "animalId": None,
                                "score": 0.9, "decisao": "accepted"})
    ambiente.write_text(json.dumps(d))
    r = tools.processar_identificacao("ident_nulo")
    assert r["ok"] is False and "animal" in r["erro"]
    assert tools.identificacoes_recentes()["total"] == 5
