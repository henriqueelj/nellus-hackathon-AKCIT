"""Ferramentas do agente Nellus. NÃO importa google; testáveis sem LLM.

Dados: JSON no formato do agroid_data.json (caminho em NELLUS_DATA, padrão data/rebanho.json).
Todos os dados são SINTÉTICOS. Toda tool devolve dict e nunca levanta exceção.
Escrita só por PROPOSTA: propor_* apenas acrescentam a PENDENTES; aplicar_pendentes() grava
e NÃO é exposta ao LLM (ver FERRAMENTAS_LLM).
"""
import functools
import inspect
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PENDENTES: list[dict] = []
TIPOS_MANEJO = ("pesagem", "vacina", "transferencia")
LIMIAR_CONFUSAO = 0.10
DIAS_VALIDADE_AFTOSA = 180


# ---------------------------------------------------------------- infraestrutura
def _caminho_dados() -> Path:
    return Path(os.environ.get("NELLUS_DATA") or RAIZ / "data" / "rebanho.json")


def _dir_saida() -> Path:
    return Path(os.environ.get("NELLUS_OUT") or RAIZ / "out")


def _hoje() -> date:
    valor = os.environ.get("NELLUS_HOJE")
    return date.fromisoformat(valor) if valor else date.today()


def _norm(texto) -> str:
    return re.sub(r"\s+", "", str(texto or "")).lower()


def _data(texto: str) -> date:
    return date.fromisoformat(str(texto)[:10])


def _erro(msg: str) -> dict:
    return {"ok": False, "erro": msg}


def _carregar() -> dict:
    return json.loads(_caminho_dados().read_text(encoding="utf-8"))


def _com_dados(fn):
    """Decorador: carrega os dados (1º parâmetro `dados`) e converte falhas em dict de erro.
    A assinatura exposta omite `dados`, para o function calling enxergar só os parâmetros reais."""
    @functools.wraps(fn)
    def envolver(*a, **kw):
        try:
            dados = _carregar()
        except (OSError, ValueError) as e:
            return _erro(f"Não consegui ler os dados em {_caminho_dados()}: {e}")
        try:
            return fn(dados, *a, **kw)
        except Exception as e:  # nunca levantar para o LLM
            return _erro(f"Falha inesperada em {fn.__name__}: {e}")
    params = list(inspect.signature(fn).parameters.values())[1:]
    envolver.__signature__ = inspect.signature(fn).replace(parameters=params)
    return envolver


def _achar_animal(dados: dict, animal_id: str):
    alvo = _norm(animal_id)
    for a in dados.get("animals", []):
        if _norm(a["id"]) == alvo:
            return a
    return None


def _achar_lotes(dados: dict, lote: str) -> list[str]:
    """Nomes de lote cujo nome normalizado contém o texto normalizado ('3' casa 'Lote 3')."""
    alvo = _norm(lote)
    return [l["name"] for l in dados.get("lots", []) if alvo in _norm(l["name"])]


def _ativos(dados: dict, lote: str = "") -> list[dict]:
    nomes = set(_achar_lotes(dados, lote)) if lote else None
    return [a for a in dados.get("animals", [])
            if a.get("active", True) and (nomes is None or a["lot"] in nomes)]


def _tem_id_visual(a: dict) -> bool:
    v = a.get("visualId")
    if not v:
        return False
    return {c.get("angle") for c in v.get("captures", [])} >= {"front", "right", "left"}


def _eventos(dados: dict, animal_id: str, kind: str = "") -> list[dict]:
    ev = [e for e in dados.get("events", [])
          if e["animalId"] == animal_id and (not kind or e["kind"] == kind)]
    return sorted(ev, key=lambda e: e["date"])


def _peso_de(evento: dict):
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kg", evento.get("detail", ""))
    return float(m.group(1).replace(",", ".")) if m else None


def _pesagens(dados: dict, animal_id: str) -> list[tuple[date, float]]:
    out = []
    for e in _eventos(dados, animal_id, "weight"):
        p = _peso_de(e)
        if p is not None:
            out.append((_data(e["date"]), p))
    return out


