# Nellus Hackathon: agente de manejo (provisório)

Agente de IA (Python + Gemini com function calling) que consulta dados **SINTÉTICOS** de um rebanho
Nelore e propõe (nunca grava sem confirmação) ações de manejo.

- Todos os dados deste repositório são sintéticos.
- O app Flutter da Nellus **não** registra histórico de identificações e **não** está integrado a este
  agente. O campo `identificacoes` do JSON é mock.

## Auditoria priorizada (regras fixas, calculadas em código)

A tool `auditoria_priorizada` ordena os achados por severidade e, dentro dela, por mais dias de
atraso. O LLM apenas explica o plano; não reordena nem inventa itens.

| Severidade | Regra | Dias de atraso (desempate) |
|---|---|---|
| CRITICA | Aftosa nunca aplicada, ou vencida (última aplicação há mais de 180 dias) | nunca: dias desde o cadastro; vencida: dias além dos 180 |
| ALTA | Animal ativo sem identificação visual (o app não consegue reconhecê-lo) | dias desde o cadastro |
| MEDIA | Lote sem área em hectares (impede o cálculo de lotação UA/ha) | 0 |
| BAIXA | SISBOV vazio (um único item agrupado: contagem + exemplos) | 0 |

README completo na Fase 4.
