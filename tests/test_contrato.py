import copy
import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
from validar_contrato import EXEMPLOS, carregar_validador, validar  # noqa: E402

V = carregar_validador()
BASE = json.loads((EXEMPLOS / "valido_02_review_com_campos_propostos.json").read_text())


@pytest.mark.parametrize("arq", sorted(EXEMPLOS.glob("valido_*.json")), ids=lambda p: p.name)
def test_exemplos_validos(arq):
    assert validar(json.loads(arq.read_text()), V) == []


@pytest.mark.parametrize("arq", sorted(EXEMPLOS.glob("invalido_*.json")), ids=lambda p: p.name)
def test_exemplos_invalidos(arq):
    assert validar(json.loads(arq.read_text()), V)


def test_quantidade_de_exemplos():
    assert len(list(EXEMPLOS.glob("valido_*.json"))) == 3
    assert len(list(EXEMPLOS.glob("invalido_*.json"))) == 2


def muda(**kw):
    d = copy.deepcopy(BASE)
    for k, v in kw.items():
        if v is KeyError:
            d.pop(k)
        else:
            d[k] = v
    return d


@pytest.mark.parametrize("doc", [
    muda(decisao="unavailable"),                       # fora do enum
    muda(score=1.2),                                   # fora de 0..1
    muda(decisao="accepted"),                          # 0.79 < 0.85
    muda(decisao="rejected"),                          # rejected exige animalId null e score < 0.70
    muda(animalId=None),                               # review exige animal
    muda(modelVersion=KeyError),                       # animal sem modelVersion
    muda(scoreSegundo=KeyError),                       # segundoCandidato sem score
    muda(margem=0.2),                                  # inconsistente com score - scoreSegundo
    muda(scoreSegundo=0.9, margem=0.0),                # segundo maior que o primeiro
    muda(timestamp="ontem"),                           # formato de data
    muda(schemaVersion="2.0"),
])
def test_invalidos_variados(doc):
    assert validar(doc, V)


def test_proposto_e_opcional():
    d = {k: v for k, v in BASE.items()
         if k in ("schemaVersion", "animalId", "score", "decisao", "modelVersion")}
    assert validar(d, V) == []


def test_origem_marcada_em_todas_as_propriedades():
    props = V.schema["properties"]
    hoje = {k for k, p in props.items() if p["x-origem"] == "produzido-hoje-pelo-app"}
    proposto = {k for k, p in props.items() if p["x-origem"] == "proposto"}
    assert hoje == {"animalId", "score", "decisao", "modelVersion"}
    assert proposto == {"timestamp", "usuario", "segundoCandidato", "scoreSegundo", "margem"}
    assert props["schemaVersion"]["x-origem"] == "contrato"
