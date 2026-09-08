"""
Agente de busca no Diário Oficial da União (INLABS).

Baixa as edições do dia (seções configuradas em config.py), varre o texto
de todas as matérias publicadas e avisa (notificação do Windows + relatório
em arquivo) quando encontra os nomes configurados em NOMES_BUSCA.

Uso manual:
    python buscar_nome_dou.py                        (hoje)
    python buscar_nome_dou.py AAAA-MM-DD              (um dia específico)
    python buscar_nome_dou.py AAAA-MM-DD AAAA-MM-DD   (intervalo de datas, inclusive)

Sem argumento, usa a data de hoje. Pensado para também ser chamado
automaticamente todo dia pelo Agendador de Tarefas do Windows (ver README.md).
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

from config import INLABS_EMAIL, INLABS_SENHA, NOMES_BUSCA, SECOES_DOU

BASE_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
RELATORIOS_DIR = BASE_DIR / "relatorios"

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
    sessao.request("POST", URL_LOGIN, data=payload, headers=headers)
    cookie = sessao.cookies.get("inlabs_session_cookie")
    if not cookie:
        raise RuntimeError(
            "Falha ao obter cookie de sessão do INLABS. Verifique email/senha em config.py."
        )
    return cookie


def baixar_secoes(sessao: requests.Session, cookie: str, data_completa: str, destino: Path):
    destino.mkdir(parents=True, exist_ok=True)
    arquivos_baixados = []
    for secao in SECOES_DOU:
        nome_arquivo = f"{data_completa}-{secao}.zip"
        url = URL_DOWNLOAD + data_completa + "&dl=" + nome_arquivo
        headers = {"Cookie": f"inlabs_session_cookie={cookie}", "origem": "736372697074"}
        resposta = sessao.get(url, headers=headers)
        if resposta.status_code == 200 and resposta.content[:2] == b"PK":
            caminho_zip = destino / nome_arquivo
            caminho_zip.write_bytes(resposta.content)
            arquivos_baixados.append(caminho_zip)
            print(f"Baixado: {nome_arquivo}")
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


def buscar_em_zip(caminho_zip: Path, secao: str) -> list[dict]:
    ocorrencias = []
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

            for nome_busca in NOMES_BUSCA:
                termo = normalizar(nome_busca)
                if termo in texto_norm:
                    ocorrencias.append(
                        {
                            "secao": secao,
                            "arquivo": nome_interno,
                            "nome_buscado": nome_busca,
                            "titulo": atributos.get("name") or atributos.get("title") or nome_interno,
                            "identifica": atributos.get("idOficio") or atributos.get("numeroDou") or "",
                            "trecho": trecho_contexto(texto, termo),
                            "texto_completo": texto,
                        }
                    )
    return ocorrencias


def gerar_relatorio(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_DIR / f"{data_completa}.txt"
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


def gerar_relatorio_html(data_completa: str, ocorrencias: list[dict]) -> Path:
    RELATORIOS_DIR.mkdir(parents=True, exist_ok=True)
    caminho_relatorio = RELATORIOS_DIR / f"{data_completa}.html"

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

    html_final = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>Relatório DOU - {data_completa}</title>
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
  <h1>Relatório de busca no DOU</h1>
  <p class="subtitulo">Data: {data_completa}</p>
  {corpo}
</body>
</html>
"""
    caminho_relatorio.write_text(html_final, encoding="utf-8")
    return caminho_relatorio


def notificar_windows(titulo: str, mensagem: str):
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="Agente INLABS",
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


def processar_dia(sessao: requests.Session, cookie: str, data_completa: str) -> list[dict]:
    """Baixa, varre e gera o relatório de um único dia. Retorna as ocorrências encontradas."""
    destino_dia = DOWNLOADS_DIR / data_completa
    arquivos = baixar_secoes(sessao, cookie, data_completa, destino_dia)

    if not arquivos:
        print(f"[{data_completa}] Nenhum arquivo disponível (sem edição publicada nesse dia).")
        gerar_relatorio(data_completa, [])
        gerar_relatorio_html(data_completa, [])
        shutil.rmtree(destino_dia, ignore_errors=True)
        return []

    todas_ocorrencias = []
    for caminho_zip in arquivos:
        secao = caminho_zip.stem.split("-")[-1]
        print(f"[{data_completa}] Varrendo {caminho_zip.name}...")
        todas_ocorrencias.extend(buscar_em_zip(caminho_zip, secao))

    relatorio = gerar_relatorio(data_completa, todas_ocorrencias)
    relatorio_html = gerar_relatorio_html(data_completa, todas_ocorrencias)
    print(f"[{data_completa}] Relatório salvo em: {relatorio}")
    print(f"[{data_completa}] Relatório (HTML) salvo em: {relatorio_html}")

    if todas_ocorrencias:
        print(f"[{data_completa}] {len(todas_ocorrencias)} ocorrência(s) encontrada(s).")
    else:
        print(f"[{data_completa}] Nenhuma ocorrência do(s) nome(s) configurado(s).")

    # limpa os arquivos baixados (zips), o relatório já guarda o essencial
    shutil.rmtree(destino_dia, ignore_errors=True)
    return todas_ocorrencias


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


def main():
    if len(sys.argv) >= 3:
        datas = intervalo_de_datas(sys.argv[1], sys.argv[2])
        print(f"Buscando no intervalo de {datas[0]} até {datas[-1]} ({len(datas)} dia(s))...")
    elif len(sys.argv) == 2:
        datas = [sys.argv[1]]
    else:
        datas = [date.today().strftime("%Y-%m-%d")]

    sessao = requests.Session()
    print(f"Autenticando no INLABS como {INLABS_EMAIL}...")
    cookie = login(sessao)

    ocorrencias_por_dia = {}
    for data_completa in datas:
        ocorrencias_por_dia[data_completa] = processar_dia(sessao, cookie, data_completa)

    total_ocorrencias = sum(len(v) for v in ocorrencias_por_dia.values())
    dias_com_ocorrencia = [d for d, v in ocorrencias_por_dia.items() if v]

    if len(datas) > 1:
        print(f"\nResumo: {total_ocorrencias} ocorrência(s) em {len(dias_com_ocorrencia)} dia(s) de {len(datas)} pesquisado(s).")
        if dias_com_ocorrencia:
            print("Dias com ocorrência: " + ", ".join(dias_com_ocorrencia))

    if total_ocorrencias:
        nomes = ", ".join(sorted({
            oc["nome_buscado"] for ocorrencias in ocorrencias_por_dia.values() for oc in ocorrencias
        }))
        if len(datas) == 1:
            mensagem = f"{total_ocorrencias} ocorrência(s) de '{nomes}' em {datas[0]}. Veja o relatório."
        else:
            mensagem = (
                f"{total_ocorrencias} ocorrência(s) de '{nomes}' em {len(dias_com_ocorrencia)} dia(s) "
                f"({datas[0]} a {datas[-1]}). Veja os relatórios."
            )
        notificar_windows("Seu nome apareceu no Diário Oficial!", mensagem)


if __name__ == "__main__":
    main()
