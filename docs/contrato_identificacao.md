# Contrato de identificação (v1.0): PROPOSTA

Schema: [contrato_identificacao.schema.json](contrato_identificacao.schema.json) · Exemplos:
[exemplos/](exemplos/) (3 válidos, 2 inválidos) · Validador: `python scripts/validar_contrato.py`.

> Todos os exemplos são **sintéticos**. Este contrato é uma **proposta**: o app Flutter **não**
> emite nem persiste este evento hoje.

## O que o app produz hoje (em memória, não persistido)

Conferido em `lib/vision/cattle_vision_service.dart` e `lib/data.dart` do app. O reconhecimento
devolve um `VisionMatch` (decisão, animal, score, mensagem) que vive só enquanto a tela está aberta.

| Campo do contrato | Origem no app |
|---|---|
| `animalId` | `animal.id` do `VisionMatch`; fica **nulo** quando a decisão é `rejected` |
| `score` | `VisionMatch.score` (0 a 1) |
| `decisao` | `accepted` (>= 0.85), `review` (>= 0.70), `rejected` (< 0.70). O app tem ainda `unavailable`, que não é resultado de identificação e fica fora do contrato |
| `modelVersion` | `visualId.modelVersion` do animal reconhecido (hoje `efficientnet_arcface_v1`); não vem no `VisionMatch` |

## PROPOSTO, não existe no app hoje (opcionais)

| Campo | Para quê |
|---|---|
| `timestamp` | Saber quando a identificação aconteceu (o app não guarda histórico) |
| `usuario` | Quem identificou |
| `segundoCandidato`, `scoreSegundo` | Permitir detectar confusão entre dois animais parecidos |
| `margem` | `score - scoreSegundo`; o agente alerta quando a margem é menor que 0.10 |

`schemaVersion` identifica a versão do contrato. Regras extras: `accepted` e `review` exigem
`animalId` e `modelVersion`; `rejected` exige `animalId` nulo e score < 0.70;
`segundoCandidato`, `scoreSegundo` e `margem` andam juntos; `margem` precisa bater com
`score - scoreSegundo` (checado em código, pois JSON Schema não calcula).

## Como isso chegaria ao agente

**A integração NÃO está implementada.** Para existir, o app precisaria (1) gravar um evento neste
formato a cada identificação, hoje inexistente, e (2) sincronizá-lo com um local que o agente
leia. Neste repositório o agente lê o campo `identificacoes` de `data/rebanho.json`, que é
**mock sintético**, sem relação com um app real. A tool `processar_identificacao` já aplica as
regras (aftosa do animal reconhecido, margem < 0.10, `rejected` = não reconhecido) sobre esse
mock; adaptá-la ao contrato real seria trabalho futuro.

O mock usa nomes próprios (`id`, `data`) e não traz `schemaVersion`, `modelVersion` nem `margem`.
`python scripts/validar_contrato.py --rebanho` adapta cada item (data -> timestamp, modelVersion
do `visualId` do animal, margem = score - scoreSegundo) e o valida contra o schema. Em
`ident_003` (rejected) o `animalId` é nulo, como no app.
