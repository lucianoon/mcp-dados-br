import httpx
import pytest
import respx

from mcp_dados_br import __version__
from mcp_dados_br.http import ApiError, cache_key, get_json


@respx.mock
async def test_get_json_sucesso() -> None:
    route = respx.get("https://api.exemplo.test/dados").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    resultado = await get_json("https://api.exemplo.test/dados")
    assert resultado == {"ok": True}
    assert route.called


@respx.mock
async def test_get_json_registra_aviso_no_retry(caplog: pytest.LogCaptureFixture) -> None:
    respx.get("https://api.exemplo.test/flaky-log").mock(
        side_effect=[
            httpx.ConnectTimeout("timeout"),
            httpx.Response(200, json={}),
        ]
    )
    with caplog.at_level("WARNING", logger="mcp_dados_br.http"):
        await get_json("https://api.exemplo.test/flaky-log")
    avisos = [r for r in caplog.records if "Tentativa 1 falhou" in r.getMessage()]
    assert len(avisos) == 1


@respx.mock
async def test_token_inmet_nao_vaza_em_logs_nem_erros(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INMET_TOKEN", "segredo-ultra")
    respx.get(
        "https://apitempo.inmet.gov.br/token/estacao/2026-01-01/2026-01-02/A001/segredo-ultra"
    ).mock(return_value=httpx.Response(400, json={}))

    with pytest.raises(ApiError) as excinfo:
        await get_json(
            "https://apitempo.inmet.gov.br/token/estacao/2026-01-01/2026-01-02/A001/segredo-ultra"
        )
    assert "segredo-ultra" not in str(excinfo.value)
    assert "***" in str(excinfo.value)

    monkeypatch.setenv("INMET_TOKEN", "outro-segredo")
    respx.get(
        "https://apitempo.inmet.gov.br/token/estacao/2026-01-01/2026-01-02/A001/outro-segredo"
    ).mock(side_effect=httpx.ConnectError("sem conexão"))
    with caplog.at_level("DEBUG", logger="mcp_dados_br.http"), pytest.raises(ApiError):
        await get_json(
            "https://apitempo.inmet.gov.br/token/estacao/2026-01-01/2026-01-02/A001/outro-segredo"
        )
    for registro in caplog.records:
        assert "outro-segredo" not in registro.getMessage()


@respx.mock
async def test_get_json_usa_cache_na_segunda_chamada() -> None:
    route = respx.get("https://api.exemplo.test/dados").mock(
        return_value=httpx.Response(200, json={"n": 42})
    )
    primeiro = await get_json("https://api.exemplo.test/dados")
    segundo = await get_json("https://api.exemplo.test/dados")
    assert route.call_count == 1
    assert primeiro == segundo


@respx.mock
async def test_get_json_erro_4xx_levanta_apierror() -> None:
    respx.get("https://api.exemplo.test/erro").mock(
        return_value=httpx.Response(400, json={"erro": "requisição inválida"})
    )
    with pytest.raises(ApiError, match="HTTP 400"):
        await get_json("https://api.exemplo.test/erro")


@respx.mock
async def test_get_json_resposta_nao_json_levanta_apierror() -> None:
    respx.get("https://api.exemplo.test/html").mock(
        return_value=httpx.Response(200, text="<html>ops</html>")
    )
    with pytest.raises(ApiError, match="não-JSON"):
        await get_json("https://api.exemplo.test/html")


@respx.mock
async def test_get_json_tenta_novamente_apos_erro_de_rede() -> None:
    route = respx.get("https://api.exemplo.test/flaky").mock(
        side_effect=[
            httpx.ConnectTimeout("timeout"),
            httpx.Response(200, json={"tentativa": 2}),
        ]
    )
    resultado = await get_json("https://api.exemplo.test/flaky")
    assert resultado == {"tentativa": 2}
    assert route.call_count == 2


@respx.mock
async def test_get_json_esgota_tentativas() -> None:
    route = respx.get("https://api.exemplo.test/offline").mock(
        side_effect=httpx.ConnectError("sem conexão")
    )
    with pytest.raises(ApiError, match="Falha ao consultar"):
        await get_json("https://api.exemplo.test/offline")
    assert route.call_count == 3


@respx.mock
async def test_get_json_tenta_novamente_apos_5xx_do_upstream() -> None:
    route = respx.get("https://api.exemplo.test/instavel").mock(
        side_effect=[
            httpx.Response(504, text="upstream request timeout"),
            httpx.Response(200, json={"tentativa": 2}),
        ]
    )
    resultado = await get_json("https://api.exemplo.test/instavel")
    assert resultado == {"tentativa": 2}
    assert route.call_count == 2


@respx.mock
async def test_get_json_5xx_persistente_levanta_apierror_com_status() -> None:
    route = respx.get("https://api.exemplo.test/caido").mock(
        return_value=httpx.Response(503, text="indisponível")
    )
    with pytest.raises(ApiError, match="HTTP 503"):
        await get_json("https://api.exemplo.test/caido")
    assert route.call_count == 3


@respx.mock
async def test_get_json_nao_repete_em_4xx() -> None:
    route = respx.get("https://api.exemplo.test/nao-existe").mock(
        return_value=httpx.Response(404, json={"erro": "não encontrado"})
    )
    with pytest.raises(ApiError, match="HTTP 404"):
        await get_json("https://api.exemplo.test/nao-existe")
    assert route.call_count == 1


def test_cache_key_independe_da_ordem_dos_params() -> None:
    assert cache_key("https://x.test/api", {"b": "2", "a": "1"}) == cache_key(
        "https://x.test/api", {"a": "1", "b": "2"}
    )


def test_cache_key_ignora_parametros_none() -> None:
    assert cache_key("https://x.test/api", {"a": "1", "vazio": None}) == cache_key(
        "https://x.test/api", {"a": "1"}
    )


def test_cache_key_trata_int_e_str_iguais() -> None:
    # Os dois viram a mesma query string, então devem compartilhar o cache.
    assert cache_key("https://x.test/api", {"n": 1}) == cache_key("https://x.test/api", {"n": "1"})


def test_cache_key_nao_confunde_valor_com_separadores() -> None:
    # Na chave antiga ("url?a=1&b=2") os dois casos colidiam.
    um_param = cache_key("https://x.test/api", {"a": "1&b=2"})
    dois_params = cache_key("https://x.test/api", {"a": "1", "b": "2"})
    assert um_param != dois_params
    assert cache_key("https://x.test/api?a=1", None) != cache_key("https://x.test/api", {"a": "1"})


@respx.mock
async def test_valores_com_separadores_nao_reaproveitam_cache() -> None:
    route = respx.get("https://api.exemplo.test/busca").mock(
        side_effect=[httpx.Response(200, json={"n": 1}), httpx.Response(200, json={"n": 2})]
    )
    primeiro = await get_json("https://api.exemplo.test/busca", {"q": "a&x=1"})
    segundo = await get_json("https://api.exemplo.test/busca", {"q": "a", "x": "1"})
    assert (primeiro, segundo) == ({"n": 1}, {"n": 2})
    assert route.call_count == 2


@respx.mock
async def test_user_agent_usa_versao_instalada() -> None:
    route = respx.get("https://api.exemplo.test/ua").mock(
        return_value=httpx.Response(200, json={})
    )
    await get_json("https://api.exemplo.test/ua")
    agente = route.calls.last.request.headers["User-Agent"]
    assert agente.startswith(f"mcp-dados-br/{__version__} ")
    assert __version__ != "0.1.0"
