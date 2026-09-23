"""Payload inesperado das APIs upstream vira ApiError com fonte e campo.

Cada caso simula uma mudança de formato (campo renomeado, tipo trocado,
resposta truncada) e confere que a tool levanta `PayloadInesperado`, subclasse
de `ApiError` e portanto de `ToolError`, em vez de KeyError/TypeError genérico.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_dados_br.http import ApiError
from mcp_dados_br.payload import (
    PayloadInesperado,
    aninhado,
    campo,
    lendo,
    lista,
    numero,
    objeto,
)
from mcp_dados_br.saida import texto_de
from mcp_dados_br.tools import bcb, camara, ibge, inmet, senado
from mcp_dados_br.validacao import EntradaInvalida

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados"
PTAX = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo"
MOEDAS = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/Moedas"
FOCUS = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
SIDRA = "https://servicodados.ibge.gov.br/api/v3/agregados/"
MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/"
INMET_ESTACOES = "https://apitempo.inmet.gov.br/estacoes/"
INMET_DADOS = "https://apitempo.inmet.gov.br/token/estacao/"
CAMARA = "https://dadosabertos.camara.leg.br/api/v2/"
SENADO = "https://legis.senado.leg.br/dadosabertos/"

_Chamada = Callable[[], Awaitable[Any]]


def _cotacao(**sobrescrever: Any) -> dict[str, Any]:
    base = {
        "cotacaoCompra": 5.2,
        "cotacaoVenda": 5.3,
        "dataHoraCotacao": "2026-08-19 13:00:00.000",
        "tipoBoletim": "Fechamento",
    }
    base.update(sobrescrever)
    return {k: v for k, v in base.items() if v is not None}


CASOS: list[tuple[str, str, Any, _Chamada, list[str]]] = [
    # (id, prefixo da URL, payload, chamada, trechos esperados na mensagem)
    ("sgs-sem-data", SGS, [{"valor": "0.24"}],
     lambda: bcb.bcb_serie(indicador="ipca"), ["BCB/SGS", "'data'"]),
    ("sgs-objeto-no-lugar-da-lista", SGS, {"erro": "série inexistente"},
     lambda: bcb.bcb_serie(indicador="ipca"), ["BCB/SGS", "lista", "dict"]),
    ("sgs-data-em-outro-formato", SGS, [{"data": "2026-06-01", "valor": "0.24"}],
     lambda: bcb.bcb_serie(indicador="ipca"), ["BCB/SGS", "ValueError"]),
    ("ptax-sem-cotacaoCompra", PTAX, {"value": [_cotacao(cotacaoCompra=None)]},
     lambda: bcb.bcb_cambio("USD"), ["BCB/PTAX", "'cotacaoCompra'"]),
    ("ptax-venda-nao-numerica", PTAX, {"value": [_cotacao(cotacaoVenda="n/d")]},
     lambda: bcb.bcb_cambio("USD"), ["BCB/PTAX", "'cotacaoVenda'", "numérico"]),
    ("ptax-sem-dataHoraCotacao", PTAX, {"value": [_cotacao(dataHoraCotacao=None)]},
     lambda: bcb.bcb_cambio("USD"), ["BCB/PTAX", "'dataHoraCotacao'"]),
    ("ptax-value-objeto", PTAX, {"value": {"cotacaoCompra": 5}},
     lambda: bcb.bcb_cambio("USD"), ["BCB/PTAX", "value", "lista"]),
    ("ptax-resposta-lista", PTAX, [_cotacao()],
     lambda: bcb.bcb_cambio("USD"), ["BCB/PTAX", "objeto", "list"]),
    ("moedas-sem-simbolo", MOEDAS, {"value": [{"nomeFormatado": "Euro"}]},
     bcb.bcb_moedas, ["BCB/PTAX", "'simbolo'"]),
    ("focus-sem-Data", FOCUS, {"value": [{"Mediana": 4.5}]},
     lambda: bcb.bcb_focus("ipca"), ["BCB/Focus", "'Data'"]),
    ("focus-registro-texto", FOCUS, {"value": ["4,5"]},
     lambda: bcb.bcb_focus("ipca"), ["BCB/Focus", "expectativa", "objeto"]),
    ("sidra-localidade-texto", SIDRA,
     [{"variavel": "População", "resultados": [
         {"series": [{"localidade": "São Paulo", "serie": {"2025": "1"}}]}]}],
     lambda: ibge.ibge_populacao("SP"), ["IBGE/SIDRA", "localidade", "objeto"]),
    ("sidra-resultados-texto", SIDRA, [{"variavel": "PIB", "resultados": "n/d"}],
     lambda: ibge.ibge_pib("BR"), ["IBGE/SIDRA", "resultados", "lista"]),
    ("sidra-objeto-no-lugar-da-lista", SIDRA, {"erro": "agregado inválido"},
     lambda: ibge.ibge_sidra("4709", "93"), ["IBGE/SIDRA", "lista"]),
    ("municipios-sem-id", MUNICIPIOS, [{"nome": "Campinas"}],
     lambda: ibge.ibge_municipios("campinas"), ["IBGE/Localidades", "'id'"]),
    ("municipios-objeto", MUNICIPIOS, {"municipios": []},
     lambda: ibge.ibge_municipios("campinas", "SP"), ["IBGE/Localidades", "lista"]),
    ("inmet-estacao-sem-codigo", INMET_ESTACOES, [{"DC_NOME": "BRASILIA", "SG_ESTADO": "DF"}],
     lambda: inmet.inmet_estacoes("T"), ["INMET/estações", "'CD_ESTACAO'"]),
    ("inmet-estacoes-objeto", INMET_ESTACOES, {"message": "manutenção"},
     lambda: inmet.inmet_estacoes("T"), ["INMET/estações", "lista"]),
    ("inmet-dados-objeto", INMET_DADOS, {"message": "token inválido"},
     lambda: inmet.inmet_dados("A001"), ["INMET/observações", "lista"]),
    ("inmet-dados-registro-texto", INMET_DADOS, ["A001;2026-09-22;25.1"],
     lambda: inmet.inmet_dados("A001"), ["INMET/observações", "registro", "objeto"]),
    ("camara-deputado-sem-nome", CAMARA + "deputados", {"dados": [{"id": 1}]},
     lambda: camara.camara_deputados(uf="SP"), ["Câmara dos Deputados", "'nome'"]),
    ("camara-deputado-id-texto", CAMARA + "deputados",
     {"dados": [{"id": "abc", "nome": "Fulano"}]},
     lambda: camara.camara_deputados(uf="SP"), ["Câmara dos Deputados", "id"]),
    ("camara-dados-objeto", CAMARA + "deputados", {"dados": {"id": 1}},
     lambda: camara.camara_deputados(), ["Câmara dos Deputados", "dados", "lista"]),
    ("camara-resposta-lista", CAMARA + "proposicoes", [{"id": 1}],
     lambda: camara.camara_proposicoes(ano=2025), ["Câmara dos Deputados", "objeto"]),
    ("camara-proposicao-sem-siglaTipo", CAMARA + "proposicoes",
     {"dados": [{"id": 1, "numero": 10, "ano": 2025}]},
     lambda: camara.camara_proposicoes(ano=2025), ["Câmara dos Deputados", "'siglaTipo'"]),
    ("camara-votacao-sem-id", CAMARA + "votacoes", {"dados": [{"data": "2025-01-01"}]},
     lambda: camara.camara_votacoes_proposicao(123), ["Câmara dos Deputados", "'id'"]),
    ("camara-evento-sem-id", CAMARA + "eventos", {"dados": [{"descricao": "Sessão"}]},
     lambda: camara.camara_agenda(1), ["Câmara dos Deputados", "'id'"]),
    ("camara-ultimoStatus-texto", CAMARA + "deputados/204554",
     {"dados": {"ultimoStatus": "em exercício"}},
     lambda: camara.camara_detalhes_deputado(204554), ["Câmara dos Deputados", "ultimoStatus"]),
    ("camara-tramitacoes-texto", CAMARA + "proposicoes/123/tramitacoes", {"dados": "n/d"},
     lambda: camara.camara_tramitacao(123), ["Câmara dos Deputados", "dados", "lista"]),
    ("senado-senadores-sem-raiz", SENADO + "senador/lista/atual.json", {},
     lambda: senado.senado_senadores(), ["Senado Federal", "'ListaParlamentarEmExercicio'"]),
    ("senado-parlamentares-texto", SENADO + "senador/lista/atual.json",
     {"ListaParlamentarEmExercicio": {"Parlamentares": "n/d"}},
     lambda: senado.senado_senadores(), ["Senado Federal", "Parlamentares", "objeto"]),
    ("senado-materia-texto", SENADO + "materia/pesquisa/lista.json",
     {"PesquisaBasicaMateria": {"Materias": {"Materia": "PL 1/2026"}}},
     lambda: senado.senado_materias(), ["Senado Federal", "Materia", "lista"]),
    ("senado-votacoes-sem-raiz", SENADO + "materia/votacoes/", {"Materia": {}},
     lambda: senado.senado_votacoes(123), ["Senado Federal", "'VotacaoMateria'"]),
    ("senado-votos-texto", SENADO + "materia/votacoes/",
     {"VotacaoMateria": {"Materia": {"Votacoes": {"Votacao": {"Votos": "secreto"}}}}},
     lambda: senado.senado_votacoes(123), ["Senado Federal", "Votos", "objeto"]),
]


@pytest.mark.parametrize(
    ("prefixo", "payload", "chamada", "trechos"),
    [pytest.param(*caso[1:], id=caso[0]) for caso in CASOS],
)
@respx.mock
async def test_payload_inesperado_vira_api_error(
    monkeypatch: pytest.MonkeyPatch,
    prefixo: str,
    payload: Any,
    chamada: _Chamada,
    trechos: list[str],
) -> None:
    monkeypatch.setenv("INMET_TOKEN", "segredo-de-teste")
    respx.get(url__startswith=prefixo).mock(return_value=httpx.Response(200, json=payload))
    with pytest.raises(PayloadInesperado) as info:
        await chamada()
    mensagem = str(info.value)
    assert isinstance(info.value, ApiError)
    assert isinstance(info.value, ToolError)
    assert mensagem.startswith("Resposta inesperada de ")
    for trecho in trechos:
        assert trecho in mensagem
    assert "segredo-de-teste" not in mensagem


@respx.mock
async def test_municipio_sem_microrregiao_usa_regiao_imediata() -> None:
    # Municípios recentes (ex.: Boa Esperança do Norte/MT) vêm com microrregiao null.
    respx.get(url__startswith=MUNICIPIOS).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 5101837,
                    "nome": "Boa Esperança do Norte",
                    "microrregiao": None,
                    "regiao-imediata": {
                        "regiao-intermediaria": {"UF": {"sigla": "MT"}},
                    },
                }
            ],
        )
    )
    saida = await ibge.ibge_municipios("esperança do norte")
    assert "5101837 — Boa Esperança do Norte — MT" in saida


@respx.mock
async def test_inmet_altitude_invalida_nao_derruba_a_lista() -> None:
    respx.get(url__startswith=INMET_ESTACOES).mock(
        return_value=httpx.Response(
            200,
            json=[{"CD_ESTACAO": "A001", "DC_NOME": "BRASILIA", "SG_ESTADO": "DF",
                   "VL_ALTITUDE": "n/d"}],
        )
    )
    saida = await inmet.inmet_estacoes("T")
    assert "A001 — BRASILIA (DF)" in saida


@respx.mock
async def test_senado_item_unico_vira_lista() -> None:
    respx.get(url__startswith=SENADO + "senador/lista/atual.json").mock(
        return_value=httpx.Response(
            200,
            json={"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar": {
                "IdentificacaoParlamentar": {"CodigoParlamentar": "1", "NomeParlamentar": "Só Um"}
            }}}},
        )
    )
    saida = await senado.senado_senadores()
    assert "1 senadores:" in saida


@respx.mock
async def test_ptax_numero_como_texto_e_aceito() -> None:
    respx.get(url__startswith=PTAX).mock(
        return_value=httpx.Response(
            200, json={"value": [_cotacao(cotacaoCompra="5.2", cotacaoVenda="5.3")]}
        )
    )
    resultado = await bcb.bcb_cambio("USD", dias=1)
    assert "compra R$ 5.2, venda R$ 5.3" in texto_de(resultado)


def test_acessores() -> None:
    assert campo({"a": 1}, "a", "X") == 1
    assert lista(None, "X") == []
    assert numero({"v": "1.5"}, "v", "X") == 1.5
    assert aninhado({"a": None}, "X", "a", "b") is None
    assert aninhado({"a": {"b": 2}}, "X", "a", "b") == 2
    with pytest.raises(PayloadInesperado, match=r"X: campo 'a' ausente"):
        campo({"a": None}, "a", "X")
    with pytest.raises(PayloadInesperado, match="deveria ser um objeto, veio list"):
        objeto([], "X")
    with pytest.raises(PayloadInesperado, match="deveria ser numérico"):
        numero({"v": True}, "v", "X")
    with pytest.raises(PayloadInesperado, match=r"a\.b deveria ser um objeto"):
        aninhado({"a": {"b": "texto"}}, "X", "a", "b", "c")


def test_lendo_converte_erros_genericos_e_preserva_tool_error() -> None:
    esperado = "Resposta inesperada de X: campo 'k' ausente"
    with pytest.raises(PayloadInesperado, match=esperado), lendo("X"):
        {}["k"]  # noqa: B018
    with pytest.raises(PayloadInesperado, match="IndexError"), lendo("X"):
        [][0]  # noqa: B018
    with pytest.raises(EntradaInvalida, match="original"), lendo("X"):
        raise EntradaInvalida("original")