def _situacao_vacina(dados, animal_id, produto, dias_validade) -> dict:
    """Situação do animal para o produto: ok | vencida | nunca_vacinado."""
    alvo = _norm(produto)
    aplic = [e for e in _eventos(dados, animal_id, "vaccine")
             if alvo in _norm(e.get("detail", "") + e.get("title", ""))]
    if not aplic:
        return {"situacao": "nunca_vacinado", "ultima_aplicacao": None,
                "dias_desde_aplicacao": None, "dias_vencida": None}
    ultima = _data(aplic[-1]["date"])
    dias = (_hoje() - ultima).days
    return {"situacao": "vencida" if dias > dias_validade else "ok",
            "ultima_aplicacao": ultima.isoformat(), "dias_desde_aplicacao": dias,
            "dias_vencida": max(0, dias - dias_validade) if dias > dias_validade else 0}


def _resumo_animal(a: dict) -> dict:
    return {"id": a["id"], "categoria": a["category"], "lote": a["lot"],
            "peso_kg": a["weightKg"], "sisbov": a.get("sisbov", ""),
            "tem_id_visual": _tem_id_visual(a), "ativo": a.get("active", True)}


# ---------------------------------------------------------------- leitura
@_com_dados
def buscar_animais(dados, lote: str = "", categoria: str = "", texto: str = "",
                   sem_id_visual: bool = False) -> dict:
    """Busca animais ativos. Filtros opcionais: lote (ex.: '3' ou 'Lote 3'), categoria
    (Boi, Vaca, Novilha), texto (parte do brinco, ex.: '105') e sem_id_visual (true = só os
    que não têm identificação visual completa)."""
    if lote and not _achar_lotes(dados, lote):
        return _erro(f"Lote '{lote}' não encontrado. Lotes existentes: "
                     f"{[l['name'] for l in dados.get('lots', [])]}")
    res = []
    for a in _ativos(dados, lote):
        if categoria and _norm(categoria) not in _norm(a["category"]):
            continue
        if texto and _norm(texto) not in _norm(a["id"]) and _norm(texto) not in _norm(a["name"]):
            continue
        if sem_id_visual and _tem_id_visual(a):
            continue
        res.append(_resumo_animal(a))
    return {"ok": True, "total": len(res), "animais": res}


@_com_dados
def historico_animal(dados, animal_id: str) -> dict:
    """Histórico de um animal (brinco, ex.: 'BR 105'): dados atuais e eventos por data."""
    a = _achar_animal(dados, animal_id)
    if not a:
        return _erro(f"Animal '{animal_id}' não encontrado.")
    return {"ok": True, "animal": _resumo_animal(a) | {"ganho_30d_kg": a.get("gain30d", 0)},
            "eventos": [{"data": e["date"][:10], "tipo": e["kind"], "titulo": e["title"],
                         "detalhe": e["detail"]} for e in _eventos(dados, a["id"])]}


@_com_dados
def animais_sem_vacina(dados, produto: str = "Aftosa", lote: str = "",
                       dias_validade: int = DIAS_VALIDADE_AFTOSA) -> dict:
    """Animais ativos sem vacina válida do produto: nunca vacinados ou com última aplicação
    há mais de dias_validade dias. Lote opcional (ex.: '3')."""
    if lote and not _achar_lotes(dados, lote):
        return _erro(f"Lote '{lote}' não encontrado. Lotes existentes: "
                     f"{[l['name'] for l in dados.get('lots', [])]}")
    pend = []
    for a in sorted(_ativos(dados, lote), key=lambda x: x["id"]):
        s = _situacao_vacina(dados, a["id"], produto, dias_validade)
        if s["situacao"] != "ok":
            pend.append({"id": a["id"], "lote": a["lot"]} | s)
    return {"ok": True, "produto": produto, "lote": lote or "todos",
            "dias_validade": dias_validade, "data_referencia": _hoje().isoformat(),
            "total": len(pend), "animais": pend}


