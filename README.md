# mcp-dados-br

[![CI](https://github.com/lucianoon/mcp-dados-br/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianoon/mcp-dados-br/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-dados-br?color=2e7d32&label=PyPI)](https://pypi.org/project/mcp-dados-br/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green.svg)](LICENSE)

*[English version](README.en.md)*

Servidor **MCP (Model Context Protocol)** que expõe dados públicos brasileiros como ferramentas para assistentes de IA: [Claude Desktop](https://claude.ai/download), Claude Code, Cursor e qualquer cliente MCP.

<!-- mcp-name: io.github.lucianoon/mcp-dados-br -->

## Instalação

A forma mais simples, sem instalar nada permanentemente:

```bash
uvx mcp-dados-br
```

Configuração no Claude Desktop:

```json
{
  "mcpServers": {
    "dados-brasil": {
      "command": "uvx",
      "args": ["mcp-dados-br"]
    }
  }
}
```

Ou no Claude Code:

```bash
claude mcp add dados-brasil -- uvx mcp-dados-br
```

### A partir do código-fonte

```bash
git clone https://github.com/lucianoon/mcp-dados-br
cd mcp-dados-br
uv sync
```

## Ferramentas disponíveis

| Fonte | Tools | Descrição |
|---|---|---|
| IBGE/SIDRA | `ibge_populacao`, `ibge_pib`, `ibge_municipios`, `ibge_sidra` | População, PIB, busca de municípios e consulta genérica a qualquer agregado SIDRA |
| Banco Central | `bcb_serie`, `bcb_cambio`, `bcb_moedas`, `bcb_focus` | Séries SGS com atalhos nomeados (`selic`, `ipca`, `cdi`...), cotações PTAX, lista de moedas e expectativas do Boletim Focus |
| INMET | `inmet_estacoes`, `inmet_dados` | Lista de estações meteorológicas e dados horários observados (dados observacionais exigem token) |
| Câmara dos Deputados | `camara_deputados`, `camara_detalhes_deputado`, `camara_proposicoes`, `camara_votacoes_proposicao`, `camara_agenda`, `camara_tramitacao` | Deputados, proposições, votações, agenda e tramitações |
| Senado Federal | `senado_senadores`, `senado_materias`, `senado_votacoes` | Senadores em exercício, matérias legislativas e votações nominais com placar |

Todas as fontes são APIs oficiais abertas — nenhuma chave de API necessária,
exceto os dados horários do INMET (veja abaixo).

## Configuração

### Claude Desktop / Cursor

Adicione ao arquivo de configuração (`claude_desktop_config.json` ou `mcp.json`):

```json
{
  "mcpServers": {
    "mcp-dados-br": {
      "command": "uv",
      "args": ["run", "--directory", "/caminho/para/mcp-dados-br", "mcp-dados-br"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add mcp-dados-br -- uv run --directory /caminho/para/mcp-dados-br mcp-dados-br
```

## Token opcional do INMET

A listagem de estações (`inmet_estacoes`) é aberta. Já os **dados horários
observados** (`inmet_dados`) exigem um token fornecido pelo INMET — solicite em
[portal.inmet.gov.br](https://portal.inmet.gov.br) e configure a variável de
ambiente no cliente MCP:

```json
{
  "mcpServers": {
    "mcp-dados-br": {
      "command": "uv",
      "args": ["run", "--directory", "/caminho/para/mcp-dados-br", "mcp-dados-br"],
      "env": { "INMET_TOKEN": "seu-token" }
    }
  }
}
```

Sem o token, as demais 18 ferramentas funcionam normalmente.

## Transporte streamable-http

Além do stdio padrão, o servidor pode rodar em modo HTTP remoto:

```bash
MCP_TRANSPORTE=streamable-http MCP_PORTA=8000 mcp-dados-br
```

Aponte clientes para `http://localhost:8000/mcp`. Útil para Docker ou
compartilhar o servidor na rede local. Por padrão o servidor escuta só em
`127.0.0.1`; defina `MCP_HOST=0.0.0.0` para aceitar conexões de outras máquinas
(a imagem Docker já faz isso).

| Variável | Padrão | Função |
|---|---|---|
| `MCP_TRANSPORTE` | `stdio` | `streamable-http` liga o modo HTTP |
| `MCP_HOST` | `127.0.0.1` | Interface de escuta (`0.0.0.0` na imagem Docker) |
| `MCP_PORTA` | `8000` | Porta HTTP |
| `MCP_AUTH_TOKEN` | vazio | Se definido, exige `Authorization: Bearer <token>` em toda requisição |

### Autenticação (bearer opcional)

> **Risco:** sem `MCP_AUTH_TOKEN`, o modo HTTP não tem autenticação. Escutando
> em `0.0.0.0` (como na imagem Docker), qualquer pessoa que alcance a porta pode
> chamar as 19 tools, consumir a sua cota nas APIs públicas e usar o seu
> `INMET_TOKEN`. O servidor registra um aviso no log quando sobe assim. Não
> publique a porta na internet sem token e prefira um proxy reverso com TLS na
> frente: sobre HTTP puro o token trafega em texto claro.

Gere um token longo e aleatório e passe-o ao servidor:

```bash
export MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
MCP_TRANSPORTE=streamable-http mcp-dados-br
```

Requisições sem o cabeçalho, com outro esquema ou com token diferente recebem
`401` com `WWW-Authenticate: Bearer`. A comparação usa `secrets.compare_digest`
(tempo constante). No cliente, envie o cabeçalho, por exemplo no Claude Code:

```bash
claude mcp add --transport http dados-brasil http://localhost:8000/mcp \
  --header "Authorization: Bearer $MCP_AUTH_TOKEN"
```

Em stdio o token não se aplica: o processo só fala com o cliente que o iniciou.

### Docker

```bash
docker build -t mcp-dados-br .
docker run -p 8000:8000 \
  -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" \
  -e INMET_TOKEN=seu-token \
  mcp-dados-br
```

Para uso só na própria máquina, publique a porta apenas no loopback:
`docker run -p 127.0.0.1:8000:8000 mcp-dados-br`.

## Exemplos de uso

Depois de configurar, pergunte diretamente ao assistente:

- "Qual foi o IPCA dos últimos 6 meses?"
- "O que o mercado espera para a Selic nas próximas reuniões?" (Boletim Focus)
- "Quem são os deputados federais de Minas Gerais do partido X?"
- "Qual a população de São Paulo em 2022? E o PIB?"
- "Como está o dólar PTAX nos últimos dias?"
- "Busque projetos de lei de 2025 sobre saúde mental"
- "O que está na agenda da Câmara esta semana?"
- "Como o Senado votou a PEC X? Qual o placar?"
- "Quem são os senadores de Minas Gerais?"
- "Quais estações automáticas do INMET existem no Amazonas?"

## Desenvolvimento

```bash
uv sync --dev
uv run pytest              # suíte unitária (mocks)
uv run pytest -m integration   # consulta as APIs reais
uv run ruff check .
uv run mypy src
```

Logs de depuração: configure `MCP_LOG_LEVEL=DEBUG` no cliente MCP.
Para contribuir, leia o [CONTRIBUTING.md](CONTRIBUTING.md).

### Arquitetura

```
src/mcp_dados_br/
├── server.py        # Servidor MCP, registro das tools e escolha do transporte
├── auth.py          # Middleware ASGI de autenticação bearer (modo HTTP)
├── validacao.py     # Validação dos argumentos das tools (UF, moeda, datas, limites)
├── saida.py         # Resultado com texto + structuredContent
├── http.py          # Cliente HTTP compartilhado, retry e tratamento de erros
├── payload.py       # Leitura defensiva das respostas das APIs (fonte e campo no erro)
├── cache.py         # Cache TTL em memória para as respostas das APIs
└── tools/
    ├── ibge.py      # SIDRA v3 + localidades v1
    ├── bcb.py       # SGS + Olinda (PTAX e Boletim Focus)
    ├── inmet.py     # Estações e dados observacionais
    ├── camara.py    # Dados Abertos da Câmara v2
    └── senado.py    # Dados Abertos do Senado (LegisSaber)
```

- Dois transportes: stdio (padrão dos clientes desktop) e streamable-http
  (Docker/rede), este com autenticação bearer opcional via `MCP_AUTH_TOKEN`
- Validação de entrada antes de montar qualquer URL: UF entre as 27 siglas,
  moeda ISO 4217 de 3 letras, datas ISO, códigos IBGE/SIDRA numéricos, IDs
  positivos e limites de `dias`/`ultimas`. Os limites também aparecem no
  `inputSchema` das tools, e o erro chega ao cliente MCP dizendo o que foi
  recebido e o que é aceito
- Cache TTL de 10 minutos por requisição idêntica, com chave inequívoca (JSON
  ordenado de URL e parâmetros)
- Retry automático em falhas de rede e em `429`/`502`/`503`/`504`
- Mudança de formato numa API upstream (campo renomeado, tipo trocado) vira
  erro da tool (`isError: true`) com a fonte e o campo, ex.:
  `Resposta inesperada de BCB/PTAX: campo 'cotacaoCompra' ausente`
- Saídas formatadas como texto legível pelo modelo; `bcb_serie`, `bcb_cambio` e
  `camara_deputados` também devolvem `structuredContent` com `outputSchema`
  (datas ISO, valores numéricos), mantendo o texto como fallback
- User-Agent com a versão instalada do pacote

## Roadmap

- [x] v0.2 — INMET (estações + observacional com token) e Boletim Focus
- [x] v0.3 — Agenda da Câmara, transporte streamable-http e testes de integração agendados no CI
- [x] v0.4 — Tramitações, atalhos nomeados no SGS, imagem Docker
- [x] v0.5 — Publicação no PyPI (`uvx mcp-dados-br`), MCP Registry e Smithery
- [x] v0.6 — Validação de entrada, autenticação bearer no modo HTTP e saída estruturada
- [ ] DOU: busca no Diário Oficial da União (aguardando API pública estável)
- [ ] TSE: resultados eleitorais

## Licença

MIT
