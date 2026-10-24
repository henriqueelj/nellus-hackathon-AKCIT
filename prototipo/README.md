# Protótipo da tela do assistente

> **Dados SINTÉTICOS.** O app Flutter da Nellus **não** tem esta tela nem a integração com o
> agente. A identificação do animal continua no celular, sem LLM. Esta página mostra **como a
> experiência ficaria**. O evento de identificação (`ident_001` etc.) é **MOCK**.

## O que é

Uma tela de celular (um único `index.html`) servida por um servidor local (`servidor.py`, só
biblioteca padrão) que conversa com o **agente real** do projeto: `agent/agent.py` (Gemini +
function calling) sobre as ferramentas de `agent/tools.py`. Nada em `agent/` foi alterado.

## Como rodar

```bash
export GEMINI_API_KEY=...                  # só do ambiente; nunca vai para a página, arquivos ou logs
.venv/bin/python prototipo/servidor.py     # escuta só em 127.0.0.1; PORTA muda a porta (padrão 8000)
# abrir http://127.0.0.1:8000
```

`GEMINI_MODEL` troca o modelo. Sem a chave, o servidor sobe e a tela avisa; as chamadas ao agente falham.

## Como funciona a confirmação

- Ao iniciar, `data/rebanho.json` é **copiado** para um diretório temporário. As ferramentas
  apontam para a cópia (`NELLUS_DATA`, `NELLUS_OUT`, `NELLUS_HOJE=2026-10-24` por padrão).
  O servidor também guarda os bytes do original e os restaura se algo o alterar.
- O agente só **propõe** (`propor_manejo`, `propor_tarefa`): isso apenas acrescenta a `PENDENTES`.
  A tela mostra o cartão "Proposta do agente" com **Confirmar** e **Descartar**.
- **Confirmar** chama `aplicar_pendentes()` no servidor (função fora do alcance do LLM) e grava
  **só na cópia**. **Descartar** limpa as pendências. Nenhum dos dois faz chamada extra ao LLM: o
  servidor guarda uma nota "[sistema] O produtor CONFIRMOU/NÃO confirmou…" e a anexa ao início da
  próxima mensagem.
- **Reiniciar** restaura a cópia a partir do original e descarta a conversa e as pendências.
  Abrir ou recarregar a página também reinicia a conversa.

## API (JSON, POST com `Content-Type: application/json`)

`GET /api/estado`, `POST /api/identificacao {id}`, `POST /api/mensagem {texto}`,
`POST /api/decidir {acao}`, `POST /api/reiniciar`. Entrada inválida devolve 400 com `{erro}`;
falha do agente ou do Gemini devolve 500 com `{erro}` curto e sem a chave. Uma conversa por vez
(lock global). Requisições com `Host` diferente de `127.0.0.1`/`localhost` são recusadas.

## Limites

- Dados sintéticos; tudo o que a tela mostra vem do rebanho fictício em `data/rebanho.json`.
- A identificação é mock; o app real não registra histórico de identificações.
- O app Flutter não está integrado: esta é uma demonstração local, sem autenticação.
- Cada resposta depende do Gemini e leva alguns segundos (mais quando há várias ferramentas).
- O servidor mantém uma única conversa; não serve vários usuários.
- A tela não foi validada em aparelhos reais; só em navegador.
