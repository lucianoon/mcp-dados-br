"""Entradas inválidas são recusadas antes de qualquer requisição HTTP.

Os testes sem `respx.mock` provam isso de graça: se a tool chegasse a montar a
URL, o httpx tentaria a rede e o erro seria outro.
"""

from typing import Any

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

from mcp_dados_br.http import ApiError
from mcp_dados_br.server import create_server
from mcp_dados_br.tools import bcb, camara, ibge, inmet, senado
from mcp_dados_br.validacao import (
    EntradaInvalida,
    validar_data,
    validar_inteiro,
    validar_moeda,
    validar_uf,
)


@pytest.mark.parametrize("uf", ["sp", " SP ", "df"])
def test_validar_uf_normaliza(uf: str) -> None:
    assert validar_uf(uf) == uf.strip().upper()


@pytest.mark.parametrize("uf", ["XX", "BR", "S", "SP/../x", ""])
def test_validar_uf_recusa(uf: str) -> None:
    with pytest.raises(EntradaInvalida, match="UF desconhecida"):
        validar_uf(uf)


def test_validar_uf_aceita_br_quando_permitido() -> None:
    assert validar_uf("br", permitir_br=True) == "BR"


@pytest.mark.parametrize("moeda", ["US", "USDX", "U$D", "USD'", "' or 1 eq 1 or '", "12A"])
def test_validar_moeda_recusa(moeda: str) -> None:
    with pytest.raises(EntradaInvalida, match="ISO 4217"):
        validar_moeda(moeda)


def test_validar_moeda_normaliza() -> None:
    assert validar_moeda(" eur ") == "EUR"


@pytest.mark.parametrize("valor", ["2026-13-01", "2026-02-30"])
def test_validar_data_recusa_data_impossivel(valor: str) -> None:
    with pytest.raises(EntradaInvalida, match="não é uma data válida"):
        validar_data("data_inicial", valor)


@pytest.mark.parametrize("valor", ["01/02/2026", "2026-1-5", "ontem", "2026-01-01T00:00"])
def test_validar_data_recusa_formato(valor: str) -> None:
    with pytest.raises(EntradaInvalida, match="AAAA-MM-DD"):
        validar_data("data_inicial", valor)


@pytest.mark.parametrize("valor", [0, -1, 15, True])
def test_validar_inteiro_fora_da_faixa(valor: Any) -> None:
    with pytest.raises(EntradaInvalida, match="dias"):
        validar_inteiro("dias", valor, 1, 14)


def test_entrada_invalida_chega_ao_cliente_mcp() -> None:
    # ToolError: o SDK repassa a mensagem ao modelo em vez de "Error executing tool".
    assert issubclass(EntradaInvalida, ToolError)
    assert not issubclass(EntradaInvalida, UnexpectedToolError)
    assert issubclass(EntradaInvalida, ValueError)
    assert issubclass(ApiError, ToolError)


CASOS_INVALIDOS = [
    (bcb.bcb_cambio, {"moeda": "USD' or '1"}, "Moeda inválida"),
    (bcb.bcb_cambio, {"moeda": "USD", "dias": 0}, "dias"),
    (bcb.bcb_cambio, {"moeda": "USD", "dias": 31}, "dias"),
    (bcb.bcb_serie, {"codigo": 0}, "codigo"),
    (bcb.bcb_serie, {"codigo": 433, "data_inicial": "01/06/2026"}, "AAAA-MM-DD"),
    (bcb.bcb_serie, {"codigo": 433, "data_final": "2026-02-31"}, "data válida"),
    (ibge.ibge_populacao, {"uf": "ZZ"}, "UF desconhecida"),
    (ibge.ibge_pib, {"uf": "SP", "ano": 1500}, "ano"),
    (ibge.ibge_municipios, {"nome": "campinas", "uf": "SP/../municipios"}, "UF desconhecida"),
    (ibge.ibge_municipios, {"nome": " "}, "nome"),
    (ibge.ibge_sidra, {"agregado": "4709/../1", "variavel": "93"}, "agregado"),
    (ibge.ibge_sidra, {"agregado": "4709", "variavel": "93?x=1"}, "variavel"),
    (ibge.ibge_sidra, {"agregado": "4709", "variavel": "93", "periodos": "2020/2024"}, "periodos"),
    (ibge.ibge_sidra, {"agregado": "4709", "variavel": "93", "localidades": "SP"}, "localidades"),
    (inmet.inmet_estacoes, {"uf": "XX"}, "UF desconhecida"),
    (inmet.inmet_dados, {"estacao": "A001/../x"}, "estacao"),
    (inmet.inmet_dados, {"estacao": "A001", "dias": 8}, "dias"),
    (camara.camara_deputados, {"uf": "XX"}, "UF desconhecida"),
    (camara.camara_deputados, {"partido": "PT&x=1"}, "partido"),
    (camara.camara_deputados, {"legislatura": 0}, "legislatura"),
    (camara.camara_deputados, {"nome": "ab"}, "nome"),
    (camara.camara_detalhes_deputado, {"id_deputado": -5}, "id_deputado"),
    (camara.camara_proposicoes, {"sigla_tipo": "PL 1"}, "sigla_tipo"),
    (camara.camara_proposicoes, {"ano": 3000}, "ano"),
    (camara.camara_proposicoes, {"palavras_chave": "x" * 201}, "palavras_chave"),
    (camara.camara_votacoes_proposicao, {"id_proposicao": 0}, "id_proposicao"),
    (camara.camara_agenda, {"dias": 0}, "dias"),
    (camara.camara_agenda, {"dias": 15}, "dias"),
    (camara.camara_tramitacao, {"id_proposicao": 1, "ultimas": 101}, "ultimas"),
    (senado.senado_senadores, {"uf": "XX"}, "UF desconhecida"),
    (senado.senado_materias, {"sigla": "P/L"}, "sigla"),
    (senado.senado_materias, {"ano": 1800}, "ano"),
    (senado.senado_votacoes, {"codigo_materia": 0}, "codigo_materia"),
]


