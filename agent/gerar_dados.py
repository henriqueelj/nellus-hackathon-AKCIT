"""Gera o rebanho SINTÉTICO em data/rebanho.json (formato do agroid_data.json do app).

Todos os dados são fictícios. O campo `identificacoes` é MOCK: o app não possui esse histórico.
Data de referência: variável NELLUS_HOJE (AAAA-MM-DD), padrão = data atual.
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MODELO = "efficientnet_arcface_v1"
SEM_ID_VISUAL = {"BR 107", "BR 112", "BR 120", "BR 124"}
CATEGORIAS = ["Boi", "Vaca", "Novilha", "Boi"]


def hoje() -> date:
    valor = os.environ.get("NELLUS_HOJE")
    return date.fromisoformat(valor) if valor else date.today()


def _iso(d: date, hora: int = 8) -> str:
    return datetime(d.year, d.month, d.day, hora).isoformat()


def gerar(ref: date) -> dict:
    def dia(n: int) -> str:
        return _iso(ref - timedelta(days=n))

    animais, eventos = [], []
    seq = 0

    def evento(animal_id, kind, title, detail, data):
        nonlocal seq
        seq += 1
        eventos.append({"id": f"event-{seq:04d}", "animalId": animal_id, "kind": kind,
                        "title": title, "detail": detail, "date": data})

    for i in range(24):
        brinco = f"BR {101 + i}"
        peso0 = 360 + (i * 7) % 60
        ganho = 12 + (i * 3) % 10
        pesos = [peso0, peso0 + ganho, peso0 + 2 * ganho + (i % 4)]
        visual = None
        if brinco not in SEM_ID_VISUAL:
            pasta = brinco.replace(" ", "-")
            visual = {
                "captures": [{"angle": a, "path": f"sintetico://{pasta}/{a}",
                              "capturedAt": dia(120)} for a in ("front", "right", "left")],
                "createdAt": dia(120),
                "modelVersion": MODELO,
            }
        animais.append({
            "id": brinco, "name": f"Sintetico {101 + i}",
            "category": CATEGORIAS[i % 4], "breed": "Nelore",
            "weightKg": pesos[-1], "lot": f"Lote {i // 8 + 1}",
            "age": "Nao informado", "variant": "nelore", "tagTone": "primary",
            "sisbov": "", "birthDate": "Nao informada", "mother": "", "father": "",
            "pregnant": False, "expectedBirth": None,
            "gain30d": pesos[-1] - pesos[-2], "active": True, "visualId": visual,
        })
        lote = "Lote 1" if brinco == "BR 110" else f"Lote {i // 8 + 1}"  # BR 110 entrou no Lote 1
        evento(brinco, "registration", "Animal cadastrado",
               f"Entrada no {lote}" + (" com ID visual" if visual else ""), dia(120))
        for atraso, p in zip((60, 30, 3), pesos):
            evento(brinco, "weight", "Pesagem registrada", f"{p} kg", dia(atraso))
        n = 101 + i
        if n <= 116:
            vac = 60
        elif n <= 119:
            vac = 45
        elif n <= 122:
            vac = 210
        else:
            vac = None
        if vac is not None:
            evento(brinco, "vaccine", "Manejo sanitario registrado", "Aftosa - dose 2 ml", dia(vac))
        if brinco == "BR 110":
            evento(brinco, "transfer", "Transferencia registrada", "De Lote 1 para Lote 2", dia(20))

    mock = [
        ("ident_001", "BR 121", 0.91, "accepted", "BR 118", 0.58),
        ("ident_002", "BR 105", 0.79, "review", "BR 109", 0.76),
        ("ident_003", "BR 110", 0.52, "rejected", "BR 103", 0.49),
        ("ident_004", "BR 103", 0.88, "accepted", "BR 111", 0.51),
    ]
    identificacoes = [
        {"id": i, "data": _iso(ref - timedelta(days=k), 10), "animalId": a, "score": s,
         "decisao": d, "segundoCandidato": c, "scoreSegundo": s2}
        for k, (i, a, s, d, c, s2) in enumerate(mock, start=1)
    ]
    return {
        "schemaVersion": 4,
        "user": {"name": "Produtor Sintetico", "email": "demo@exemplo.invalid",
                 "ranch": "Fazenda Sintetica", "farms": 1},
        "animals": animais,
        "lots": [
            {"name": "Lote 1", "hectares": 40, "status": "ativo", "days": 0, "tone": "primary"},
            {"name": "Lote 2", "hectares": 0, "status": "ativo", "days": 0, "tone": "primary"},
            {"name": "Lote 3", "hectares": 35, "status": "ativo", "days": 0, "tone": "primary"},
        ],
        "tasks": [], "movements": [], "events": eventos, "recognitionReports": [],
        "setupComplete": True,
        "identificacoes": identificacoes,  # MOCK: o app não registra histórico de identificações
        "_aviso": "DADOS SINTETICOS. 'identificacoes' e MOCK (inexistente no app).",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", default=str(RAIZ / "data" / "rebanho.json"))
    args = ap.parse_args()
    ref = hoje()
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(gerar(ref), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gerado {saida} (HOJE={ref.isoformat()}, dados sintéticos)")


if __name__ == "__main__":
    main()
