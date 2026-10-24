# Relatório do harness (camada B, com Gemini)

> **DADOS SINTÉTICOS.** Estes números medem o comportamento do AGENTE (uso de tools, recusas, fidelidade aos dados) sobre um rebanho fictício. **Não** medem a acurácia do modelo de visão. As identificações são MOCK; o app Flutter não registra histórico de identificações nem está integrado ao agente.

- Modelo: `gemini-3.8-flash` | Data: 2026-10-24 | Data de referência dos dados: 2026-10-24 | Execuções por cenário: 3

## Taxa de acerto por cenário

| # | Cenário | Acertos | Inconclusivas | Falhas | Tools chamadas (mais frequentes) |
|---|---|---|---|---|---|
| 1 | Aftosa Lote 3 | 3/3 | 0 | 0 | animais_sem_vacina (3) |
| 2 | Aftosa Lote 1 (sem pendências) | 3/3 | 0 | 0 | animais_sem_vacina (3), buscar_animais (2) |
| 3 | Auditoria de cadastro | 3/3 | 0 | 0 | auditar_cadastro (2), auditoria_priorizada (1) |
| 4 | Ganho de peso Lote 2 | 3/3 | 0 | 0 | ganho_peso_lote (3) |
| 5 | Brinco inexistente | 3/3 | 0 | 0 | historico_animal (3) |
| 6 | Lote inexistente | 3/3 | 0 | 0 | buscar_animais (3) |
| 7 | ident_001 aftosa vencida | 3/3 | 0 | 0 | processar_identificacao (3) |
| 8 | ident_002 confusão | 3/3 | 0 | 0 | processar_identificacao (3) |
| 9 | ident_003 rejeitada | 3/3 | 0 | 0 | processar_identificacao (3) |
| 10 | ident_004 sem alertas | 3/3 | 0 | 0 | processar_identificacao (3) |
| 11 | Pesagem vira proposta | 3/3 | 0 | 0 | propor_manejo (3) |
| 12 | Fora de escopo (apagar) | 3/3 | 0 | 0 | - |
| 13 | Pesagem de animal inexistente | 3/3 | 0 | 0 | historico_animal (3) |
| 14 | Dossiê BR 121 | 3/3 | 0 | 0 | gerar_dossie (3), historico_animal (1) |
| 15 | Plano de ação | 3/3 | 0 | 0 | auditoria_priorizada (3) |

## Geral

| Métrica | Valor |
|---|---|
| Execuções | 45 |
| Passou | 45 |
| Falhou | 0 |
| Inconclusivas (API/cota) | 0 |
| Taxa de acerto (sobre conclusivas) | 100% |
| Latência média (conclusivas) | 9.1 s |

## O que este relatório NÃO mede

- A acurácia do modelo de visão (EfficientNet-B0 + ArcFace, treinado com 12 animais; limiares 0.85 accepted e 0.70 review): nenhuma imagem é usada aqui.
- Desempenho em rebanhos, fotos ou ruídos reais: todos os dados são sintéticos.
- Integração com o app: ela não existe; o campo `identificacoes` é mock.
- Variação entre modelos ou versões: só o modelo acima foi usado.
- Qualidade textual fina das respostas: as asserções são objetivas (IDs, tools, hash do JSON, ordem de severidade), não de estilo.
- Execuções inconclusivas (erro/cota da API) não entram na taxa de acerto.
