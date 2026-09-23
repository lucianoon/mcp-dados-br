# mcp-dados-br

[![CI](https://github.com/lucianoon/mcp-dados-br/actions/workflows/ci.yml/badge.svg)](https://github.com/lucianoon/mcp-dados-br/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mcp-dados-br?color=2e7d32&label=PyPI)](https://pypi.org/project/mcp-dados-br/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

*[Versão em português](README.md)*

An **MCP (Model Context Protocol)** server that exposes Brazilian public data as tools for AI assistants: [Claude Desktop](https://claude.ai/download), Claude Code, Cursor and any other MCP client.

## Installation

The simplest way, with nothing installed permanently:

```bash
uvx mcp-dados-br
```

Claude Desktop configuration:

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

Or in Claude Code:

```bash
claude mcp add dados-brasil -- uvx mcp-dados-br
```

### From source

```bash
git clone https://github.com/lucianoon/mcp-dados-br
cd mcp-dados-br
uv sync
```

## Available tools

| Source | Tools | Description |
|---|---|---|
| IBGE/SIDRA (statistics office) | `ibge_populacao`, `ibge_pib`, `ibge_municipios`, `ibge_sidra` | Population, GDP, municipality lookup and generic queries against any SIDRA aggregate |
| Banco Central (central bank) | `bcb_serie`, `bcb_cambio`, `bcb_moedas`, `bcb_focus` | SGS time series with named shortcuts (`selic`, `ipca`, `cdi`...), PTAX exchange rates, currency list and Focus survey market expectations |
| INMET (weather institute) | `inmet_estacoes`, `inmet_dados` | Weather station list and hourly observations (observational data requires a token) |
| Chamber of Deputies | `camara_deputados`, `camara_detalhes_deputado`, `camara_proposicoes`, `camara_votacoes_proposicao`, `camara_agenda`, `camara_tramitacao` | Deputies, bills, roll-call votes, agenda and legislative progress |
| Federal Senate | `senado_senadores`, `senado_materias`, `senado_votacoes` | Sitting senators, legislative matters and roll-call votes with tallies |

Every source is an official open API. No API key is required, except for INMET hourly
observations (see below).

## Configuration

### Claude Desktop / Cursor

Add this to the configuration file (`claude_desktop_config.json` or `mcp.json`):

```json
{
  "mcpServers": {
    "mcp-dados-br": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-dados-br", "mcp-dados-br"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add mcp-dados-br -- uv run --directory /path/to/mcp-dados-br mcp-dados-br
```

## Optional INMET token

Listing stations (`inmet_estacoes`) is open. **Hourly observations** (`inmet_dados`)
require a token issued by INMET. Request one at
[portal.inmet.gov.br](https://portal.inmet.gov.br) and set the environment variable in
your MCP client:

```json
{
  "mcpServers": {
    "mcp-dados-br": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-dados-br", "mcp-dados-br"],
      "env": { "INMET_TOKEN": "your-token" }
    }
  }
}
```

Without the token, the other 18 tools work normally.

## Streamable HTTP transport

Besides the default stdio transport, the server can run as a remote HTTP service:

```bash
MCP_TRANSPORTE=streamable-http MCP_PORTA=8000 mcp-dados-br
```

Point clients at `http://localhost:8000/mcp`. Handy for Docker or for sharing the server
on a local network. By default the server listens on `127.0.0.1` only; set
`MCP_HOST=0.0.0.0` to accept connections from other machines (the Docker image
already does).

| Variable | Default | Purpose |
|---|---|---|
| `MCP_TRANSPORTE` | `stdio` | `streamable-http` enables HTTP mode |
| `MCP_HOST` | `127.0.0.1` | Listen interface (`0.0.0.0` in the Docker image) |
| `MCP_PORTA` | `8000` | HTTP port |
| `MCP_AUTH_TOKEN` | empty | When set, every request must send `Authorization: Bearer <token>` |

### Authentication (optional bearer token)

> **Risk:** without `MCP_AUTH_TOKEN`, HTTP mode has no authentication. Listening
> on `0.0.0.0` (as the Docker image does), anyone who can reach the port can call
> all 19 tools, burn your quota on the public APIs and use your `INMET_TOKEN`.
> The server logs a warning when it starts like that. Do not expose the port to
> the internet without a token, and put a TLS reverse proxy in front of it: over
> plain HTTP the token travels in clear text.

Generate a long random token and hand it to the server:

```bash
export MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
MCP_TRANSPORTE=streamable-http mcp-dados-br
```

Requests without the header, with another scheme or with a different token get
`401` with `WWW-Authenticate: Bearer`. The comparison uses `secrets.compare_digest`
(constant time). On the client, send the header, for example in Claude Code:

```bash
claude mcp add --transport http dados-brasil http://localhost:8000/mcp \
  --header "Authorization: Bearer $MCP_AUTH_TOKEN"
```

The token does not apply to stdio: the process only talks to the client that started it.

### Docker

```bash
docker build -t mcp-dados-br .
docker run -p 8000:8000 \
  -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" \
  -e INMET_TOKEN=your-token \
  mcp-dados-br
```

For local-only use, publish the port on loopback only:
`docker run -p 127.0.0.1:8000:8000 mcp-dados-br`.

## Usage examples

Once configured, just ask your assistant (in Portuguese or English):

- "What was the IPCA inflation index over the last 6 months?"
- "What does the market expect for the Selic rate at the next meetings?" (Focus survey)
- "Who are the federal deputies from Minas Gerais in party X?"
- "What was the population of São Paulo in 2022? And its GDP?"
- "How has the PTAX dollar rate moved over the last few days?"
- "Find 2025 bills about mental health"
- "What is on the Chamber's agenda this week?"
- "How did the Senate vote on constitutional amendment X? What was the tally?"
- "Who are the senators from Minas Gerais?"
- "Which automatic INMET weather stations exist in Amazonas?"

## Development

```bash
uv sync --dev
uv run pytest                  # unit suite (mocked)
uv run pytest -m integration   # hits the real APIs
uv run ruff check .
uv run mypy src
```

Debug logs: set `MCP_LOG_LEVEL=DEBUG` in the MCP client.
To contribute, read [CONTRIBUTING.md](CONTRIBUTING.md).

### Architecture

```
src/mcp_dados_br/
├── server.py        # MCP server, tool registration and transport selection
├── auth.py          # ASGI bearer authentication middleware (HTTP mode)
├── validacao.py     # Tool argument validation (state codes, currency, dates, limits)
├── saida.py         # Tool result with text + structuredContent
├── http.py          # Shared HTTP client, retries and error handling
├── payload.py       # Defensive reading of API responses (source and field in the error)
├── cache.py         # In-memory TTL cache for API responses
└── tools/
    ├── ibge.py      # SIDRA v3 + localities v1
    ├── bcb.py       # SGS + Olinda (PTAX and Focus survey)
    ├── inmet.py     # Stations and observational data
    ├── camara.py    # Chamber of Deputies open data v2
    └── senado.py    # Federal Senate open data (LegisSaber)
```

- Two transports: stdio (the desktop client default) and streamable HTTP
  (Docker/network), the latter with optional bearer auth via `MCP_AUTH_TOKEN`
- Input validation before any URL is built: state codes among the 27 UFs, 3-letter
  ISO 4217 currency codes, ISO dates, numeric IBGE/SIDRA codes, positive IDs and
  bounds on `dias`/`ultimas`. Bounds are also published in each tool's
  `inputSchema`, and the MCP client gets an error message saying what was
  received and what is accepted
- 10-minute TTL cache per identical request, with an unambiguous key (sorted JSON
  of URL and parameters)
- Automatic retries on network failures and on `429`/`502`/`503`/`504`
- A format change in an upstream API (renamed field, different type) becomes a
  tool error (`isError: true`) naming the source and the field, e.g.
  `Resposta inesperada de BCB/PTAX: campo 'cotacaoCompra' ausente`
- Output formatted as model-readable text; `bcb_serie`, `bcb_cambio` and
  `camara_deputados` also return `structuredContent` with an `outputSchema`
  (ISO dates, numeric values), keeping the text as a fallback
- User-Agent carries the installed package version

## Roadmap

- [x] v0.2 — INMET (stations + observations with token) and Focus survey
- [x] v0.3 — Chamber agenda, streamable HTTP transport and scheduled integration tests in CI
- [x] v0.4 — Legislative progress, named SGS shortcuts, Docker image
- [x] v0.5 — Published on PyPI (`uvx mcp-dados-br`), MCP Registry and Smithery
- [x] v0.6 — Input validation, bearer auth for HTTP mode and structured output
- [ ] DOU: search the Federal Official Gazette (waiting for a stable public API)
- [ ] TSE: election results

## License

MIT
