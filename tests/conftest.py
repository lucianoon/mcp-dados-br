import re

import pytest

from mcp_dados_br.http import ApiError, reset_cache

# 5xx e falha de transporte depois dos retries indicam API pública fora do ar,
# não contrato quebrado: nos testes de integração isso vira skip, e 4xx ou
# mudança de formato continuam falhando.
_INDISPONIVEL = re.compile(r"^(HTTP 5\d\d |Falha ao consultar )")


@pytest.fixture(autouse=True)
def _cache_limpo_por_teste() -> None:
    reset_cache()
    yield
    reset_cache()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item):
    try:
        return (yield)
    except ApiError as exc:
        if item.get_closest_marker("integration") and _INDISPONIVEL.match(str(exc)):
            pytest.skip(f"API externa indisponível: {exc}")
        raise