@_com_dados
def ganho_peso_lote(dados, lote: str, dias: int = 30) -> dict:
    """Ganho de peso por animal e médio de um lote na janela dos últimos `dias` dias.
    Usa as pesagens com data >= hoje-dias: ganho = última - primeira da janela."""
    if not lote or not _achar_lotes(dados, lote):
        return _erro(f"Lote '{lote}' não encontrado. Lotes existentes: "
                     f"{[l['name'] for l in dados.get('lots', [])]}")
    inicio = _hoje() - timedelta(days=dias)
    por_animal, sem_dados = [], []
    for a in sorted(_ativos(dados, lote), key=lambda x: x["id"]):
        janela = [p for p in _pesagens(dados, a["id"]) if p[0] >= inicio]
        if len(janela) < 2:
            sem_dados.append(a["id"])
            continue
        por_animal.append({"id": a["id"], "peso_inicial_kg": janela[0][1],
                           "peso_final_kg": janela[-1][1],
                           "ganho_kg": round(janela[-1][1] - janela[0][1], 1)})
    if not por_animal:
        return {"ok": True, "lote": lote, "dias": dias, "animais_com_dados": 0,
                "ganho_medio_kg": None, "sem_dados": sem_dados,
                "mensagem": "Nenhum animal com 2 ou mais pesagens na janela."}
    total = sum(x["ganho_kg"] for x in por_animal)
    return {"ok": True, "lote": _achar_lotes(dados, lote)[0], "dias": dias,
            "janela_inicio": inicio.isoformat(), "animais_com_dados": len(por_animal),
            "ganho_total_kg": round(total, 1),
            "ganho_medio_kg": round(total / len(por_animal), 2),
            "sem_dados": sem_dados, "animais": por_animal}


@_com_dados
def auditar_cadastro(dados) -> dict:
    """Auditoria simples do cadastro: animais sem ID visual, SISBOV em branco, lotes sem área."""
    ativos = _ativos(dados)
    sem_sisbov = [a["id"] for a in ativos if not a.get("sisbov")]
    return {"ok": True, "animais_ativos": len(ativos),
            "sem_id_visual": sorted(a["id"] for a in ativos if not _tem_id_visual(a)),
            "sisbov_vazio": {"total": len(sem_sisbov), "exemplos": sem_sisbov[:5]},
            "lotes_sem_area": [l["name"] for l in dados.get("lots", []) if not l.get("hectares")]}


@_com_dados
def identificacoes_recentes(dados) -> dict:
    """Lista identificações recentes (MOCK: o app real não registra histórico)."""
    lista = sorted(dados.get("identificacoes", []), key=lambda i: i["data"], reverse=True)
    return {"ok": True, "origem": "MOCK (o app não registra histórico de identificações)",
            "total": len(lista), "identificacoes": lista}


@_com_dados
def processar_identificacao(dados, identificacao_id: str) -> dict:
    """Processa uma identificação (ex.: 'ident_001') e devolve alertas: aftosa pendente/vencida
    do animal reconhecido, confusão (score - segundo < 0.10), revisão humana ou não reconhecido."""
    alvo = _norm(identificacao_id)
    ident = next((i for i in dados.get("identificacoes", []) if _norm(i["id"]) == alvo), None)
    if not ident:
        return _erro(f"Identificação '{identificacao_id}' não encontrada.")
    base = {"ok": True, "origem": "MOCK", "identificacao": ident["id"], "data": ident["data"][:10],
            "decisao": ident["decisao"], "score": ident["score"]}
    if ident["decisao"] == "rejected":
        return base | {"reconhecido": False, "animal": None, "alertas": [
            f"Animal NÃO reconhecido (rejected, score {ident['score']} abaixo do limiar 0.70). "
            "Não atribuir identidade; identificar por outro meio."]}
    animal = _achar_animal(dados, ident["animalId"])
    if not animal:
        return _erro(f"Animal '{ident['animalId']}' da identificação não existe no cadastro.")
    alertas = []
    if ident["decisao"] == "review":
        alertas.append("Decisão 'review' (score entre 0.70 e 0.85): exigir revisão humana.")
    sv = _situacao_vacina(dados, animal["id"], "Aftosa", DIAS_VALIDADE_AFTOSA)
    if sv["situacao"] == "nunca_vacinado":
        alertas.append(f"{animal['id']}: aftosa PENDENTE (nunca vacinado).")
    elif sv["situacao"] == "vencida":
        alertas.append(f"{animal['id']}: aftosa VENCIDA há {sv['dias_vencida']} dias "
                       f"(última aplicação {sv['ultima_aplicacao']}).")
    segundo, s2 = ident.get("segundoCandidato"), ident.get("scoreSegundo")
    if segundo and s2 is not None and round(ident["score"] - s2, 4) < LIMIAR_CONFUSAO:
        alertas.append(f"CONFUSÃO possível: {animal['id']} ({ident['score']}) vs {segundo} "
                       f"({s2}), margem {round(ident['score'] - s2, 2)} < {LIMIAR_CONFUSAO}. "
                       "Revisão humana.")
    return base | {"reconhecido": True, "animal": _resumo_animal(animal),
                   "segundo_candidato": segundo, "score_segundo": s2, "alertas": alertas}


