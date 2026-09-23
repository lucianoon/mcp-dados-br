import asyncio
import json
import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_dados_br._versao import __version__
from mcp_dados_br.cache import TTLCache

logger = logging.getLogger(__name__)

_USER_AGENT = f"mcp-dados-br/{__version__} (+https://github.com/lucianoon/mcp-dados-br)"
_TIMEOUT = httpx.Timeout(30.0, connect=5.0)
_RETRYS_DELAY = [0.5, 1.5]
# Códigos em que vale repetir: limite de taxa e falhas transitórias do upstream
# (o 504 da Câmara derrubou a suíte de integração em 31/08/2026).
_STATUS_RETRY = {429, 502, 503, 504}

_cache = TTLCache(ttl_seconds=600.0)
_client: httpx.AsyncClient | None = None
_lock = asyncio.Lock()


class ApiError(ToolError):
    """Falha ao consultar uma API upstream.

    Herda de `ToolError` para que o SDK MCP entregue a mensagem (já sem o token
    do INMET) ao cliente, em vez do genérico "Error executing tool".
    """


async def get_client() -> httpx.AsyncClient:
    global _client
    async with _lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                timeout=_TIMEOUT,
                follow_redirects=True,
            )
        return _client


def reset_cache() -> None:
    _cache.clear()


def cache_key(url: str, params: dict[str, Any] | None) -> str:
    """Chave inequívoca para a requisição.

    Serializa URL e parâmetros como JSON ordenado: um valor contendo `&` ou `=`
    não consegue se passar por outro parâmetro. Os valores viram `str` porque é
    assim que vão para a query string (`1` e `"1"` geram a mesma requisição).
    """
    itens = sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)
    return json.dumps([url, itens], ensure_ascii=False, separators=(",", ":"))


def _query_string(params: dict[str, Any]) -> str:
    return "&".join(
        f"{k}={quote(str(v), safe='')}"
        for k, v in sorted(params.items())
        if v is not None
    )


def _redigir(url: str) -> str:
    token_inmet = os.environ.get("INMET_TOKEN")
    if token_inmet:
        url = url.replace(token_inmet, "***")
    return url


async def get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    key = cache_key(url, params)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    request_url = f"{url}?{_query_string(params)}" if params else url
    logger.debug("GET %s", _redigir(request_url))
    client = await get_client()
    last_error: Exception | None = None
    for attempt in range(len(_RETRYS_DELAY) + 1):
        try:
            response = await client.get(request_url)
            if response.status_code in _STATUS_RETRY and attempt < len(_RETRYS_DELAY):
                logger.warning(
                    "Tentativa %d falhou para %s: HTTP %d",
                    attempt + 1,
                    _redigir(url),
                    response.status_code,
                )
                await asyncio.sleep(_RETRYS_DELAY[attempt])
                continue
            if response.status_code >= 400:
                corpo = response.text[:200]
                raise ApiError(
                    f"HTTP {response.status_code} ao consultar {_redigir(url)}: {corpo}"
                )
            try:
                data: Any = response.json()
            except ValueError as exc:
                raise ApiError(f"Resposta não-JSON de {_redigir(url)}: {exc}") from exc
            _cache.set(key, data)
            return data
        except httpx.TransportError as exc:
            last_error = exc
            logger.warning("Tentativa %d falhou para %s: %r", attempt + 1, _redigir(url), exc)
            if attempt < len(_RETRYS_DELAY):
                await asyncio.sleep(_RETRYS_DELAY[attempt])
    raise ApiError(f"Falha ao consultar {_redigir(url)}: {last_error}") from last_error


async def aclose() -> None:
    global _client
    async with _lock:
        if _client is not None and not _client.is_closed:
            await _client.aclose()
        _client = None
