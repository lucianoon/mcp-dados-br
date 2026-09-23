from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from mcp_dados_br import server as modulo_server
from mcp_dados_br.auth import ExigirBearer
from mcp_dados_br.server import create_server

TOKEN = "token-de-teste-bem-comprido"

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    },
}
CABECALHOS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    # O app real do SDK, com o gerenciador de sessões subindo pelo lifespan que
    # o middleware precisa deixar passar. base_url local por causa da proteção
    # contra DNS rebinding do SDK.
    app = ExigirBearer(create_server().streamable_http_app(), TOKEN)
    with TestClient(app, base_url="http://127.0.0.1:8000") as c:
        yield c


def test_sem_authorization_recebe_401(cliente: TestClient) -> None:
    resposta = cliente.post("/mcp", json=INITIALIZE, headers=CABECALHOS)
    assert resposta.status_code == 401
    assert resposta.headers["www-authenticate"].startswith("Bearer")
    assert resposta.json()["error"] == "unauthorized"


@pytest.mark.parametrize(
    "authorization",
    [
        f"Bearer {TOKEN}x",
        f"Bearer {TOKEN[:-1]}",
        "Bearer ",
        f"Basic {TOKEN}",
        TOKEN,
    ],
)
def test_token_errado_ou_esquema_errado_recebe_401(cliente: TestClient, authorization: str) -> None:
    resposta = cliente.post(
        "/mcp", json=INITIALIZE, headers={**CABECALHOS, "Authorization": authorization}
    )
    assert resposta.status_code == 401


def test_token_correto_inicializa_sessao_mcp(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/mcp", json=INITIALIZE, headers={**CABECALHOS, "Authorization": f"Bearer {TOKEN}"}
    )
    assert resposta.status_code == 200
    assert "mcp-dados-br" in resposta.text


def test_esquema_bearer_nao_diferencia_maiusculas(cliente: TestClient) -> None:
    resposta = cliente.post(
        "/mcp", json=INITIALIZE, headers={**CABECALHOS, "Authorization": f"bearer {TOKEN}"}
    )
    assert resposta.status_code == 200


def test_token_vazio_e_recusado_na_construcao() -> None:
    with pytest.raises(ValueError):
        ExigirBearer(create_server().streamable_http_app(), "")


def test_main_com_token_envolve_app_no_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[dict[str, object]] = []

    def uvicorn_falso(app: object, **kwargs: object) -> None:
        chamadas.append({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", uvicorn_falso)
    monkeypatch.setenv("MCP_TRANSPORTE", "streamable-http")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORTA", "9100")
    monkeypatch.setenv("MCP_AUTH_TOKEN", f"  {TOKEN}  ")

    modulo_server.main()

    assert len(chamadas) == 1
    assert isinstance(chamadas[0]["app"], ExigirBearer)
    assert chamadas[0]["host"] == "0.0.0.0"
    assert chamadas[0]["port"] == 9100


def test_main_sem_token_em_host_publico_avisa(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class ServidorFalso:
        def run(self, transport: str = "stdio", **kwargs: object) -> None:
            pass

    monkeypatch.setattr(modulo_server, "create_server", lambda: ServidorFalso())
    monkeypatch.setenv("MCP_TRANSPORTE", "streamable-http")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    with caplog.at_level("WARNING", logger="mcp_dados_br.server"):
        modulo_server.main()

    assert any("MCP_AUTH_TOKEN" in r.getMessage() for r in caplog.records)
