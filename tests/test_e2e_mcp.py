"""Ponta a ponta no protocolo MCP, em processo e sem rede.

O cliente do SDK conversa com o servidor real (`create_server`). No modo
"legacy" a sessão passa pelo handshake `initialize` e por mensagens JSON-RPC
em streams de memória; no modo "auto" usa o despacho direto do SDK. As APIs
upstream são simuladas com respx.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
import respx
from mcp.client import Client
from mcp.types import TextContent

from mcp_dados_br.server import create_server
from test_server import NOMES_ESPERADOS

SGS_433 = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
DEPUTADOS = "https://dadosabertos.camara.leg.br/api/v2/deputados"
PTAX = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo"

ESTRUTURADAS = {"bcb_serie", "bcb_cambio", "camara_deputados"}


@pytest.fixture(params=["legacy", "auto"])
def modo(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@asynccontextmanager
async def _conectar(modo: str) -> AsyncIterator[Client]:
    # Aberto dentro do próprio teste: o Client usa task group do anyio, que
    # precisa entrar e sair na mesma task (fixture assíncrona roda em outra).
    async with Client(create_server(), mode=modo) as cliente:
        yield cliente


def _texto(resultado: object) -> str:
    conteudo = resultado.content  # type: ignore[attr-defined]
    assert conteudo, "resultado sem content"
    bloco = conteudo[0]
    assert isinstance(bloco, TextContent)
    return bloco.text


async def test_lista_as_19_tools_com_output_schema_nas_estruturadas(modo: str) -> None:
    async with _conectar(modo) as cliente:
        tools = (await cliente.list_tools()).tools
        nomes = {t.name for t in tools}
        assert len(tools) == 19
        assert nomes == NOMES_ESPERADOS
        for tool in tools:
            assert tool.description, f"{tool.name} sem descrição"
            assert tool.input_schema["type"] == "object"
            if tool.name in ESTRUTURADAS:
                assert tool.output_schema is not None, f"{tool.name} sem outputSchema"
                assert tool.output_schema["type"] == "object"
        esquema_serie = next(t for t in tools if t.name == "bcb_serie").output_schema
        assert esquema_serie is not None
        assert {"codigo", "registros", "total_registros"} <= set(esquema_serie["properties"])


@respx.mock
async def test_bcb_serie_devolve_content_e_structured_content(modo: str) -> None:
    async with _conectar(modo) as cliente:
        respx.get(SGS_433).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"data": "01/06/2026", "valor": "0.24"},
                    {"data": "01/07/2026", "valor": "0.17"},
                ],
            )
        )
        resultado = await cliente.call_tool(
            "bcb_serie",
            {"indicador": "ipca", "data_inicial": "2026-06-01", "data_final": "2026-07-31"},
        )
        assert not resultado.is_error
        texto = _texto(resultado)
        assert "Série 433:" in texto
        assert "01/07/2026: 0.17" in texto
        assert resultado.structured_content == {
            "codigo": 433,
            "data_inicial": "2026-06-01",
            "data_final": "2026-07-31",
            "total_registros": 2,
            "registros": [
                {"data": "2026-06-01", "valor": 0.24},
                {"data": "2026-07-01", "valor": 0.17},
            ],
        }


@respx.mock
async def test_camara_deputados_devolve_content_e_structured_content(modo: str) -> None:
    async with _conectar(modo) as cliente:
        rota = respx.get(DEPUTADOS).mock(
            return_value=httpx.Response(
                200,
                json={
                    "dados": [
                        {
                            "id": 204554,
                            "nome": "Fulana de Tal",
                            "siglaPartido": "PT",
                            "siglaUf": "SP",
                            "urlFoto": "https://www.camara.leg.br/foto.jpg",
                        }
                    ]
                },
            )
        )
        resultado = await cliente.call_tool("camara_deputados", {"uf": "sp"})
        assert not resultado.is_error
        assert rota.calls.last.request.url.params["siglaUf"] == "SP"
        assert _texto(resultado) == "204554 — Fulana de Tal (PT/SP)"
        assert resultado.structured_content == {
            "deputados": [
                {
                    "id": 204554,
                    "nome": "Fulana de Tal",
                    "partido": "PT",
                    "uf": "SP",
                    "url_foto": "https://www.camara.leg.br/foto.jpg",
                }
            ]
        }


@respx.mock
async def test_tool_de_texto_devolve_so_content(modo: str) -> None:
    async with _conectar(modo) as cliente:
        respx.get(
            "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas"
        ).mock(
            return_value=httpx.Response(
                200, json={"value": [{"simbolo": "EUR", "nomeFormatado": "Euro"}]}
            )
        )
        resultado = await cliente.call_tool("bcb_moedas", {})
        assert not resultado.is_error
        assert _texto(resultado) == "EUR — Euro"


@respx.mock
@pytest.mark.parametrize(
    ("tool", "argumentos", "trecho"),
    [
        ("camara_deputados", {"uf": "XX"}, "UF"),
        ("bcb_serie", {"indicador": "dolar_futuro"}, "Indicador desconhecido"),
        ("bcb_cambio", {"moeda": "US$"}, "moeda"),
    ],
)
async def test_entrada_invalida_vira_is_error_sem_chamar_a_api(
    modo: str, tool: str, argumentos: dict[str, object], trecho: str
) -> None:
    async with _conectar(modo) as cliente:
        rota = respx.route().mock(return_value=httpx.Response(500))
        resultado = await cliente.call_tool(tool, argumentos)
        assert resultado.is_error
        assert trecho in _texto(resultado)
        assert not rota.called


async def test_argumento_fora_do_input_schema_vira_is_error(modo: str) -> None:
    async with _conectar(modo) as cliente:
        resultado = await cliente.call_tool("bcb_cambio", {"moeda": "USD", "dias": 999})
        assert resultado.is_error
        assert "dias" in _texto(resultado)


@respx.mock
async def test_payload_inesperado_chega_ao_cliente_como_is_error(modo: str) -> None:
    async with _conectar(modo) as cliente:
        respx.get(url__startswith=PTAX).mock(
            return_value=httpx.Response(
                200,
                json={"value": [
                    {"cotacaoVenda": 5.3, "dataHoraCotacao": "2026-08-19 13:00:00.000"}
                ]},
            )
        )
        resultado = await cliente.call_tool("bcb_cambio", {"moeda": "USD"})
        assert resultado.is_error
        texto = _texto(resultado)
        assert "Resposta inesperada de BCB/PTAX" in texto
        assert "'cotacaoCompra'" in texto
