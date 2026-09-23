"""Leitura defensiva dos payloads das APIs upstream.

As APIs públicas mudam de formato sem aviso. Sem estas funções, um campo
renomeado vira `KeyError` ou `TypeError` genérico e o cliente MCP recebe só
"Error executing tool". Aqui toda surpresa no payload vira `PayloadInesperado`
(um `ApiError`, portanto `ToolError`), com a fonte e o campo na mensagem.

- `campo`, `objeto`, `lista` e `numero` validam o que a tool vai usar.
- `lendo(fonte)` é a rede de segurança em volta do trecho que interpreta o
  payload: o que escapar dos acessores também vira `PayloadInesperado`.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from mcp.server.mcpserver.exceptions import ToolError

from mcp_dados_br.http import ApiError

_LIMITE_DETALHE = 200


class PayloadInesperado(ApiError):
    """Resposta da API upstream fora do formato esperado."""


def _tipo(valor: Any) -> str:
    return "null" if valor is None else type(valor).__name__


def _falha(fonte: str, detalhe: str) -> PayloadInesperado:
    return PayloadInesperado(
        f"Resposta inesperada de {fonte}: {detalhe[:_LIMITE_DETALHE]}. "
        "A API pode ter mudado de formato."
    )


def objeto(valor: Any, fonte: str, contexto: str = "resposta") -> dict[str, Any]:
    """Exige um objeto JSON."""
    if not isinstance(valor, dict):
        raise _falha(fonte, f"{contexto} deveria ser um objeto, veio {_tipo(valor)}")
    return valor


def lista(valor: Any, fonte: str, contexto: str = "resposta") -> list[Any]:
    """Exige uma lista JSON; `null` conta como lista vazia."""
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise _falha(fonte, f"{contexto} deveria ser uma lista, veio {_tipo(valor)}")
    return valor


def campo(registro: Any, chave: str, fonte: str) -> Any:
    """Valor obrigatório de `registro[chave]`; ausente ou `null` é erro."""
    valor = objeto(registro, fonte, f"registro com o campo {chave!r}").get(chave)
    if valor is None:
        raise _falha(fonte, f"campo {chave!r} ausente")
    return valor


def texto(registro: Any, chave: str, fonte: str) -> str:
    """Campo obrigatório como texto."""
    return str(campo(registro, chave, fonte))


def numero(registro: Any, chave: str, fonte: str) -> float:
    """Campo obrigatório convertido para `float`."""
    valor = campo(registro, chave, fonte)
    if isinstance(valor, bool):
        raise _falha(fonte, f"campo {chave!r} deveria ser numérico, veio {valor!r}")
    try:
        return float(valor)
    except (TypeError, ValueError):
        raise _falha(
            fonte, f"campo {chave!r} deveria ser numérico, veio {str(valor)[:40]!r}"
        ) from None


def aninhado(valor: Any, fonte: str, *chaves: str) -> Any:
    """Percorre objetos aninhados; chave ausente ou `null` no caminho devolve `None`.

    Um nível que exista mas não seja objeto é mudança de formato e vira erro.
    """
    atual = valor
    percorrido: list[str] = []
    for chave in chaves:
        if atual is None:
            return None
        caminho = ".".join(percorrido) or "resposta"
        atual = objeto(atual, fonte, caminho).get(chave)
        percorrido.append(chave)
    return atual


@contextmanager
def lendo(fonte: str) -> Iterator[None]:
    """Converte erros de interpretação do payload em `PayloadInesperado`.

    `ToolError` (inclusive os já levantados pelos acessores) passa intacto.
    """
    try:
        yield
    except ToolError:
        raise
    except KeyError as exc:
        chave = exc.args[0] if exc.args else "?"
        raise _falha(fonte, f"campo {chave!r} ausente") from exc
    except (TypeError, ValueError, IndexError, AttributeError) as exc:
        raise _falha(fonte, f"{type(exc).__name__}: {exc}") from exc
