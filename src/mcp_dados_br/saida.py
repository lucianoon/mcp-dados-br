"""Resultado de tool com texto e dados estruturados ao mesmo tempo.

O texto continua sendo o que o modelo lê (`content`); os mesmos dados vão em
`structuredContent`, validados pelo `outputSchema` que o SDK deriva do modelo
pydantic anotado no retorno: `Annotated[CallToolResult, MeuModelo]`.
"""

from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel


def resultado(texto: str, dados: BaseModel) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=texto)],
        structured_content=dados.model_dump(mode="json"),
    )


def texto_de(resultado: CallToolResult) -> str:
    """Texto do primeiro bloco; útil para quem chama a tool direto do Python."""
    bloco = resultado.content[0]
    assert isinstance(bloco, TextContent)
    return bloco.text
