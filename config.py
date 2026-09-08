# Configuração do agente de busca no Diário Oficial da União (INLABS)
#
# Credenciais ficam em ".env" (fora do controle de versão), não neste arquivo.
# Use ".env.example" como modelo.

import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent / ".env"


def _carregar_env(caminho: Path) -> None:
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env(_ENV_PATH)

INLABS_EMAIL = os.environ.get("INLABS_EMAIL", "")
INLABS_SENHA = os.environ.get("INLABS_SENHA", "")

if not INLABS_EMAIL or not INLABS_SENHA:
    raise RuntimeError(
        "INLABS_EMAIL/INLABS_SENHA não configurados. Copie .env.example para .env "
        "e preencha suas credenciais."
    )

# Nome(s) a procurar no texto das publicações, separados por ";" no .env.
# Cada item é buscado de forma independente (case-insensitive, sem acentuação).
_NOMES_BUSCA_RAW = os.environ.get("NOMES_BUSCA", "")
NOMES_BUSCA = [nome.strip() for nome in _NOMES_BUSCA_RAW.split(";") if nome.strip()]

if not NOMES_BUSCA:
    raise RuntimeError(
        "NOMES_BUSCA não configurado no .env. Copie .env.example para .env "
        "e preencha o(s) nome(s) a buscar (separados por ';')."
    )

# Seções do Diário Oficial a baixar e varrer, separadas por espaço no .env.
# Opções: DO1 DO2 DO3 DO1E DO2E DO3E
_SECOES_DOU_RAW = os.environ.get("SECOES_DOU", "DO1 DO2 DO3")
SECOES_DOU = _SECOES_DOU_RAW.split()
