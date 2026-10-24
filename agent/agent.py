"""Agente Nellus (CLI): Gemini com function calling sobre dados SINTÉTICOS do rebanho.

Uso:
    export GEMINI_API_KEY=...        # a chave vem só do ambiente
    python agent/agent.py                          # chat
    python agent/agent.py --identificacao ident_001
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools  # noqa: E402

MODELO_PADRAO = "gemini-3.8-flash"  # conferido na doc do Gemini; sobrescreva com GEMINI_MODEL

PROMPT_SISTEMA = """Você é o assistente de manejo do Nellus, para um produtor de gado Nelore.
Os dados são SINTÉTICOS (demonstração). As identificações são MOCK: o app real não registra
histórico de identificações e não está integrado a você.

Regras:
- Use SEMPRE as ferramentas para consultar dados. Nunca invente animais, datas, pesos ou números.
- Cite apenas brincos, lotes e valores que vieram das ferramentas.
- Responda curto e direto, em português.
- Você NUNCA grava nada. Para registrar pesagem, vacina, transferência ou tarefa, use
  propor_manejo / propor_tarefa; o sistema pede a confirmação do usuário depois.
- Pedidos que as ferramentas não suportam (apagar, vender, editar cadastro) devem ser recusados
  com clareza; diga o que você consegue fazer.
- Se a ferramenta indicar que algo não existe (animal, lote, identificação), avise o usuário e
  não proponha nenhuma ação.
- Para "plano de ação", "o que priorizar" ou auditoria, chame auditoria_priorizada. A ordem e a
  severidade dos itens são calculadas pela ferramenta: explique e converse sobre o plano, mas NÃO
  reordene, NÃO reclassifique e NÃO invente itens. Apresente os itens na ordem recebida.
- Animal com decisão 'rejected' não é reconhecido: não diga quem ele é.
"""


def criar_chat(chave: str, modelo: str | None = None):
    """Cria o chat Gemini com as tools de FERRAMENTAS_LLM (sem aplicar_pendentes)."""
    from google import genai
    from google.genai import types

    modelo = modelo or os.environ.get("GEMINI_MODEL", MODELO_PADRAO)
    client = genai.Client(api_key=chave)
    chat = client.chats.create(model=modelo, config=types.GenerateContentConfig(
        system_instruction=PROMPT_SISTEMA, tools=tools.FERRAMENTAS_LLM, temperature=0.2))
    chat._client_ref = client  # sem isto o client é coletado e fechado ao sair da função
    return chat, modelo


def chamadas_do_turno(resposta, chat=None) -> list[tuple[str, dict]]:
    """Tools chamadas neste turno (só o que vem depois da última mensagem de texto do usuário).
    Lê automatic_function_calling_history; se vier vazio (google-genai 2.x), usa o histórico do chat."""
    hist = list(getattr(resposta, "automatic_function_calling_history", None) or [])
    if not hist and chat is not None:
        hist = list(chat.get_history(curated=False))
    inicio = 0
    for i, c in enumerate(hist):
        if c.role == "user" and any(getattr(p, "text", None) for p in (c.parts or [])):
            inicio = i + 1
    chamadas = []
    for c in hist[inicio:]:
        for p in c.parts or []:
            if getattr(p, "function_call", None):
                chamadas.append((p.function_call.name, dict(p.function_call.args or {})))
    return chamadas


def _enviar(chat, texto: str):
    resposta = chat.send_message(texto)
    for nome, args in chamadas_do_turno(resposta, chat):
        print(f"  [tool] {nome}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
    print(f"\nAgente: {resposta.text or '(sem texto)'}\n")
    return resposta


def _confirmar_pendentes(chat):
    """Confirmação feita no CÓDIGO, não pelo LLM."""
    pend = tools.listar_pendentes()
    if not pend:
        return
    print("Propostas pendentes (nada foi gravado ainda):")
    for p in pend:
        print(f"  - {p['resumo']}")
    try:
        r = input("Aplicar? [s/N] ").strip().lower()
    except EOFError:
        r = ""
    if r == "s":
        res = tools.aplicar_pendentes()
        print(f"Resultado: {res}")
        _enviar(chat, f"[sistema] O usuário confirmou. Resultado da gravação: {res}. "
                      "Informe o resultado de forma curta.")
    else:
        n = tools.descartar_pendentes()
        print("Descartado. Nada foi gravado.")
        _enviar(chat, f"[sistema] O usuário recusou; {n} proposta(s) descartada(s), nada gravado.")


def _turno(chat, texto: str):
    _enviar(chat, texto)
    _confirmar_pendentes(chat)


def main():
    ap = argparse.ArgumentParser(description="Agente Nellus (dados sintéticos)")
    ap.add_argument("--identificacao", metavar="ID", help="processa uma identificação MOCK e sai")
    args = ap.parse_args()

    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        sys.exit("Defina GEMINI_API_KEY no ambiente (a chave não é lida de arquivos).")
    chat, modelo = criar_chat(chave)
    print(f"Nellus | modelo {modelo} | DADOS SINTÉTICOS | identificações MOCK")

    try:
        if args.identificacao:
            _turno(chat, f"Processe a identificação {args.identificacao} e explique os alertas.")
            return
        print("Digite sua pergunta (vazio ou 'sair' encerra).\n")
        while True:
            try:
                msg = input("Você: ").strip()
            except EOFError:
                break
            if not msg or msg.lower() == "sair":
                break
            _turno(chat, msg)
    except Exception as e:  # erro/cota da API: mostra e sai sem stack trace
        sys.exit(f"Erro na chamada à API Gemini: {e}")


if __name__ == "__main__":
    main()
