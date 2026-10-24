"""Falha (exit 1) se o repositório contiver ativos proprietários ou segredos.

Verifica: extensões proibidas, pastas proibidas e padrões de chave/segredo.
Imagens (.jpg .jpeg .png) só são aceitas dentro de docs/ (diagramas).
"""
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
IGNORAR = {".git", ".venv", "out", "__pycache__", ".pytest_cache", "node_modules"}
EXT_PROIBIDAS = {".onnx", ".pt", ".pth", ".ckpt", ".safetensors", ".zip"}
EXT_IMAGEM = {".jpg", ".jpeg", ".png"}
PASTAS_PROIBIDAS = ("dataset", "modelo_visao")
# Padrões montados por partes para este arquivo não casar consigo mesmo.
PADROES = {
    "chave Google (prefixo " + "AI" + "za)": re.compile("AI" + r"za[0-9A-Za-z_\-]{20,}"),
    "chave privada": re.compile("-----BEGIN [A-Z ]*PRIVATE " + "KEY-----"),
    "GEMINI_API_KEY com valor": re.compile(r"GEMINI_API_KEY\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    "token tipo sk-": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
}


def varrer():
    problemas = []
    for pasta, dirs, arquivos in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in IGNORAR]
        rel_pasta = Path(pasta).relative_to(RAIZ)
        for d in dirs:
            if d.lower().startswith(PASTAS_PROIBIDAS):
                problemas.append(f"pasta proibida: {rel_pasta / d}")
        for nome in arquivos:
            caminho = Path(pasta) / nome
            rel = caminho.relative_to(RAIZ)
            ext = caminho.suffix.lower()
            if ext in EXT_PROIBIDAS:
                problemas.append(f"extensão proibida: {rel}")
            elif ext in EXT_IMAGEM and (not rel.parts or rel.parts[0] != "docs"):
                problemas.append(f"imagem fora de docs/: {rel}")
            if nome == ".env":
                problemas.append(f"arquivo de segredos: {rel}")
            try:
                texto = caminho.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for rotulo, padrao in PADROES.items():
                if padrao.search(texto):
                    problemas.append(f"{rotulo}: {rel}")
    return problemas


def main():
    problemas = varrer()
    if problemas:
        print("verificar_ip: FALHOU")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("verificar_ip: OK (nenhum ativo proibido ou segredo encontrado)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
