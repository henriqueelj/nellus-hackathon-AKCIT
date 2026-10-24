import json

import tools


def test_totais_e_ordem_por_severidade():
    r = tools.auditoria_priorizada()
    assert r["ok"] and r["total"] == 11
    assert r["por_severidade"] == {"CRITICA": 5, "ALTA": 4, "MEDIA": 1, "BAIXA": 1}
    ordem = [i["severidade"] for i in r["itens"]]
    assert ordem == ["CRITICA"] * 5 + ["ALTA"] * 4 + ["MEDIA", "BAIXA"]
    assert [i["id"] for i in r["itens"]] == [f"ACH-{n:03d}" for n in range(1, 12)]


def test_criticos_nunca_antes_de_vencida_por_dias_de_atraso():
    itens = tools.auditoria_priorizada()["itens"]
    criticos = [(i["alvo"], i["descricao"], i["dias_atraso"]) for i in itens[:5]]
    assert criticos == [("BR 123", "Aftosa nunca aplicada", 120),
                        ("BR 124", "Aftosa nunca aplicada", 120),
                        ("BR 120", "Aftosa vencida", 30),
                        ("BR 121", "Aftosa vencida", 30),
                        ("BR 122", "Aftosa vencida", 30)]
    assert itens[2]["evidencia"]["ultima_aplicacao"] == "2026-03-28"


def test_alta_sem_id_visual_media_lote_baixa_agrupada():
    itens = tools.auditoria_priorizada()["itens"]
    alta = sorted(i["alvo"] for i in itens if i["severidade"] == "ALTA")
    assert alta == ["BR 107", "BR 112", "BR 120", "BR 124"]
    media = [i for i in itens if i["severidade"] == "MEDIA"]
    assert [m["alvo"] for m in media] == ["Lote 2"]
    baixa = [i for i in itens if i["severidade"] == "BAIXA"]
    assert len(baixa) == 1
    assert baixa[0]["evidencia"]["animais_afetados"] == 24
    assert len(baixa[0]["evidencia"]["exemplos"]) == 5


def test_cada_item_tem_campos_obrigatorios():
    for i in tools.auditoria_priorizada()["itens"]:
        for campo in ("id", "severidade", "alvo", "descricao", "evidencia", "acao_sugerida"):
            assert i[campo], campo


def test_filtro_por_lote():
    r = tools.auditoria_priorizada("3")
    alvos = {i["alvo"] for i in r["itens"] if i["severidade"] != "BAIXA"}
    assert alvos == {"BR 120", "BR 121", "BR 122", "BR 123", "BR 124"}
    assert r["por_severidade"]["MEDIA"] == 0  # Lote 3 tem área
    assert next(i for i in r["itens"] if i["severidade"] == "BAIXA")["evidencia"][
        "animais_afetados"] == 8
    assert tools.auditoria_priorizada("2")["por_severidade"]["MEDIA"] == 1


def test_lote_inexistente_devolve_erro():
    r = tools.auditoria_priorizada("9")
    assert r["ok"] is False and "não encontrado" in r["erro"]


def test_nao_grava_e_sem_sisbov_vazio_nao_gera_baixa(ambiente):
    antes = ambiente.read_bytes()
    tools.auditoria_priorizada()
    assert ambiente.read_bytes() == antes
    d = json.loads(antes)
    for a in d["animals"]:
        a["sisbov"] = "123"
    ambiente.write_text(json.dumps(d))
    assert tools.auditoria_priorizada()["por_severidade"]["BAIXA"] == 0


def test_registrada_para_o_llm():
    assert tools.auditoria_priorizada in tools.FERRAMENTAS_LLM
