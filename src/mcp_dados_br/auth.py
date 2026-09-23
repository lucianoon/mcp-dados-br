"""Autenticação bearer opcional para o transporte streamable-http.

Quando `MCP_AUTH_TOKEN` está definido, toda requisição HTTP precisa enviar
`Authorization: Bearer <token>`. Sem a variável o servidor continua aberto,
como antes, o que só é aceitável escutando em `127.0.0.1`.
"""

import json
import secrets

from starlette.types import ASGIApp, Receive, Scope, Send

_PREFIXO = b"bearer "


class ExigirBearer:
    """Middleware ASGI que rejeita com 401 requisições sem o token esperado.

    Mensagens de lifespan passam direto, para o gerenciador de sessões do SDK
    MCP subir e descer normalmente; websocket sem token é fechado.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        if not token:
            raise ValueError("O token de autenticação não pode ser vazio.")
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan" or self._autorizado(scope):
            await self._app(scope, receive, send)
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await _responder_401(send)

    def _autorizado(self, scope: Scope) -> bool:
        valores = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
        if len(valores) != 1:
            return False
        valor: bytes = valores[0]
        if valor[: len(_PREFIXO)].lower() != _PREFIXO:
            return False
        recebido = valor[len(_PREFIXO) :].strip()
        # Comparação em tempo constante: não revela quantos bytes acertaram.
        return secrets.compare_digest(recebido, self._token)


async def _responder_401(send: Send) -> None:
    corpo = json.dumps(
        {"error": "unauthorized", "error_description": "Token bearer ausente ou inválido."}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(corpo)).encode()),
                (b"www-authenticate", b'Bearer realm="mcp-dados-br"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": corpo})
