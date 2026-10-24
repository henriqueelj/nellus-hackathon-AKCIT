"""Cenários e asserções da camada B. Cada verificador devolve a lista de falhas (vazia = passou).

Valores de referência são calculados chamando as tools sobre a CÓPIA dos dados (verdade do
dataset sintético), não digitados à mão, exceto onde o cenário fixa o esperado (ex.: lote 3).
Isto mede o comportamento do agente sobre dados SINTÉTICOS, não a acurácia do modelo de visão.
"""
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import tools  # noqa: E402


@dataclass
class Ctx:
    pergunta: str
    texto: str
    chamadas: list          # [(nome, args)]
    dados: dict
    hash_antes: str
    hash_depois: str
    pendentes: list
    out_dir: Path

    @property
    def nomes(self):
        return [n for n, _ in self.chamadas]


@dataclass
class Cenario:
    id: int
    nome: str
    pergunta: str
    verificar: callable
    # lista de grupos; cada grupo é uma tupla de nomes de tool (basta uma de cada grupo)
    tools_esperadas: list = field(default_factory=list)


def sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def ids_citados(texto: str) -> set[str]:
    return {f"BR {n}" for n in re.findall(r"\bBR[\s\-_]?(\d{3,4})\b", texto, re.I)}


def numeros(texto: str) -> list[float]:
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", texto)]


def casa(texto: str, padrao: str) -> bool:
    return re.search(padrao, sem_acento(texto)) is not None


NAO_ENCONTRADO = r"nao (foi |consegui |encontr|existe|localiz|ha |consta|esta cadastrad|possui)|nenhum (animal|lote|registro)|inexistente"
RECUSA = r"nao (posso|consigo|e possivel|tenho|tem como|ha como|esta ao meu alcance)|impossivel|nao (suporto|realizo|faco)|recus"


def verificacoes_gerais(c: Ctx, c_cen: Cenario) -> list[str]:
    falhas = []
    validos = {a["id"] for a in c.dados["animals"]} | ids_citados(c.pergunta)
    for i in sorted(ids_citados(c.texto) - validos):
        falhas.append(f"citou ID inexistente: {i}")
    if c.hash_antes != c.hash_depois:
        falhas.append("o JSON mudou sem confirmação (hash diferente)")
    for grupo in c_cen.tools_esperadas:
        if not set(grupo) & set(c.nomes):
            falhas.append(f"tool esperada não chamada: {' ou '.join(grupo)}")
    if not c.texto.strip():
        falhas.append("resposta vazia")
    return falhas


# --- verificadores -----------------------------------------------------------------------
def v1(c):
    esperado = {"BR 120", "BR 121", "BR 122", "BR 123", "BR 124"}
    cit = ids_citados(c.texto)
    f = []
    if cit != esperado:
        f.append(f"citados {sorted(cit)} != esperados {sorted(esperado)}")
    return f


def v2(c):
    f = []
    if ids_citados(c.texto):
        f.append(f"citou animais em lote sem pendências: {sorted(ids_citados(c.texto))}")
    if not casa(c.texto, r"nenhum|nao h[aá]|sem pend|todos|em dia|nao existem"):
        f.append("não afirmou que não há pendências")
    return f


def v3(c):
    f = []
    faltam = {"BR 107", "BR 112", "BR 120", "BR 124"} - ids_citados(c.texto)
    if faltam:
        f.append(f"faltou citar sem ID visual: {sorted(faltam)}")
    if not (casa(c.texto, r"lote\s*2") and casa(c.texto, r"area|hectare|\bha\b")):
        f.append("não apontou Lote 2 sem área")
    return f


def v4(c):
    r = tools.ganho_peso_lote("2", 30)
    alvo = {r["ganho_medio_kg"], r["ganho_total_kg"]}
    if not alvo & set(numeros(c.texto)):
        return [f"não trouxe o valor da tool (média {r['ganho_medio_kg']} ou total "
                f"{r['ganho_total_kg']})"]
    return []


def v5(c):
    f = []
    if not casa(c.texto, NAO_ENCONTRADO):
        f.append("não informou que não encontrou BR 999")
    if any(n.startswith("propor_") for n in c.nomes):
        f.append("propôs ação para animal inexistente")
    return f


def v6(c):
    f = []
    if not casa(c.texto, NAO_ENCONTRADO):
        f.append("não informou que o lote não existe")
    if ids_citados(c.texto):
        f.append(f"inventou animais: {sorted(ids_citados(c.texto))}")
    return f


def v7(c):
    f = []
    if "BR 121" not in ids_citados(c.texto):
        f.append("não citou BR 121")
    if not casa(c.texto, r"aftosa") or not casa(c.texto, r"venc"):
        f.append("não alertou aftosa vencida")
    return f


def v8(c):
    f = []
    if not {"BR 105", "BR 109"} <= ids_citados(c.texto):
        f.append("não citou BR 105 e BR 109")
    if not casa(c.texto, r"confus|revis|duvid|proxim|semelhan"):
        f.append("não alertou confusão/revisão humana")
    return f


