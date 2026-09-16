# Agente INLABS — Busca de Nome e Convocações no Diário Oficial

Script que baixa as edições do Diário Oficial da União (via
[INLABS](https://inlabs.in.gov.br)) e faz **duas checagens independentes**
sobre o mesmo conteúdo baixado — um único login/download serve para as
duas, evitando bater duas vezes no INLABS à toa:

1. **Busca por nome**: varre o texto de todas as matérias e avisa quando
   encontra o(s) nome(s) configurado(s).
2. **Convocações/nomeações de um órgão** *(opcional)*: avisa quando sai
   uma convocação ou nomeação de um órgão específico (ex.: IFAM) — de
   **qualquer** candidato, não só o seu nome. Desativa sozinha se você não
   configurar `ORGAOS_BUSCA`/`TIPOS_ATO`.

Cada checagem tem seu próprio relatório e notificação, isolados um do
outro (um erro numa não afeta a outra).

Feito para rodar sozinho, todo dia, sem precisar abrir nada manualmente —
com nova tentativa automática se algo falhar (sem internet, site fora do
ar etc.).

---

## Índice

1. [Como funciona](#como-funciona)
2. [Instalação (primeira vez)](#instalação-primeira-vez)
3. [Configurar suas informações (.env)](#configurar-suas-informações-env)
4. [Rodar manualmente](#rodar-manualmente)
5. [Automatizar](#automatizar)
6. [Onde ficam os resultados](#onde-ficam-os-resultados)
7. [Arquivos do projeto](#arquivos-do-projeto)
8. [Segurança](#segurança)
9. [Solução de problemas](#solução-de-problemas)
10. [Créditos](#créditos)
11. [Licença](#licença)

---

## Como funciona

A cada execução automática (sem data específica), o script primeiro
verifica **se já tem um relatório de hoje com sucesso** — se tiver, encerra
na hora, sem tentar conectar em nada (evita reprocessar à toa, já que a
tarefa roda de hora em hora). Se ainda não tiver:

1. Faz login no INLABS com o e-mail/senha do seu `.env`.
2. Baixa as seções do Diário Oficial do dia (ex.: DO1, DO2, DO3).
3. Abre cada matéria publicada **uma única vez** e roda as duas checagens
   sobre o mesmo texto: nome (`NOMES_BUSCA`) e, se ativado, convocação/
   nomeação de órgão (`ORGAOS_BUSCA` + `TIPOS_ATO`) — a busca ignora
   acentuação e maiúsculas/minúsculas (ex.: "José" e "JOSE" são tratados
   como iguais).
4. Para cada checagem que encontrar alguma ocorrência:
   - dispara uma **notificação do Windows** própria;
   - salva um **relatório** próprio (`relatorios/nome/` ou
     `relatorios/convocacoes/`).
5. Se não achar nada numa checagem, só salva o relatório dela (sem
   notificação) e segue em frente.
6. Apaga os arquivos baixados ao final — só os relatórios ficam guardados.

Se falhar (sem internet, INLABS fora do ar, etc.), nada é salvo como
"sucesso de hoje" — então a próxima execução (1h depois) tenta de novo
automaticamente, até dar certo. Veja mais em
[Solução de problemas](#solução-de-problemas).

## Instalação (primeira vez)

Pré-requisitos: **Python 3** instalado e disponível no PATH do Windows.

```bash
cd INLABS-SEARCH
pip install -r requirements.txt
```

Isso instala:
- `requests` — para baixar os arquivos do INLABS
- `winotify` — para exibir a notificação do Windows

## Configurar suas informações (.env)

Todas as suas informações pessoais ficam em um arquivo `.env` — nunca no
código. Isso torna o script seguro para compartilhar com outras pessoas.

**Passo 1:** copie o arquivo de modelo:

```bash
copy .env.example .env
```

**Passo 2:** abra o `.env` num editor de texto e preencha:

```ini
INLABS_EMAIL=seu_email@dominio.com
INLABS_SENHA=sua_senha

# Nome(s) a procurar. Para mais de um, separe com ";"
NOMES_BUSCA=SEU NOME COMPLETO

# Seções do DOU a varrer, separadas por espaço.
# Opções: DO1 DO2 DO3 DO1E DO2E DO3E
SECOES_DOU=DO1 DO2 DO3

# Checagem extra e OPCIONAL: avisa quando sai uma convocação/nomeação de um
# órgão específico (de QUALQUER candidato, não só o seu nome). Deixe os
# dois vazios pra desativar essa checagem.
ORGAOS_BUSCA=INSTITUTO FEDERAL DE EDUCACAO, CIENCIA E TECNOLOGIA DO AMAZONAS;IFAM
TIPOS_ATO=NOMEAR;NOMEACAO;CONVOCACAO;CONVOCA
```

| Variável | O que é | Exemplo |
|---|---|---|
| `INLABS_EMAIL` | Login cadastrado em inlabs.in.gov.br | `joao@email.com` |
| `INLABS_SENHA` | Senha do INLABS | `minhaSenha123` |
| `NOMES_BUSCA` | Nome(s) a buscar no texto, separados por `;` | `JOAO DA SILVA;J. DA SILVA` |
| `SECOES_DOU` | Seções a baixar, separadas por espaço | `DO1 DO2 DO3` |
| `ORGAOS_BUSCA` *(opcional)* | Termos de órgão para a checagem de convocações, separados por `;` | `IFAM;INSTITUTO FEDERAL...` |
| `TIPOS_ATO` *(opcional)* | Termos de tipo de ato para a checagem de convocações, separados por `;` | `NOMEAR;CONVOCACAO` |

> Seções comuns: **DO1/DO2/DO3** são as edições normais das Seções 1, 2 e 3.
> **DO1E/DO2E/DO3E** são as edições extras. A Seção 2 (`DO2`) concentra a
> maior parte dos atos de pessoal (nomeações, exonerações, concursos).

> A checagem de convocações só roda se **ambos** `ORGAOS_BUSCA` e
> `TIPOS_ATO` tiverem algum valor. Um documento só conta como
> convocação/nomeação se tiver pelo menos um termo de cada lista ao mesmo
> tempo — isso evita falso positivo (ex.: nomeação de outro órgão).

## Rodar manualmente

```bash
python buscar_nome_dou.py
```

Roda para a data de hoje. Para reprocessar um dia específico:

```bash
python buscar_nome_dou.py 2026-05-12
```

Ou um **intervalo de datas** (baixa e varre cada dia, com um único login):

```bash
python buscar_nome_dou.py 2026-05-01 2026-05-31
```

(formato `AAAA-MM-DD`; ao final mostra um resumo com o total de ocorrências
e em quais dias apareceram)

## Automatizar

Duas automações independentes, que podem ser usadas juntas ou separadas.
**Basta dar dois cliques** nos arquivos `.bat` abaixo — nenhum precisa ser
executado como Administrador.

### 1. Rodar periodicamente, com nova tentativa automática

| Arquivo | O que faz |
|---|---|
| [`configurar_horario.bat`](configurar_horario.bat) | Menu para **configurar/alterar** o horário diário ou **remover** o agendamento |

Por padrão a tarefa `AgenteINLABS_BuscaNome` roda **de hora em hora** (não
só uma vez por dia). Isso não significa 24 downloads por dia: o script
verifica, no início de cada execução automática, se **já tem um relatório
de hoje com sucesso** — se já tiver, ele nem tenta logar de novo, só
encerra na hora. Ou seja, na prática:

- Se a primeira tentativa do dia der certo, ele fica quieto o resto do dia.
- Se falhar (ex.: sem internet no momento em que o PC ligou), ele **tenta
  de novo automaticamente na próxima hora**, e assim por diante, até
  conseguir.

Isso resolve o caso comum de "internet caiu bem na hora que o PC ligou,
voltou minutos depois" sem precisar de nenhuma ação manual.

Pra mudar a frequência de tentativa (não recomendado descer de 1h), edite
direto no Agendador de Tarefas ou recrie via linha de comando:

```bash
schtasks /Create /TN "AgenteINLABS_BuscaNome" /TR "\"C:\caminho\para\pythonw.exe\" \"C:\caminho\para\buscar_nome_dou.py\"" /SC HOURLY /MO 1 /F
```

> A opção `[1]` do `configurar_horario.bat` ainda existe caso você prefira
> voltar para um horário fixo único por dia em vez do esquema de hora em
> hora com nova tentativa.

### 2. Rodar ao ligar/logar no computador

Útil como complemento do horário fixo: se o PC estiver desligado no horário
programado, isso garante que a busca rode assim que você ligar.

| Arquivo | O que faz |
|---|---|
| [`ativar_inicializacao.bat`](ativar_inicializacao.bat) | Ativa a execução automática ao ligar/logar |
| [`remover_inicializacao.bat`](remover_inicializacao.bat) | Desativa essa execução |

Por baixo dos panos, isso cria/remove um atalho na pasta **Inicializar**
do seu usuário (`shell:startup`).

### Gerenciar pela linha de comando (opcional)

Se preferir não usar os `.bat`:

```bash
# ver status do agendamento diário
schtasks /Query /TN "AgenteINLABS_BuscaNome" /V /FO LIST

# rodar agora, fora do horário programado
schtasks /Run /TN "AgenteINLABS_BuscaNome"

# remover o agendamento diário
schtasks /Delete /TN "AgenteINLABS_BuscaNome" /F
```

## Onde ficam os resultados

- **`relatorios/nome/AAAA-MM-DD.txt`** e **`.html`** — resultado da busca
  por nome, um relatório por dia (mesmo sem ocorrências). Contém seção,
  arquivo, nome encontrado, um trecho de contexto e o **texto completo**
  de cada matéria. O `.html` destaca o nome em amarelo e tem tema
  claro/escuro automático.
- **`relatorios/convocacoes/AAAA-MM-DD.txt`** e **`.html`** — resultado da
  checagem de convocações/nomeações (se ativada), mesmo formato.
- **`relatorios/falhas.log`** — falhas de execução (sem internet, site em
  manutenção etc.), sem gerar alarme falso.
- **Notificação do Windows** — uma para cada checagem que encontrar algo
  (podem disparar as duas juntas ou só uma), com som de alerta, **fixa na
  tela até você clicar para dispensar**.
- **`downloads/`** — pasta de trabalho temporária; fica vazia entre
  execuções (os arquivos baixados do INLABS são apagados ao final).

## Arquivos do projeto

```
INLABS-SEARCH/
├── .env                      ← suas configurações pessoais (não versionado)
├── .env.example               ← modelo do .env, sem dados reais
├── config.py                  ← carrega o .env, sem dados pessoais
├── buscar_nome_dou.py         ← script principal (as duas checagens)
├── configurar_horario.bat     ← configurar/remover o agendamento diário
├── ativar_inicializacao.bat   ← ativar execução ao ligar o PC
├── remover_inicializacao.bat  ← desativar execução ao ligar o PC
├── requirements.txt           ← dependências Python
├── relatorios/
│   ├── nome/                  ← relatórios da busca por nome (um .txt/.html por dia)
│   ├── convocacoes/           ← relatórios da checagem de convocações (idem)
│   └── falhas.log             ← falhas de execução
└── downloads/                 ← pasta de trabalho temporária
```

## Segurança

- O `.env` guarda sua senha do INLABS em **texto puro**. É necessário para a
  automação funcionar sem interação, mas:
  - nunca é enviado ao git (veja `.gitignore`);
  - não compartilhe esta pasta com o `.env` preenchido;
  - se for enviar o projeto para outra pessoa, mande sem o `.env` — ela cria
    o dela a partir do `.env.example`.
- `config.py` e `buscar_nome_dou.py` **não têm nenhum dado pessoal** —
  são seguros para compartilhar/versionar.

## Solução de problemas

### Sem internet ou site fora do ar

O script foi pensado pra nunca travar/crashar sem deixar rastro: se não
houver conexão (ou o INLABS estiver em manutenção) no momento da execução
automática, ele registra o motivo em `relatorios/falhas.log` e encerra
normalmente — sem notificação de alarme falso, sem relatório de dia
incompleto. Como a tarefa roda de hora em hora e só "desiste" quando já
teve sucesso naquele dia, ele **tenta de novo automaticamente na próxima
hora**, sem precisar de nenhuma ação manual. Se só uma seção (DO1/DO2/DO3)
falhar por conexão, as outras continuam sendo verificadas normalmente.

O script também reconhece a página de manutenção do INLABS (quando o site
volta um "Sistema em Manutenção" em vez do conteúdo esperado) e registra
isso com uma mensagem específica no log, em vez do erro genérico de
login.

**"Falha ao obter cookie de sessão do INLABS"**
E-mail ou senha errados no `.env`. Confira em https://inlabs.in.gov.br se o
login funciona pelo navegador. (Também aparece se o site estiver em
manutenção — nesse caso é só tentar mais tarde.)

**"NOMES_BUSCA não configurado no .env"**
Faltou preencher `NOMES_BUSCA` no `.env` (ou o arquivo `.env` não existe —
copie `.env.example` para `.env`).

**Nenhum arquivo disponível para baixar**
A edição do dia ainda não foi publicada no INLABS (normalmente sai de manhã)
ou é fim de semana/feriado, quando não há publicação.

**A tarefa agendada não rodou**
Confira se o computador estava ligado no horário configurado. Ative também
a execução ao ligar o PC (`ativar_inicializacao.bat`) como reforço. Nas
propriedades da tarefa no Agendador de Tarefas, a tarefa por padrão não
roda com o notebook na bateria — ajuste isso lá se precisar.

**A notificação do Windows não aparece**
Ela só aparece quando há ocorrência do nome. Confira o relatório do dia em
`relatorios/` para ver se rodou e o que encontrou.

## Créditos

O login e o download das edições ([`login()`](buscar_nome_dou.py) e
[`baixar_secoes()`](buscar_nome_dou.py)) são baseados no script de exemplo
oficial disponibilizado pela Imprensa Nacional no repositório
[Imprensa-Nacional/inlabs](https://github.com/Imprensa-Nacional/inlabs)
(`public/python/inlabs-auto-download-xml.py`).

Todo o restante — varredura do texto das matérias, geração dos relatórios
`.txt`/`.html`, notificação com som, configuração via `.env` e a automação
(agendamento diário, execução ao ligar o PC, os `.bat`) — foi desenvolvido
especificamente para este projeto.

## Licença

Este projeto usa **[MIT](LICENSE)** para o trabalho autoral próprio (busca,
relatórios, notificação, automação, `.env`, `.bat`).

> **Atenção:** o repositório de origem
> ([Imprensa-Nacional/inlabs](https://github.com/Imprensa-Nacional/inlabs)),
> de onde vem a parte de login/download, **não declara nenhuma licença**. A
> MIT deste projeto cobre o que foi desenvolvido aqui — não estende nem
> "regulariza" retroativamente a licença do trecho de origem. Veja o arquivo
> [`LICENSE`](LICENSE) para os detalhes dessa ressalva.
