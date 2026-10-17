from datetime import date, timedelta

import httpx
import pytest
import respx

from mcp_dados_br.tools import bcb

FOCUS_URL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata"

HOJE = date.today()
INICIO = (HOJE - timedelta(days=bcb._FOCUS_JANELA_DIAS)).isoformat()

RESPOSTA_SELIC = {
    "value": [
        {
            "Indicador": "Selic",
            "Data": f"{HOJE}",
            "Reuniao": "R5/2028",
            "Media": 11.13,
            "Mediana": 11.25,
            "Minimo": 8.75,
            "Maximo": 13.75,
            "numeroRespondentes": 70,
            "baseCalculo": 0,
        },
        {
            "Indicador": "Selic",
            "Data": f"{HOJE}",
            "Reuniao": "R5/2028",
            "Media": 11.29,
            "Mediana": 11.5,
            "Minimo": 9.75,
            "Maximo": 13.75,
            "numeroRespondentes": 47,
            "baseCalculo": 1,
        },
    ]
}


async def test_focus_indicador_invalido() -> None:
    with pytest.raises(ValueError, match="Indicador desconhecido"):
        await bcb.bcb_focus("bitcoin")


@respx.mock
async def test_bcb_focus_selic_saida() -> None:
    route = respx.get(f"{FOCUS_URL}/ExpectativasMercadoSelic").mock(
        return_value=httpx.Response(200, json=RESPOSTA_SELIC)
    )
    saida = await bcb.bcb_focus("Selic")
    requisicao = route.calls.last.request.url.params
    assert requisicao["$filter"] == f"Data ge '{INICIO}' and baseCalculo eq 0"
    assert requisicao["$orderby"] == "Data desc"
    assert "expectativas para SELIC:" in saida
    assert "mediana 11.25" in saida
    assert "baseCalculo 1" not in saida and "11.5" not in saida
    assert "70 analistas" in saida


@respx.mock
async def test_bcb_focus_ipca_com_filtro_indicador() -> None:
    route = respx.get(f"{FOCUS_URL}/ExpectativasMercadoTop5Inflacao12Meses").mock(
        return_value=httpx.Response(
            200,
            json={
                "value": [
                    {
                        "Indicador": "IPCA",
                        "Data": f"{HOJE}",
                        "Media": 4.35,
                        "Mediana": 4.56,
                        "Minimo": 3.38,
                        "Maximo": 4.92,
                        "numeroRespondentes": 4,
                    }
                ]
            },
        )
    )
    saida = await bcb.bcb_focus("ipca")
    requisicao = route.calls.last.request.url.params
    assert "Indicador eq 'IPCA'" in requisicao["$filter"]
    assert "próximos 12 meses | mediana 4.56" in saida


@respx.mock
async def test_bcb_focus_sem_dados_recentes() -> None:
    respx.get(f"{FOCUS_URL}/ExpectativasMercadoTop5Anuais").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    saida = await bcb.bcb_focus("pib")
    assert "Nenhuma expectativa recente" in saida
    assert f"últimos {bcb._FOCUS_JANELA_DIAS} dias" in saida


@respx.mock
async def test_bcb_focus_selic_descarta_so_base_calculo_1() -> None:
    respx.get(f"{FOCUS_URL}/ExpectativasMercadoSelic").mock(
        return_value=httpx.Response(200, json={"value": [RESPOSTA_SELIC["value"][1]]})
    )
    saida = await bcb.bcb_focus("selic")
    assert "Nenhuma expectativa recente" in saida
