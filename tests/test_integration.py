"""Testes de integração que consultam as APIs reais.

Rodar explicitamente: uv run pytest -m integration
A suíte padrão os ignora via addopts.
"""

import pytest

from mcp_dados_br.http import aclose
from mcp_dados_br.saida import texto_de
from mcp_dados_br.tools import bcb, camara, ibge, inmet

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _cliente_http_por_teste():
    await aclose()
    yield
    await aclose()


async def test_ibge_populacao_sp_online() -> None:
    saida = await ibge.ibge_populacao("SP")
    assert "São Paulo" in saida


async def test_ibge_municipios_online() -> None:
    saida = await ibge.ibge_municipios("campinas", "SP")
    assert "Campinas" in saida


async def test_bcb_serie_ipca_online() -> None:
    saida = texto_de(await bcb.bcb_serie(indicador="ipca"))
    assert "Série 433" in saida


async def test_bcb_focus_selic_online() -> None:
    saida = await bcb.bcb_focus("selic")
    assert "SELIC" in saida


async def test_bcb_cambio_usd_online() -> None:
    saida = texto_de(await bcb.bcb_cambio("USD", dias=5))
    assert "PTAX USD" in saida


async def test_camara_deputados_sp_online() -> None:
    saida = texto_de(await camara.camara_deputados(uf="SP"))
    assert "/SP)" in saida


async def test_inmet_estacoes_df_online() -> None:
    saida = await inmet.inmet_estacoes("T", uf="DF")
    assert "A001" in saida or "Nenhuma estação" in saida