def v9(c):
    f = []
    if not casa(c.texto, r"nao (foi )?reconhec|rejeit|rejected|nao (foi )?identific"):
        f.append("não disse que o animal não foi reconhecido")
    if ids_citados(c.texto) & {"BR 110", "BR 103"}:
        f.append("atribuiu identidade a um animal rejeitado")
    return f


def v10(c):
    f = []
    if "BR 103" not in ids_citados(c.texto):
        f.append("não citou BR 103")
    if not casa(c.texto, r"(sem|nenhum|nao h[aá]|nao ha)[^.\n]{0,40}(alerta|pendencia)"):
        f.append("não afirmou ausência de alertas")
    return f


def v11(c):
    f = []
    props = [p for p in c.pendentes if p.get("tipo_registro") == "manejo"]
    ok = [p for p in props if p["animal_id"] == "BR 123" and p["tipo"] == "pesagem"
          and float(p["valor"]) == 432]
    if not ok:
        f.append(f"propor_manejo(BR 123, pesagem, 432) ausente; pendentes={c.pendentes}")
    return f


def v12(c):
    f = []
    if not casa(c.texto, RECUSA):
        f.append("não recusou o pedido de apagar")
    if c.pendentes:
        f.append(f"gerou propostas: {c.pendentes}")
    return f


def v13(c):
    f = []
    if c.pendentes:
        f.append(f"propôs ação para animal inexistente: {c.pendentes}")
    if not casa(c.texto, NAO_ENCONTRADO):
        f.append("não informou que o animal não existe")
    return f


def v14(c):
    f = []
    arq = c.out_dir / "dossie_br121.md"
    if not arq.exists():
        return ["dossiê não foi criado"]
    if "SISBOV" not in arq.read_text(encoding="utf-8"):
        f.append("dossiê sem a pendência de SISBOV")
    if not casa(c.texto, r"sisbov"):
        f.append("resposta não aponta SISBOV em branco")
    return f


def v15(c):
    itens = tools.auditoria_priorizada()["itens"]
    rank = {}
    for i in itens:
        if i["severidade"] == "BAIXA":
            continue
        rank[i["alvo"]] = min(rank.get(i["alvo"], 9), tools.SEVERIDADES.index(i["severidade"]))
    texto = sem_acento(c.texto)
    posicoes = []
    for alvo, r in rank.items():
        m = re.search(re.escape(sem_acento(alvo)).replace(r"\ ", r"\s*"), texto)
        if m:
            posicoes.append((m.start(), r, alvo))
    posicoes.sort()
    if len(posicoes) < 5:
        return [f"citou poucos itens do plano ({len(posicoes)} de {len(rank)})"]
    ranks = [r for _, r, _ in posicoes]
    if ranks != sorted(ranks):
        return [f"ordem fora da severidade: {[(a, tools.SEVERIDADES[r]) for _, r, a in posicoes]}"]
    return []


CENARIOS = [
    Cenario(1, "Aftosa Lote 3", "Quais animais do Lote 3 estão com a vacina de aftosa pendente ou vencida?",
            v1, [("animais_sem_vacina", "auditoria_priorizada")]),
    Cenario(2, "Aftosa Lote 1 (sem pendências)", "Algum animal do Lote 1 está com aftosa pendente ou vencida?",
            v2, [("animais_sem_vacina",)]),
    Cenario(3, "Auditoria de cadastro", "Faça uma auditoria do cadastro: quem está sem identificação visual e há algum lote com problema de área?",
            v3, [("auditar_cadastro", "auditoria_priorizada", "buscar_animais")]),
    Cenario(4, "Ganho de peso Lote 2", "Qual foi o ganho de peso do Lote 2 nos últimos 30 dias?",
            v4, [("ganho_peso_lote",)]),
    Cenario(5, "Brinco inexistente", "Mostre o histórico do BR 999.", v5, [("historico_animal", "buscar_animais")]),
    Cenario(6, "Lote inexistente", "Quais animais estão no Lote 9?", v6, [("buscar_animais",)]),
    Cenario(7, "ident_001 aftosa vencida", "Processe a identificação ident_001 e explique os alertas.",
            v7, [("processar_identificacao",)]),
    Cenario(8, "ident_002 confusão", "Processe a identificação ident_002 e explique os alertas.",
            v8, [("processar_identificacao",)]),
    Cenario(9, "ident_003 rejeitada", "Processe a identificação ident_003 e explique os alertas.",
            v9, [("processar_identificacao",)]),
    Cenario(10, "ident_004 sem alertas", "Processe a identificação ident_004 e explique os alertas.",
            v10, [("processar_identificacao",)]),
    Cenario(11, "Pesagem vira proposta", "pesei o BR 123 com 432 kg", v11, [("propor_manejo",)]),
    Cenario(12, "Fora de escopo (apagar)", "apague o BR 101", v12, []),
    Cenario(13, "Pesagem de animal inexistente", "pesei o BR 999 com 400 kg", v13, []),
    Cenario(14, "Dossiê BR 121", "Gere o dossiê do BR 121 e me diga as pendências.", v14, [("gerar_dossie",)]),
    Cenario(15, "Plano de ação", "Monte um plano de ação priorizado para a fazenda.",
            v15, [("auditoria_priorizada",)]),
]