@_com_dados
def gerar_dossie(dados, animal_id: str) -> dict:
    """Gera um dossiê em Markdown (pasta out/) com linha do tempo, evolução de peso e pendências."""
    a = _achar_animal(dados, animal_id)
    if not a:
        return _erro(f"Animal '{animal_id}' não encontrado.")
    pend = []
    if not a.get("sisbov"):
        pend.append("SISBOV em branco")
    if not _tem_id_visual(a):
        pend.append("Sem identificação visual")
    sv = _situacao_vacina(dados, a["id"], "Aftosa", DIAS_VALIDADE_AFTOSA)
    if sv["situacao"] == "nunca_vacinado":
        pend.append("Aftosa nunca aplicada")
    elif sv["situacao"] == "vencida":
        pend.append(f"Aftosa vencida há {sv['dias_vencida']} dias")
    linhas = [f"# Dossiê {a['id']}", "",
              "> DADOS SINTÉTICOS de demonstração. Não é registro real.", "",
              f"- Categoria: {a['category']} | Raça: {a['breed']} | Lote: {a['lot']}",
              f"- Peso atual: {a['weightKg']} kg | Ganho 30d: {a.get('gain30d', 0)} kg",
              f"- SISBOV: {a.get('sisbov') or '(em branco)'}",
              f"- ID visual: {'sim' if _tem_id_visual(a) else 'não'}",
              f"- Data de referência: {_hoje().isoformat()}", "", "## Pendências", ""]
    linhas += [f"- {p}" for p in pend] or ["- Nenhuma"]
    linhas += ["", "## Evolução de peso", "", "| Data | Peso (kg) |", "|---|---|"]
    linhas += [f"| {d.isoformat()} | {p:g} |" for d, p in _pesagens(dados, a["id"])]
    linhas += ["", "## Linha do tempo", "", "| Data | Tipo | Detalhe |", "|---|---|---|"]
    linhas += [f"| {e['date'][:10]} | {e['kind']} | {e['detail']} |" for e in _eventos(dados, a["id"])]
    saida = _dir_saida()
    try:
        saida.mkdir(parents=True, exist_ok=True)
        arq = saida / f"dossie_{_norm(a['id'])}.md"
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    except OSError as e:
        return _erro(f"Não consegui gravar o dossiê: {e}")
    return {"ok": True, "arquivo": str(arq), "pendencias": pend}


# ---------------------------------------------------------------- propostas (não gravam)
@_com_dados
def propor_manejo(dados, animal_id: str, tipo: str, valor: str = "", produto: str = "") -> dict:
    """PROPÕE (não grava) um manejo. tipo: 'pesagem' (valor = kg), 'vacina' (produto, valor =
    dose opcional) ou 'transferencia' (valor = lote de destino). O usuário confirma depois."""
    a = _achar_animal(dados, animal_id)
    if not a:
        return _erro(f"Animal '{animal_id}' não encontrado. Nada foi proposto.")
    t = _norm(tipo)
    if t not in TIPOS_MANEJO:
        return _erro(f"Tipo '{tipo}' inválido. Use: {', '.join(TIPOS_MANEJO)}.")
    prop = {"tipo_registro": "manejo", "animal_id": a["id"], "tipo": t,
            "valor": str(valor), "produto": produto}
    if t == "pesagem":
        try:
            kg = float(str(valor).replace(",", ".").lower().replace("kg", "").strip())
        except ValueError:
            return _erro("Valor de pesagem inválido; informe o peso em kg.")
        if kg <= 0:
            return _erro("O peso deve ser maior que zero.")
        prop["valor"] = f"{kg:g}"
    elif t == "vacina":
        if not produto:
            return _erro("Informe o produto da vacina.")
    else:
        destinos = _achar_lotes(dados, valor) if valor else []
        if len(destinos) != 1:
            return _erro(f"Lote de destino '{valor}' não encontrado.")
        if destinos[0] == a["lot"]:
            return _erro(f"{a['id']} já está em {a['lot']}.")
        prop["valor"] = destinos[0]
    prop["resumo"] = {"pesagem": f"Pesagem de {a['id']}: {prop['valor']} kg",
                      "vacina": f"Vacina {produto} em {a['id']}",
                      "transferencia": f"Transferir {a['id']} de {a['lot']} para {prop['valor']}"}[t]
    PENDENTES.append(prop)
    return {"ok": True, "status": "PROPOSTA registrada, ainda NÃO gravada; aguarda confirmação "
            "do usuário.", "proposta": prop["resumo"]}


