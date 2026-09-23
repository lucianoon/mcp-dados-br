"""Saída estruturada (structuredContent + outputSchema) nas tools principais."""

import httpx
import respx

from mcp_dados_br.server import create_server
from mcp_dados_br.tools import bcb

SGS_433 = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)


async def test_output_schema_publicado_nas_tools_estruturadas() -> None:
    tools = {t.name: t for t in await create_server().list_tools()}
    serie = tools["bcb_serie"].output_schema
    assert serie is not None
    assert {"codigo", "registros", "total_registros"} <= set(serie["properties"])
    cambio = tools["bcb_cambio"].output_schema
    assert cambio is not None
    assert {"moeda", "cotacoes", "ultima"} <= set(cambio["properties"])
    deputados = tools["camara_deputados"].output_schema
    assert deputados is not None
    assert "deputados" in deputados["properties"]


@respx.mock
async def test_bcb_serie_via_servidor_traz_texto_e_dados() -> None:
    respx.get(SGS_433).mock(
        return_value=httpx.Response(
            200,
            json=[{"data": "01/06/2026", "valor": "0.24"}, {"data": "01/07/2026", "valor": ""}],
        )
    )
    resultado = await create_server().call_tool(
        "bcb_serie", {"indicador": "ipca", "data_inicial": "2026-06-01", "data_final": "2026-07-31"}
    )
    assert not resultado.is_error
    # O texto de sempre continua no content, como fallback para clientes sem suporte.
    assert "01/06/2026: 0.24" in resultado.content[0].text
    assert resultado.structured_content == {
        "codigo": 433,
        "data_inicial": "2026-06-01",
        "data_final": "2026-07-31",
        "total_registros": 2,
        "registros": [
            {"data": "2026-06-01", "valor": 0.24},
            {"data": "2026-07-01", "valor": None},
        ],
    }


@respx.mock
async def test_bcb_cambio_estruturado_so_com_fechamento() -> None:
    respx.get(PTAX_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "cotacaoCompra": 5.0,
                        "cotacaoVenda": 5.1,
                        "dataHoraCotacao": "2026-08-19 10:00:00.000",
                        "tipoBoletim": "Abertura",
                    },
                    {
                        "cotacaoCompra": 5.2,
                        "cotacaoVenda": 5.3,
                        "dataHoraCotacao": "2026-08-19 13:00:00.000",
                        "tipoBoletim": "Fechamento",
                    },
                ]
            },
        )
    )
    resultado = await bcb.bcb_cambio("usd", dias=3)
    dados = resultado.structured_content
    assert dados is not None
    assert dados["moeda"] == "USD"
    assert dados["cotacoes"] == [{"data": "2026-08-19", "compra": 5.2, "venda": 5.3}]
    assert dados["ultima"] == dados["cotacoes"][0]
    assert dados["compra_media"] == 5.2


@respx.mock
async def test_camara_deputados_vazio_estruturado() -> None:
    respx.get("https://dadosabertos.camara.leg.br/api/v2/deputados").mock(
        return_value=httpx.Response(200, json={"dados": []})
    )
    resultado = await create_server().call_tool("camara_deputados", {"uf": "AC"})
    assert resultado.structured_content == {"deputados": []}
    assert "Nenhum deputado" in resultado.content[0].text
