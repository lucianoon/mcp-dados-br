
from datetime import date

import httpx
import pytest
import respx

from mcp_dados_br.saida import texto_de
from mcp_dados_br.tools import bcb

PTAX_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)

RESPOSTA_PTAX = {
    "value": [
        {
            "cotacaoCompra": 5.0,
            "cotacaoVenda": 5.1,
            "dataHoraCotacao": "2026-08-18 10:00:00.000",
            "tipoBoletim": "Abertura",
        },
        {
            "cotacaoCompra": 5.2,
            "cotacaoVenda": 5.3,
            "dataHoraCotacao": "2026-08-19 13:00:00.000",
            "tipoBoletim": "Fechamento",
        },
        {
            "cotacaoCompra": 5.4,
            "cotacaoVenda": 5.5,
            "dataHoraCotacao": "2026-08-20 13:00:00.000",
            "tipoBoletim": "Fechamento",
        },
    ]
}


def test_conversao_datas() -> None:
    assert bcb._data_sgs("2026-08-24") == "24/08/2026"
    assert bcb._data_ptax("2026-08-24") == "08-24-2026"


@respx.mock
async def test_bcb_serie_formata_registros() -> None:
    respx.get(
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"data": "01/06/2026", "valor": "0.24"},
                {"data": "01/07/2026", "valor": "0.17"},
            ],
        )
    )
    saida = texto_de(
        await bcb.bcb_serie(codigo=433, data_inicial="2026-06-01", data_final="2026-07-31")
    )
    assert "Série 433:" in saida
    assert "01/06/2026: 0.24" in saida
    assert "01/07/2026: 0.17" in saida


async def test_bcb_serie_periodo_invalido() -> None:
    with pytest.raises(ValueError, match="anterior"):
        await bcb.bcb_serie(codigo=433, data_inicial="2026-07-01", data_final="2026-06-01")


async def test_bcb_serie_sem_indicador_nem_codigo() -> None:
    with pytest.raises(ValueError, match="atalhos"):
        await bcb.bcb_serie()


async def test_bcb_serie_indicador_desconhecido() -> None:
    with pytest.raises(ValueError, match="Indicador desconhecido"):
        await bcb.bcb_serie(indicador="dolar_futuro")


@respx.mock
async def test_bcb_serie_atalho_ipca_resolve_codigo_433() -> None:
    route = respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados").mock(
        return_value=httpx.Response(200, json=[{"data": "01/07/2026", "valor": "0.17"}])
    )
    saida = texto_de(await bcb.bcb_serie(indicador="IPCA", data_inicial="2026-07-01"))
    assert "/bcdata.sgs.433/" in str(route.calls.last.request.url)
    assert "01/07/2026: 0.17" in saida


@respx.mock
async def test_bcb_cambio_resume_apenas_fechamento() -> None:
    route = respx.get(PTAX_URL).mock(
        return_value=httpx.Response(200, json=RESPOSTA_PTAX)
    )
    saida = texto_de(await bcb.bcb_cambio("USD", dias=2))
    requisicao = route.calls.last.request.url.params
    assert requisicao["@moeda"] == "'USD'"
    assert requisicao["@dataInicial"].startswith("'")
    assert requisicao["$format"] == "json"
    assert "compra mín. R$ 5.2" in saida
    assert "média R$ 5.3000" in saida
    assert "Abertura" not in saida


@respx.mock
async def test_bcb_cambio_moeda_inexistente() -> None:
    respx.get(PTAX_URL).mock(return_value=httpx.Response(200, json={"value": []}))
    saida = texto_de(await bcb.bcb_cambio("XXX"))
    assert "Nenhuma cotação encontrada" in saida


@respx.mock
async def test_bcb_moedas_lista_simbolos() -> None:
    respx.get(
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"value": [{"simbolo": "EUR", "nomeFormatado": "Euro"}]},
        )
    )
    saida = await bcb.bcb_moedas()
    assert "EUR — Euro" in saida


@respx.mock
async def test_bcb_cambio_top_cobre_todos_os_boletins_da_janela() -> None:
    # Com $top = dias * 2 o OData cortava os dias mais recentes: são até 5
    # boletins PTAX por dia útil. Em 22/09/2026, dias=7 devolvia a cotação de 15/09.
    route = respx.get(PTAX_URL).mock(return_value=httpx.Response(200, json={"value": []}))
    await bcb.bcb_cambio("USD", dias=7)
    params = route.calls.last.request.url.params
    inicio = params["@dataInicial"].strip("'")
    fim = params["@dataFinalCotacao"].strip("'")
    dias_corridos = (
        date(int(fim[6:]), int(fim[:2]), int(fim[3:5]))
        - date(int(inicio[6:]), int(inicio[:2]), int(inicio[3:5]))
    ).days
    assert int(params["$top"]) >= dias_corridos * 5
