"""
Agente de busca no Diário Oficial da União (INLABS).

Baixa as edições do dia (seções configuradas em config.py) e faz DUAS
checagens independentes sobre o mesmo conteúdo baixado (um único
login/download serve para as duas):

  1. Busca por nome (NOMES_BUSCA) em qualquer publicação — relatório e
     notificação em relatorios/nome/.
  2. (Opcional) Busca por convocação/nomeação de um órgão específico
     (ORGAOS_BUSCA + TIPOS_ATO, ex.: IFAM) — de qualquer candidato, não
     só o seu nome — relatório e notificação em relatorios/convocacoes/.
     Desativada se ORGAOS_BUSCA/TIPOS_ATO estiverem vazios no .env.

Uso manual:
    python buscar_nome_dou.py                        (hoje)
    python buscar_nome_dou.py AAAA-MM-DD              (um dia específico)
    python buscar_nome_dou.py AAAA-MM-DD AAAA-MM-DD   (intervalo de datas, inclusive)

Sem argumento, usa a data de hoje. Se já houver relatório de sucesso de
hoje, a execução automática não repete o processo (só faz login/download
de novo se a tentativa anterior tiver falhado). Pensado para rodar de
hora em hora pelo Agendador de Tarefas do Windows (ver README.md).
"""

import html
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from config import (
    CONVOCACOES_ATIVADO,
    INLABS_EMAIL,
    INLABS_SENHA,
    NOMES_BUSCA,
    ORGAOS_BUSCA,
    SECOES_DOU,
    TIPOS_ATO,
)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
RELATORIOS_DIR = BASE_DIR / "relatorios"
RELATORIOS_NOME_DIR = RELATORIOS_DIR / "nome"
RELATORIOS_CONVOCACOES_DIR = RELATORIOS_DIR / "convocacoes"

URL_LOGIN = "https://inlabs.in.gov.br/logar.php"
URL_DOWNLOAD = "https://inlabs.in.gov.br/index.php?p="


