"""Harness de avaliação do agente Nellus (camada B, com Gemini).

Uso:  GEMINI_API_KEY=... python eval/harness.py [-n 3] [--cenarios 1 5 11]
Cada execução usa uma CÓPIA do JSON e NELLUS_HOJE=2026-10-24. Nunca grava no original e
nunca chama aplicar_pendentes (nenhuma escrita sem confirmação).
Erro ou cota da API = "inconclusivo" (reexecutado 1x), nunca falha do agente.
Mede o comportamento do agente em dados SINTÉTICOS; NÃO mede a acurácia do modelo de visão.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAIZ / "agent"))
from cenarios import CENARIOS, Ctx, verificacoes_gerais  # noqa: E402
import agent  # noqa: E402
import tools  # noqa: E402

DATA_FIXA = "2026-10-24"
RELATORIO = Path(__file__).resolve().parent / "relatorio.md"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def executar(cen, chave, modelo):
    """Uma execução. Retorna dict com resultado: passou | falhou | inconclusivo."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        copia = tmp / "rebanho.json"
        shutil.copy(RAIZ / "data" / "rebanho.json", copia)
        os.environ.update(NELLUS_HOJE=DATA_FIXA, NELLUS_DATA=str(copia), NELLUS_OUT=str(tmp / "out"))
        tools.PENDENTES.clear()
        antes = sha(copia)
        t0 = time.time()
        try:
            chat, _ = agent.criar_chat(chave, modelo)
            resp = chat.send_message(cen.pergunta)
            texto = resp.text or ""
            chamadas = agent.chamadas_do_turno(resp, chat)
        except Exception as e:  # API/cota/rede: inconclusivo
            return {"resultado": "inconclusivo", "motivo": f"{type(e).__name__}: {str(e)[:160]}",
                    "latencia": time.time() - t0, "tools": []}
        lat = time.time() - t0
        ctx = Ctx(cen.pergunta, texto, chamadas, json.loads(copia.read_text()), antes, sha(copia),
                  list(tools.PENDENTES), tmp / "out")
        falhas = verificacoes_gerais(ctx, cen) + cen.verificar(ctx)
        tools.PENDENTES.clear()
        return {"resultado": "falhou" if falhas else "passou", "falhas": falhas,
                "latencia": lat, "tools": ctx.nomes, "resposta": texto[:300]}


def relatorio(modelo, n, resultados, nota=""):
    tot = Counter(r["resultado"] for rs in resultados.values() for r in rs)
    todas = [r for rs in resultados.values() for r in rs]
    conclusivas = tot["passou"] + tot["falhou"]
    lat = [r["latencia"] for r in todas if r["resultado"] != "inconclusivo"]
    L = ["# Relatório do harness (camada B, com Gemini)", "",
         "> **DADOS SINTÉTICOS.** Estes números medem o comportamento do AGENTE (uso de tools, "
         "recusas, fidelidade aos dados) sobre um rebanho fictício. **Não** medem a acurácia do "
         "modelo de visão. As identificações são MOCK; o app Flutter não registra histórico de "
         "identificações nem está integrado ao agente.", "",
         f"- Modelo: `{modelo}` | Data: {date.today().isoformat()} | Data de referência dos "
         f"dados: {DATA_FIXA} | Execuções por cenário: {n}", ""]
    if nota:
        L += [nota, ""]
    L += ["## Taxa de acerto por cenário", "", "| # | Cenário | Acertos | Inconclusivas | Falhas "
          "| Tools chamadas (mais frequentes) |", "|---|---|---|---|---|---|"]
    for cen in CENARIOS:
        rs = resultados.get(cen.id)
        if not rs:
            continue
        c = Counter(r["resultado"] for r in rs)
        feitas = c["passou"] + c["falhou"]
        tl = Counter(t for r in rs for t in set(r["tools"])).most_common(3)
        L.append(f"| {cen.id} | {cen.nome} | {c['passou']}/{feitas if feitas else '-'} | "
                 f"{c['inconclusivo']} | {c['falhou']} | "
                 f"{', '.join(f'{t} ({k})' for t, k in tl) or '-'} |")
    L += ["", "## Geral", "", "| Métrica | Valor |", "|---|---|",
          f"| Execuções | {len(todas)} |", f"| Passou | {tot['passou']} |",
          f"| Falhou | {tot['falhou']} |", f"| Inconclusivas (API/cota) | {tot['inconclusivo']} |",
          f"| Taxa de acerto (sobre conclusivas) | "
          f"{tot['passou'] / conclusivas:.0%} |" if conclusivas else "| Taxa de acerto | n/d |",
          f"| Latência média (conclusivas) | {sum(lat) / len(lat):.1f} s |" if lat
          else "| Latência média | n/d |", ""]
    falhas = [(c.id, c.nome, r["falhas"]) for c in CENARIOS for r in resultados.get(c.id, [])
              if r["resultado"] == "falhou"]
    if falhas:
        L += ["## Falhas observadas", ""]
        L += [f"- Cenário {i} ({nome}): {'; '.join(f)}" for i, nome, f in falhas]
        L.append("")
    L += ["## O que este relatório NÃO mede", "",
          "- A acurácia do modelo de visão (EfficientNet-B0 + ArcFace, treinado com 12 animais; "
          "limiares 0.85 accepted e 0.70 review): nenhuma imagem é usada aqui.",
          "- Desempenho em rebanhos, fotos ou ruídos reais: todos os dados são sintéticos.",
          "- Integração com o app: ela não existe; o campo `identificacoes` é mock.",
          "- Variação entre modelos ou versões: só o modelo acima foi usado.",
          "- Qualidade textual fina das respostas: as asserções são objetivas (IDs, tools, "
          "hash do JSON, ordem de severidade), não de estilo.",
          "- Execuções inconclusivas (erro/cota da API) não entram na taxa de acerto.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=3, help="execuções por cenário (padrão 3)")
    ap.add_argument("--cenarios", type=int, nargs="*", help="ids de cenários (padrão: todos)")
    args = ap.parse_args()

    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        print("AVISO: GEMINI_API_KEY ausente: camada B (Gemini) PULADA. Rode a camada A com pytest.")
        if not RELATORIO.exists():
            RELATORIO.write_text(
                "# Relatório do harness (camada B)\n\n> DADOS SINTÉTICOS.\n\n**Camada B NÃO "
                "executada**: faltou GEMINI_API_KEY. Nenhum número foi medido. Rode "
                "`python eval/harness.py` com a chave para gerar este relatório.\n",
                encoding="utf-8")
        return 0
    modelo = os.environ.get("GEMINI_MODEL", agent.MODELO_PADRAO)
    resultados = {}
    for cen in CENARIOS:
        if args.cenarios and cen.id not in args.cenarios:
            continue
        resultados[cen.id] = []
        for k in range(args.n):
            r = executar(cen, chave, modelo)
            if r["resultado"] == "inconclusivo":  # reexecução única (erro de API/cota/timeout)
                print(f"[{cen.id:02d}] {cen.nome} #{k + 1}: inconclusivo ({r['motivo']}); reexecutando 1x")
                time.sleep(5)
                r2 = executar(cen, chave, modelo)
                r2["reexecutada"] = True
                r = r2
            resultados[cen.id].append(r)
            extra = r.get("motivo") or "; ".join(r.get("falhas", []))
            print(f"[{cen.id:02d}] {cen.nome} #{k + 1}: {r['resultado']} {extra}")
    RELATORIO.write_text(relatorio(modelo, args.n, resultados), encoding="utf-8")
    print(f"Relatório: {RELATORIO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
