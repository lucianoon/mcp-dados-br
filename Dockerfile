FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

# Processo sem root: o servidor só lê o próprio código e fala com APIs públicas.
RUN useradd --system --uid 1000 --no-create-home mcp && chown -R mcp:mcp /app
USER mcp

# Escuta em todas as interfaces do container. Defina MCP_AUTH_TOKEN no
# `docker run -e` para exigir Authorization: Bearer; sem ele o HTTP fica aberto.
ENV MCP_TRANSPORTE=streamable-http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORTA=8000
EXPOSE 8000

# Entrypoint direto do venv: `uv run` tentaria criar cache em $HOME, que o
# usuário sem privilégios não tem.
CMD ["/app/.venv/bin/mcp-dados-br"]
