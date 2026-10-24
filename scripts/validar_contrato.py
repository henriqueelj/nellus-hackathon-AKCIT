"""Valida eventos de identificação contra docs/contrato_identificacao.schema.json.

Uso:  python scripts/validar_contrato.py [arquivo.json ...]
Sem argumentos valida docs/exemplos/: valido_*.json devem passar e invalido_*.json devem falhar.
Com --rebanho [caminho]: valida cada item de `identificacoes` do JSON de dados, após adaptá-lo
ao contrato (o mock usa `id`/`data` e não traz schemaVersion/modelVersion/margem).
Além do JSON Schema, confere a regra que ele não expressa: margem == score - scoreSegundo.
O contrato é uma PROPOSTA; o app Flutter não emite este evento hoje.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA = RAIZ / "docs" / "contrato_identificacao.schema.json"
EXEMPLOS = RAIZ / "docs" / "exemplos"
TOLERANCIA = 0.005


def carregar_validador() -> Draft202012Validator:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validar(doc, validador=None) -> list[str]:
    """Lista de erros (vazia = válido): schema + consistência numérica."""
    validador = validador or carregar_validador()
    erros = [f"{'/'.join(map(str, e.path)) or '(raiz)'}: {e.message}"
             for e in sorted(validador.iter_errors(doc), key=lambda e: list(map(str, e.path)))]
    if not erros and isinstance(doc, dict):
        if "timestamp" in doc:  # 'format' não é validado sem pacotes extras; checamos aqui
            try:
                datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00"))
            except ValueError:
                erros.append(f"timestamp '{doc['timestamp']}' não é data/hora ISO 8601")
        if "scoreSegundo" in doc and doc["scoreSegundo"] > doc["score"]:
            erros.append("scoreSegundo maior que score (o primeiro deve ser o melhor)")
        if "margem" in doc and abs(doc["margem"] - (doc["score"] - doc["scoreSegundo"])) > TOLERANCIA:
            erros.append(f"margem {doc['margem']} != score - scoreSegundo "
                         f"({doc['score'] - doc['scoreSegundo']:.2f})")
    return erros


def identificacao_para_contrato(item: dict, animais: list[dict]) -> dict:
    """Adapta um item de `identificacoes` (mock) ao contrato: data->timestamp, acrescenta
    schemaVersion, modelVersion (do visualId do animal) e margem; descarta o `id` do mock."""
    doc = {"schemaVersion": "1.0", "animalId": item.get("animalId"), "score": item["score"],
           "decisao": item["decisao"], "timestamp": item["data"]}
    animal = next((a for a in animais if a["id"] == doc["animalId"]), None)
    if animal and animal.get("visualId"):
        doc["modelVersion"] = animal["visualId"]["modelVersion"]
    if item.get("segundoCandidato") is not None:
        doc["segundoCandidato"] = item["segundoCandidato"]
        doc["scoreSegundo"] = item["scoreSegundo"]
        doc["margem"] = round(item["score"] - item["scoreSegundo"], 2)
    return doc


def validar_rebanho(caminho: Path, validador) -> int:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    ruim = 0
    for item in dados.get("identificacoes", []):
        erros = validar(identificacao_para_contrato(item, dados["animals"]), validador)
        print(f"{'OK      ' if not erros else 'INVALIDO'} {item['id']} ({item['decisao']})")
        for e in erros:
            print(f"    - {e}")
        ruim += bool(erros)
    print("validar_contrato --rebanho:", "FALHOU" if ruim else "OK")
    return 1 if ruim else 0


def main(argv) -> int:
    validador = carregar_validador()
    if argv and argv[0] == "--rebanho":
        return validar_rebanho(Path(argv[1]) if len(argv) > 1 else RAIZ / "data" / "rebanho.json",
                               validador)
    if argv:
        ruim = 0
        for caminho in map(Path, argv):
            erros = validar(json.loads(caminho.read_text(encoding="utf-8")), validador)
            print(f"{'OK    ' if not erros else 'INVALIDO'} {caminho}")
            for e in erros:
                print(f"    - {e}")
            ruim += bool(erros)
        return 1 if ruim else 0
    falhas = 0
    for caminho in sorted(EXEMPLOS.glob("*.json")):
        erros = validar(json.loads(caminho.read_text(encoding="utf-8")), validador)
        esperado_valido = caminho.name.startswith("valido_")
        ok = (not erros) == esperado_valido
        falhas += not ok
        print(f"{'OK  ' if ok else 'ERRO'} {caminho.name}: "
              f"{'válido' if not erros else 'inválido (' + erros[0] + ')'}")
    print("validar_contrato:", "FALHOU" if falhas else "OK")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