def limpar_html(texto: str) -> str:
    """Remove tags HTML soltas (comuns no texto do INLABS), preservando as
    quebras de parágrafo originais (<p>, <br>) para leitura no relatório."""
    texto = re.sub(r"</p\s*>", "\n\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<p[^>]*>", "\n\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


def paragrafos(texto_limpo: str) -> list[str]:
    """Divide um texto já limpo em parágrafos não vazios."""
    return [p.strip() for p in texto_limpo.split("\n\n") if p.strip()]


def normalizar(texto: str) -> str:
    """Maiúsculas e sem acentuação, para comparação tolerante."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.upper()


def login(sessao: requests.Session) -> str:
    payload = {"email": INLABS_EMAIL, "password": INLABS_SENHA}
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resposta = sessao.request("POST", URL_LOGIN, data=payload, headers=headers, timeout=30)
    if "manuten" in resposta.text.lower() and not sessao.cookies.get("inlabs_session_cookie"):
        raise RuntimeError(
            "O site do INLABS está em manutenção no momento. Tente de novo mais tarde."
        )
    cookie = sessao.cookies.get("inlabs_session_cookie")
    if not cookie:
        raise RuntimeError(
            "Falha ao obter cookie de sessão do INLABS. Verifique email/senha em config.py "
            "(ou o site pode estar em manutenção — tente de novo mais tarde)."
        )
    return cookie


def baixar_secoes(sessao: requests.Session, cookie: str, data_completa: str, destino: Path):
    destino.mkdir(parents=True, exist_ok=True)
    arquivos_baixados = []
    for secao in SECOES_DOU:
        nome_arquivo = f"{data_completa}-{secao}.zip"
        url = URL_DOWNLOAD + data_completa + "&dl=" + nome_arquivo
        headers = {"Cookie": f"inlabs_session_cookie={cookie}", "origem": "736372697074"}
        try:
            resposta = sessao.get(url, headers=headers, timeout=60)
        except requests.exceptions.RequestException as exc:
            print(f"Erro de conexão ao baixar {secao} ({data_completa}): {exc}")
            continue
        if resposta.status_code == 200 and resposta.content[:2] == b"PK":
            caminho_zip = destino / nome_arquivo
            caminho_zip.write_bytes(resposta.content)
            arquivos_baixados.append(caminho_zip)
            print(f"Baixado: {nome_arquivo}")
        elif resposta.status_code == 200 and b"manuten" in resposta.content[:2000].lower():
            print(f"INLABS em manutenção ao tentar baixar {secao} ({data_completa}).")
        else:
            print(f"Sem edição disponível para {secao} ({data_completa}): HTTP {resposta.status_code}")
    return arquivos_baixados


def trecho_contexto(texto: str, termo_normalizado: str, janela: int = 120) -> str:
    texto_norm = normalizar(texto)
    idx = texto_norm.find(termo_normalizado)
    if idx == -1:
        return ""
    inicio = max(0, idx - janela)
    fim = min(len(texto), idx + len(termo_normalizado) + janela)
    return "..." + texto[inicio:fim].replace("\n", " ").strip() + "..."


def classificar_convocacao(texto: str) -> dict | None:
    """Retorna os termos casados (órgão + tipo de ato) se o texto for uma
    convocação/nomeação de ORGAOS_BUSCA, ou None se não for."""
    texto_norm = normalizar(texto)

    orgao_casado = next((o for o in ORGAOS_BUSCA if normalizar(o) in texto_norm), None)
    if not orgao_casado:
        return None

    tipo_casado = next((t for t in TIPOS_ATO if normalizar(t) in texto_norm), None)
    if not tipo_casado:
        return None

    return {"orgao": orgao_casado, "tipo_ato": tipo_casado}


def buscar_em_zip(caminho_zip: Path, secao: str) -> dict[str, list[dict]]:
    """Varre um zip uma única vez e roda as duas checagens (nome e
    convocação) sobre o mesmo texto extraído — evita reprocessar o XML
    duas vezes. Um erro numa checagem não afeta a outra."""
    ocorrencias_nome: list[dict] = []
    ocorrencias_convocacao: list[dict] = []

    with zipfile.ZipFile(caminho_zip) as z:
        for nome_interno in z.namelist():
            if not nome_interno.lower().endswith(".xml"):
                continue
            with z.open(nome_interno) as f:
                conteudo = f.read()
            try:
                raiz = ET.fromstring(conteudo)
            except ET.ParseError:
                continue
            partes = [e.text.strip() for e in raiz.iter() if e.text and e.text.strip()]
            texto = "\n".join(partes)
            texto_norm = normalizar(texto)
            atributos = dict(raiz.attrib)
            titulo = atributos.get("name") or atributos.get("title") or nome_interno
            identifica = atributos.get("idOficio") or atributos.get("numeroDou") or ""

            try:
                for nome_busca in NOMES_BUSCA:
                    termo = normalizar(nome_busca)
                    if termo in texto_norm:
                        ocorrencias_nome.append(
                            {
                                "secao": secao,
                                "arquivo": nome_interno,
                                "nome_buscado": nome_busca,
                                "titulo": titulo,
                                "identifica": identifica,
                                "trecho": trecho_contexto(texto, termo),
                                "texto_completo": texto,
                            }
                        )
            except Exception as exc:  # isola a checagem de nome da de convocação
                print(f"(Aviso: erro na checagem de nome em {nome_interno}: {exc})")

            if CONVOCACOES_ATIVADO:
                try:
                    resultado = classificar_convocacao(texto)
                    if resultado:
                        ocorrencias_convocacao.append(
                            {
                                "secao": secao,
                                "arquivo": nome_interno,
                                "orgao": resultado["orgao"],
                                "tipo_ato": resultado["tipo_ato"],
                                "titulo": titulo,
                                "identifica": identifica,
                                "trecho": trecho_contexto(texto, normalizar(resultado["tipo_ato"])),
                                "texto_completo": texto,
                            }
                        )
                except Exception as exc:  # isola a checagem de convocação da de nome
                    print(f"(Aviso: erro na checagem de convocação em {nome_interno}: {exc})")

    return {"nome": ocorrencias_nome, "convocacoes": ocorrencias_convocacao}


# ---------------------------------------------------------------------------
# Relatórios: busca por nome
# ---------------------------------------------------------------------------

def gerar_relatorio_nome(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_NOME_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_NOME_DIR / f"{data_completa}.txt"
    linhas = [f"Relatório de busca no DOU - {data_completa}", "=" * 50, ""]
    if not ocorrencias:
        linhas.append("Nenhuma ocorrência encontrada nas seções: " + ", ".join(SECOES_DOU))
    else:
        linhas.append(f"{len(ocorrencias)} ocorrência(s) encontrada(s):\n")
        for i, oc in enumerate(ocorrencias, 1):
            linhas.append(f"[{i}] Seção {oc['secao']} - {oc['arquivo']}")
            linhas.append(f"    Nome buscado: {oc['nome_buscado']}")
            titulo_linha = f"{oc['titulo']} {oc['identifica']}".strip()
            linhas.append(f"    Título/identificação: {titulo_linha}")
            linhas.append(f"    Trecho: {oc['trecho']}")
            linhas.append("    Texto completo da matéria:")
            linhas.append("    " + "-" * 46)
            for linha_texto in limpar_html(oc["texto_completo"]).splitlines():
                linhas.append(f"    {linha_texto}")
            linhas.append("    " + "-" * 46)
            linhas.append("")
    caminho_relatorio.write_text("\n".join(linhas), encoding="utf-8")
    return caminho_relatorio


def destacar_nome(texto_limpo: str, nome_busca: str) -> str:
    """Escapa o HTML e envolve as ocorrências do nome buscado em <mark>."""
    texto_escapado = html.escape(texto_limpo)
    padrao = re.compile(re.escape(html.escape(nome_busca)), re.IGNORECASE)
    return padrao.sub(lambda m: f"<mark>{m.group(0)}</mark>", texto_escapado)


def _pagina_html(titulo_pagina: str, subtitulo: str, corpo: str) -> str:
    """Template HTML compartilhado pelos dois tipos de relatório."""
    return f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>{html.escape(titulo_pagina)}</title>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f5f5f4;
    --fg: #1c1c1c;
    --card-bg: #ffffff;
    --border: #dddddd;
    --accent: #0a5c36;
    --mark-bg: #fff176;
    --muted: #666666;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #1a1a1a;
      --fg: #eaeaea;
      --card-bg: #262626;
      --border: #3a3a3a;
      --accent: #6fcf97;
      --mark-bg: #8a6d00;
      --muted: #a0a0a0;
    }}
  }}
  body {{
    background: var(--bg);
    color: var(--fg);
    font-family: Segoe UI, Arial, sans-serif;
    margin: 0;
    padding: 24px;
    line-height: 1.5;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitulo {{ color: var(--muted); margin-top: 0; margin-bottom: 24px; }}
  .resumo, .vazio {{ font-weight: 600; margin-bottom: 20px; }}
  .ocorrencia {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 20px;
  }}
  .ocorrencia h2 {{
    font-size: 1.05rem;
    color: var(--accent);
    margin-top: 0;
  }}
  .ocorrencia .arquivo {{
    font-weight: normal;
    color: var(--muted);
    font-size: 0.85rem;
  }}
  .meta {{ margin: 4px 0; font-size: 0.9rem; }}
  .texto-dou {{
    margin-top: 14px;
    max-height: 520px;
    overflow-y: auto;
    padding: 4px 12px 4px 4px;
    font-family: "Times New Roman", Georgia, serif;
    font-size: 1rem;
  }}
  .texto-dou p {{
    text-align: justify;
    text-indent: 2em;
    margin: 0 0 0.8em 0;
    hyphens: auto;
  }}
  mark {{
    background: var(--mark-bg);
    color: inherit;
    padding: 0 2px;
    border-radius: 2px;
  }}
</style>
</head>
<body>
  <h1>{html.escape(titulo_pagina)}</h1>
  <p class="subtitulo">{html.escape(subtitulo)}</p>
  {corpo}
</body>
</html>
"""


def gerar_relatorio_nome_html(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_NOME_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_NOME_DIR / f"{data_completa}.html"

    if not ocorrencias:
        corpo = (
            '<p class="vazio">Nenhuma ocorrência encontrada nas seções: '
            f'{html.escape(", ".join(SECOES_DOU))}.</p>'
        )
    else:
        blocos = []
        for i, oc in enumerate(ocorrencias, 1):
            titulo_linha = html.escape(f"{oc['titulo']} {oc['identifica']}".strip())
            paragrafos_html = "".join(
                f"<p>{destacar_nome(p, oc['nome_buscado'])}</p>"
                for p in paragrafos(limpar_html(oc["texto_completo"]))
            )
            blocos.append(f"""
    <article class="ocorrencia">
      <h2>[{i}] Seção {html.escape(oc['secao'])} <span class="arquivo">{html.escape(oc['arquivo'])}</span></h2>
      <p class="meta"><strong>Nome buscado:</strong> {html.escape(oc['nome_buscado'])}</p>
      <p class="meta"><strong>Título/identificação:</strong> {titulo_linha}</p>
      <div class="texto-dou">{paragrafos_html}</div>
    </article>""")
        corpo = f'<p class="resumo">{len(ocorrencias)} ocorrência(s) encontrada(s).</p>' + "".join(blocos)

    caminho_relatorio.write_text(
        _pagina_html("Relatório de busca no DOU", f"Data: {data_completa}", corpo),
        encoding="utf-8",
    )
    return caminho_relatorio


# ---------------------------------------------------------------------------
# Relatórios: convocações/nomeações de um órgão específico
# ---------------------------------------------------------------------------

def gerar_relatorio_convocacoes(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_CONVOCACOES_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_CONVOCACOES_DIR / f"{data_completa}.txt"
    linhas = [f"Relatório de convocações/nomeações - {data_completa}", "=" * 50, ""]
    if not ocorrencias:
        linhas.append("Nenhuma convocação/nomeação encontrada nas seções: " + ", ".join(SECOES_DOU))
    else:
        linhas.append(f"{len(ocorrencias)} documento(s) encontrado(s):\n")
        for i, oc in enumerate(ocorrencias, 1):
            linhas.append(f"[{i}] Seção {oc['secao']} - {oc['arquivo']}")
            linhas.append(f"    Órgão: {oc['orgao']}")
            linhas.append(f"    Tipo de ato: {oc['tipo_ato']}")
            titulo_linha = f"{oc['titulo']} {oc['identifica']}".strip()
            linhas.append(f"    Título/identificação: {titulo_linha}")
            linhas.append(f"    Trecho: {oc['trecho']}")
            linhas.append("    Texto completo da matéria:")
            linhas.append("    " + "-" * 46)
            for linha_texto in limpar_html(oc["texto_completo"]).splitlines():
                linhas.append(f"    {linha_texto}")
            linhas.append("    " + "-" * 46)
            linhas.append("")
    caminho_relatorio.write_text("\n".join(linhas), encoding="utf-8")
    return caminho_relatorio


def destacar_termos(texto_limpo: str, termos: list[str]) -> str:
    """Escapa o HTML e envolve as ocorrências de vários termos em <mark>."""
    texto_escapado = html.escape(texto_limpo)
    for termo in termos:
        padrao = re.compile(re.escape(html.escape(termo)), re.IGNORECASE)
        texto_escapado = padrao.sub(lambda m: f"<mark>{m.group(0)}</mark>", texto_escapado)
    return texto_escapado


def gerar_relatorio_convocacoes_html(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_CONVOCACOES_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_CONVOCACOES_DIR / f"{data_completa}.html"

    if not ocorrencias:
        corpo = (
            '<p class="vazio">Nenhuma convocação/nomeação encontrada nas seções: '
            f'{html.escape(", ".join(SECOES_DOU))}.</p>'
        )
    else:
        blocos = []
        for i, oc in enumerate(ocorrencias, 1):
            titulo_linha = html.escape(f"{oc['titulo']} {oc['identifica']}".strip())
            paragrafos_html = "".join(
                f"<p>{destacar_termos(p, [oc['orgao'], oc['tipo_ato']])}</p>"
                for p in paragrafos(limpar_html(oc["texto_completo"]))
            )
            blocos.append(f"""
    <article class="ocorrencia">
      <h2>[{i}] Seção {html.escape(oc['secao'])} <span class="arquivo">{html.escape(oc['arquivo'])}</span></h2>
      <p class="meta"><strong>Órgão:</strong> {html.escape(oc['orgao'])}</p>
      <p class="meta"><strong>Tipo de ato:</strong> {html.escape(oc['tipo_ato'])}</p>
      <p class="meta"><strong>Título/identificação:</strong> {titulo_linha}</p>
      <div class="texto-dou">{paragrafos_html}</div>
    </article>""")
        corpo = f'<p class="resumo">{len(ocorrencias)} documento(s) encontrado(s).</p>' + "".join(blocos)

    caminho_relatorio.write_text(
        _pagina_html("Convocações/Nomeações", f"Data: {data_completa}", corpo),
        encoding="utf-8",
    )
    return caminho_relatorio


def registrar_falha(motivo: str) -> Path:
    """Registra uma falha de execução num log único (não sobrescreve relatórios de dias)."""
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
    caminho = RELATORIOS_DIR / "falhas.log"
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    with caminho.open("a", encoding="utf-8") as f:
        f.write(f"[{agora}] {motivo}\n")
    return caminho


def notificar_windows(titulo: str, mensagem: str, app_id: str = "Agente INLABS"):
    try:
        import winotify
        from winotify import Notification, audio

        # scenario="reminder" faz a notificação ficar fixa na tela até o
        # usuário clicar em dispensar, em vez de sumir sozinha
        if 'scenario="reminder"' not in winotify.TEMPLATE:
            winotify.TEMPLATE = winotify.TEMPLATE.replace(
                '<toast {launch} duration="{duration}">',
                '<toast {launch} duration="{duration}" scenario="reminder">',
            )

        toast = Notification(
            app_id=app_id,
            title=titulo,
            msg=mensagem,
            duration="long",
        )
        # por padrão o winotify cria notificações silenciosas; aqui tocamos
        # um som de alerta (uma vez, sem repetir)
        toast.set_audio(audio.LoopingAlarm2, loop=False)
        toast.show()
    except Exception as exc:  # notificação é best-effort, não deve derrubar o script
        print(f"(Aviso: não foi possível exibir notificação do Windows: {exc})")


def processar_dia(sessao: requests.Session, cookie: str, data_completa: str) -> dict[str, list[dict]]:
    """Baixa, varre e gera os relatórios de um único dia (nome e, se
    ativado, convocações). Retorna {"nome": [...], "convocacoes": [...]}.

    Erros inesperados aqui (zip corrompido, etc.) não derrubam o processamento
    dos outros dias de um intervalo — ficam registrados em falhas.log."""
    destino_dia = DOWNLOADS_DIR / data_completa
    try:
        arquivos = baixar_secoes(sessao, cookie, data_completa, destino_dia)
    except requests.exceptions.RequestException as exc:
        registrar_falha(f"[{data_completa}] falha de conexão ao baixar seções: {exc}")
        print(f"[{data_completa}] Falha de conexão, pulando este dia.")
        shutil.rmtree(destino_dia, ignore_errors=True)
        return {"nome": [], "convocacoes": []}

    if not arquivos:
        print(f"[{data_completa}] Nenhum arquivo disponível (sem edição publicada nesse dia).")
        gerar_relatorio_nome(data_completa, [])
        gerar_relatorio_nome_html(data_completa, [])
        if CONVOCACOES_ATIVADO:
            gerar_relatorio_convocacoes(data_completa, [])
            gerar_relatorio_convocacoes_html(data_completa, [])
        shutil.rmtree(destino_dia, ignore_errors=True)
        return {"nome": [], "convocacoes": []}

    ocorrencias_nome: list[dict] = []
    ocorrencias_convocacao: list[dict] = []
    for caminho_zip in arquivos:
        secao = caminho_zip.stem.split("-")[-1]
        print(f"[{data_completa}] Varrendo {caminho_zip.name}...")
        try:
            resultado = buscar_em_zip(caminho_zip, secao)
            ocorrencias_nome.extend(resultado["nome"])
            ocorrencias_convocacao.extend(resultado["convocacoes"])
        except zipfile.BadZipFile as exc:
            registrar_falha(f"[{data_completa}] arquivo {caminho_zip.name} corrompido/incompleto: {exc}")
            print(f"[{data_completa}] Aviso: {caminho_zip.name} parece corrompido, pulando esse arquivo.")

    relatorio = gerar_relatorio_nome(data_completa, ocorrencias_nome)
    relatorio_html = gerar_relatorio_nome_html(data_completa, ocorrencias_nome)
    print(f"[{data_completa}] Relatório (nome) salvo em: {relatorio}")
    print(f"[{data_completa}] Relatório (nome, HTML) salvo em: {relatorio_html}")
    if ocorrencias_nome:
        print(f"[{data_completa}] {len(ocorrencias_nome)} ocorrência(s) de nome encontrada(s).")
    else:
        print(f"[{data_completa}] Nenhuma ocorrência do(s) nome(s) configurado(s).")

    if CONVOCACOES_ATIVADO:
        relatorio_c = gerar_relatorio_convocacoes(data_completa, ocorrencias_convocacao)
        relatorio_c_html = gerar_relatorio_convocacoes_html(data_completa, ocorrencias_convocacao)
        print(f"[{data_completa}] Relatório (convocações) salvo em: {relatorio_c}")
        print(f"[{data_completa}] Relatório (convocações, HTML) salvo em: {relatorio_c_html}")
        if ocorrencias_convocacao:
            print(f"[{data_completa}] {len(ocorrencias_convocacao)} convocação(ões)/nomeação(ões) encontrada(s).")
        else:
            print(f"[{data_completa}] Nenhuma convocação/nomeação encontrada.")

    # limpa os arquivos baixados (zips), os relatórios já guardam o essencial
    shutil.rmtree(destino_dia, ignore_errors=True)
    return {"nome": ocorrencias_nome, "convocacoes": ocorrencias_convocacao}


def intervalo_de_datas(data_inicio: str, data_fim: str) -> list[str]:
    inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    fim = datetime.strptime(data_fim, "%Y-%m-%d").date()
    if fim < inicio:
        inicio, fim = fim, inicio
    dias = []
    atual = inicio
    while atual <= fim:
        dias.append(atual.strftime("%Y-%m-%d"))
        atual += timedelta(days=1)
    return dias


def ja_verificado_hoje(data_completa: str) -> bool:
    """Já existe relatório de sucesso para essa data (gerado só quando o dia foi processado)."""
    nome_ok = (RELATORIOS_NOME_DIR / f"{data_completa}.txt").exists()
    if not CONVOCACOES_ATIVADO:
        return nome_ok
    convocacoes_ok = (RELATORIOS_CONVOCACOES_DIR / f"{data_completa}.txt").exists()
    return nome_ok and convocacoes_ok


def main():
    execucao_automatica_diaria = len(sys.argv) == 1

    if len(sys.argv) >= 3:
        datas = intervalo_de_datas(sys.argv[1], sys.argv[2])
        print(f"Buscando no intervalo de {datas[0]} até {datas[-1]} ({len(datas)} dia(s))...")
    elif len(sys.argv) == 2:
        datas = [sys.argv[1]]
    else:
        datas = [date.today().strftime("%Y-%m-%d")]

    if execucao_automatica_diaria and ja_verificado_hoje(datas[0]):
        print(f"Já verificado hoje ({datas[0]}) com sucesso — nada a fazer.")
        return

    sessao = requests.Session()
    print(f"Autenticando no INLABS como {INLABS_EMAIL}...")
    try:
        cookie = login(sessao)
    except requests.exceptions.RequestException as exc:
        registrar_falha(f"falha de conexão ao fazer login ({type(exc).__name__}: {exc})")
        print(f"Falha de conexão ao fazer login: {exc}")
        return
    except RuntimeError as exc:
        registrar_falha(str(exc))
        print(str(exc))
        return

    resultados_por_dia = {}
    for data_completa in datas:
        resultados_por_dia[data_completa] = processar_dia(sessao, cookie, data_completa)

    # --- resumo e notificação: busca por nome ---
    ocorrencias_nome_todas = {d: r["nome"] for d, r in resultados_por_dia.items()}
    total_nome = sum(len(v) for v in ocorrencias_nome_todas.values())
    dias_com_nome = [d for d, v in ocorrencias_nome_todas.items() if v]

    if len(datas) > 1:
        print(f"\nResumo (nome): {total_nome} ocorrência(s) em {len(dias_com_nome)} dia(s) de {len(datas)} pesquisado(s).")
        if dias_com_nome:
            print("Dias com ocorrência: " + ", ".join(dias_com_nome))

    if total_nome:
        nomes = ", ".join(sorted({
            oc["nome_buscado"] for ocorrencias in ocorrencias_nome_todas.values() for oc in ocorrencias
        }))
        if len(datas) == 1:
            mensagem = f"{total_nome} ocorrência(s) de '{nomes}' em {datas[0]}. Veja o relatório."
        else:
            mensagem = (
                f"{total_nome} ocorrência(s) de '{nomes}' em {len(dias_com_nome)} dia(s) "
                f"({datas[0]} a {datas[-1]}). Veja os relatórios."
            )
        notificar_windows("Seu nome apareceu no Diário Oficial!", mensagem)

    # --- resumo e notificação: convocações/nomeações ---
    if CONVOCACOES_ATIVADO:
        ocorrencias_conv_todas = {d: r["convocacoes"] for d, r in resultados_por_dia.items()}
        total_conv = sum(len(v) for v in ocorrencias_conv_todas.values())
        dias_com_conv = [d for d, v in ocorrencias_conv_todas.items() if v]

        if len(datas) > 1:
            print(f"Resumo (convocações): {total_conv} documento(s) em {len(dias_com_conv)} dia(s) de {len(datas)} pesquisado(s).")
            if dias_com_conv:
                print("Dias com convocação/nomeação: " + ", ".join(dias_com_conv))

        if total_conv:
            if len(datas) == 1:
                mensagem = f"{total_conv} convocação(ões)/nomeação(ões) em {datas[0]}. Veja o relatório."
            else:
                mensagem = (
                    f"{total_conv} convocação(ões)/nomeação(ões) em {len(dias_com_conv)} dia(s) "
                    f"({datas[0]} a {datas[-1]}). Veja os relatórios."
                )
            notificar_windows(
                "Convocação/nomeação publicada no DOU!", mensagem, app_id="Agente INLABS Convocações"
            )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # rede de segurança: nunca falhar em silêncio total
        import traceback

        traceback.print_exc()
        try:
            registrar_falha(f"erro inesperado ({type(exc).__name__}: {exc})")
        except Exception:
            pass  # se até o log falhar, não há mais nada a fazer
