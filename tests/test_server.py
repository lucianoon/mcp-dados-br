import asyncio

import pytest

from mcp_dados_br import server as modulo_server
from mcp_dados_br.server import create_server

NOMES_ESPERADOS = {
    "ibge_populacao",
    "ibge_pib",
    "ibge_municipios",
    "ibge_sidra",
    "bcb_serie",
    "bcb_cambio",
    "bcb_moedas",
    "bcb_focus",
    "inmet_estacoes",
    "inmet_dados",
    "camara_deputados",
    "camara_detalhes_deputado",
    "camara_proposicoes",
    "camara_votacoes_proposicao",
    "camara_agenda",
    "camara_tramitacao",
    "senado_senadores",
    "senado_materias",
    "senado_votacoes",
}


def test_servidor_registra_todas_as_tools() -> None:
    async def coletar() -> list[str]:
        servidor = create_server()
        tools = await servidor.list_tools()
        return [t.name for t in tools]

    nomes = set(asyncio.run(coletar()))
    assert nomes == NOMES_ESPERADOS


class _ServidorFalso:
    def __init__(self) -> None:
        self.chamadas: list[dict[str, object]] = []

    def run(self, transport: str = "stdio", **kwargs: object) -> None:
        self.chamadas.append({"transport": transport, **kwargs})


def test_main_streamable_http_respeita_host_e_porta(monkeypatch: pytest.MonkeyPatch) -> None:
    falso = _ServidorFalso()
    monkeypatch.setattr(modulo_server, "create_server", lambda: falso)
    monkeypatch.setenv("MCP_TRANSPORTE", "streamable-http")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORTA", "9000")

    modulo_server.main()

    assert falso.chamadas == [{"transport": "streamable-http", "host": "0.0.0.0", "port": 9000}]


def test_main_streamable_http_escuta_apenas_local_por_padrao(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    falso = _ServidorFalso()
    monkeypatch.setattr(modulo_server, "create_server", lambda: falso)
    monkeypatch.setenv("MCP_TRANSPORTE", "streamable-http")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_HOST", raising=False)
    monkeypatch.delenv("MCP_PORTA", raising=False)

    modulo_server.main()

    assert falso.chamadas[0]["host"] == "127.0.0.1"
    assert falso.chamadas[0]["port"] == 8000