@pytest.mark.parametrize(
    ("tool", "argumentos", "mensagem"),
    CASOS_INVALIDOS,
    ids=[f"{t.__name__}-{i}" for i, (t, _, _) in enumerate(CASOS_INVALIDOS)],
)
async def test_tool_recusa_entrada_invalida(
    tool: Any, argumentos: dict[str, Any], mensagem: str
) -> None:
    with pytest.raises(EntradaInvalida, match=mensagem):
        await tool(**argumentos)


async def test_inmet_dados_valida_mesmo_com_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INMET_TOKEN", "segredo")
    with pytest.raises(EntradaInvalida, match="estacao"):
        await inmet.inmet_dados("../../x")


@respx.mock
async def test_bcb_cambio_normaliza_moeda_minuscula() -> None:
    route = respx.get(url__startswith="https://olinda.bcb.gov.br/").mock(
        return_value=httpx.Response(200, json={"value": []})
    )
    await bcb.bcb_cambio(" eur ", dias=3)
    assert route.calls.last.request.url.params["@moeda"] == "'EUR'"


@respx.mock
async def test_ibge_sidra_aceita_sintaxes_validas() -> None:
    route = respx.get(url__startswith="https://servicodados.ibge.gov.br/").mock(
        return_value=httpx.Response(200, json=[])
    )
    await ibge.ibge_sidra("1737", "63|2266", "N6[N3[35]]|N1[all]", "202401-202406")
    requisicao = route.calls.last.request.url
    assert requisicao.path.endswith("/1737/periodos/202401-202406/variaveis/63|2266")
    assert requisicao.params["localidades"] == "N6[N3[35]]|N1[all]"


# Pela via do servidor MCP: a mensagem precisa chegar ao cliente, não o genérico.


async def test_call_tool_devolve_mensagem_de_validacao() -> None:
    servidor = create_server()
    with pytest.raises(ToolError, match="Moeda inválida") as excinfo:
        await servidor.call_tool("bcb_cambio", {"moeda": "DOLAR"})
    assert not isinstance(excinfo.value, UnexpectedToolError)


async def test_call_tool_recusa_limite_pelo_schema() -> None:
    servidor = create_server()
    with pytest.raises(ToolError, match="less than or equal to 14") as excinfo:
        await servidor.call_tool("camara_agenda", {"dias": 60})
    assert not isinstance(excinfo.value, UnexpectedToolError)


async def test_schema_das_tools_publica_limites() -> None:
    servidor = create_server()
    schemas = {t.name: t.input_schema for t in await servidor.list_tools()}
    dias_agenda = schemas["camara_agenda"]["properties"]["dias"]
    assert (dias_agenda["minimum"], dias_agenda["maximum"]) == (1, 14)
    dias_cambio = schemas["bcb_cambio"]["properties"]["dias"]
    assert (dias_cambio["minimum"], dias_cambio["maximum"]) == (1, 30)
    assert schemas["senado_votacoes"]["properties"]["codigo_materia"]["minimum"] == 1