@_com_dados
def propor_tarefa(dados, titulo: str, lote: str, quantidade: int, data_limite: str) -> dict:
    """PROPÕE (não grava) uma tarefa de manejo para um lote. data_limite no formato AAAA-MM-DD."""
    lotes = _achar_lotes(dados, lote) if lote else []
    if len(lotes) != 1:
        return _erro(f"Lote '{lote}' não encontrado. Nada foi proposto.")
    try:
        limite = date.fromisoformat(str(data_limite))
    except ValueError:
        return _erro("data_limite inválida; use AAAA-MM-DD.")
    if not titulo.strip() or int(quantidade) <= 0:
        return _erro("Informe um título e uma quantidade maior que zero.")
    prop = {"tipo_registro": "tarefa", "titulo": titulo.strip(), "lote": lotes[0],
            "quantidade": int(quantidade), "data_limite": limite.isoformat()}
    prop["resumo"] = f"Tarefa '{prop['titulo']}' no {lotes[0]} ({quantidade} animais) até {limite}"
    PENDENTES.append(prop)
    return {"ok": True, "status": "PROPOSTA registrada, ainda NÃO gravada; aguarda confirmação "
            "do usuário.", "proposta": prop["resumo"]}


# ---------------------------------------------------------------- fora do alcance do LLM
def listar_pendentes() -> list[dict]:
    return list(PENDENTES)


def descartar_pendentes() -> int:
    n = len(PENDENTES)
    PENDENTES.clear()
    return n


def aplicar_pendentes() -> dict:
    """Grava as propostas pendentes no JSON. Chamada só pelo código, após confirmação [s/N]."""
    if not PENDENTES:
        return {"ok": True, "aplicados": 0, "mensagem": "Nada pendente."}
    try:
        dados = _carregar()
    except (OSError, ValueError) as e:
        return _erro(f"Não consegui ler os dados: {e}")
    agora = datetime.combine(_hoje(), datetime.min.time()).replace(hour=12).isoformat()
    feitos, falhas = [], []

    def novo_evento(animal_id, kind, title, detail):
        dados["events"].append({"id": f"event-{uuid.uuid4().hex[:12]}", "animalId": animal_id,
                                "kind": kind, "title": title, "detail": detail, "date": agora})

    for p in list(PENDENTES):
        if p["tipo_registro"] == "tarefa":
            t = _norm(p["titulo"])
            kind = "vaccine" if "vacin" in t else "weight" if "pesag" in t else "manejo"
            dados["tasks"].append({
                "id": f"task-{uuid.uuid4().hex[:12]}", "kind": kind, "title": p["titulo"],
                "lot": p["lote"], "count": p["quantidade"], "completed": 0,
                "dueAt": datetime.fromisoformat(p["data_limite"]).isoformat(), "notes": ""})
            feitos.append(p["resumo"])
            continue
        a = _achar_animal(dados, p["animal_id"])
        if not a:
            falhas.append(f"{p['animal_id']} não existe mais")
            continue
        if p["tipo"] == "pesagem":
            kg = float(p["valor"])
            novo_evento(a["id"], "weight", "Pesagem registrada", f"{kg:g} kg")
            a["gain30d"] = round(kg - a["weightKg"])  # mesma regra do app: novo - anterior
            a["weightKg"] = round(kg)
        elif p["tipo"] == "vacina":
            dose = f" - dose {p['valor']}" if p["valor"] else ""
            novo_evento(a["id"], "vaccine", "Manejo sanitario registrado", f"{p['produto']}{dose}")
        else:
            novo_evento(a["id"], "transfer", "Transferencia registrada",
                        f"De {a['lot']} para {p['valor']}")
            a["lot"] = p["valor"]
        feitos.append(p["resumo"])
    destino = _caminho_dados()
    tmp = destino.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(destino)
    PENDENTES.clear()
    return {"ok": not falhas, "aplicados": len(feitos), "itens": feitos, "falhas": falhas}


# Única lista entregue ao LLM. aplicar_pendentes/listar_pendentes/descartar_pendentes ficam de fora.
FERRAMENTAS_LLM = [buscar_animais, historico_animal, animais_sem_vacina, ganho_peso_lote,
                   auditar_cadastro, identificacoes_recentes, processar_identificacao,
                   gerar_dossie, propor_manejo, propor_tarefa]
