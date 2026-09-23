import logging
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server import MCPServer

from mcp_dados_br.auth import ExigirBearer
from mcp_dados_br.tools import bcb, camara, ibge, inmet, senado

logger = logging.getLogger(__name__)

_HOSTS_LOCAIS = {"127.0.0.1", "localhost", "::1"}

_INSTRUCTIONS = """\
Servidor de dados públicos brasileiros. Use as ferramentas para responder
perguntas sobre estatísticas do IBGE (população, PIB), indicadores econômicos
do Banco Central (Selic, IPCA, câmbio PTAX, expectativas do boletim Focus),
estações meteorológicas do INMET, atividade legislativa da Câmara dos
Deputados e do Senado Federal (senadores, matérias e votações). Todas as
respostas são texto em português brasileiro pronto para uso; bcb_serie,
bcb_cambio e camara_deputados também devolvem os dados em structuredContent.
Prefira sempre as ferramentas específicas antes da genérica ibge_sidra.
"""


def create_server() -> MCPServer:
    mcp = MCPServer("mcp-dados-br", instructions=_INSTRUCTIONS)
    tools: list[Callable[..., Awaitable[Any]]] = [
        ibge.ibge_populacao,
        ibge.ibge_pib,
        ibge.ibge_municipios,
        ibge.ibge_sidra,
        bcb.bcb_serie,
        bcb.bcb_cambio,
        bcb.bcb_moedas,
        bcb.bcb_focus,
        inmet.inmet_estacoes,
        inmet.inmet_dados,
        camara.camara_deputados,
        camara.camara_detalhes_deputado,
        camara.camara_proposicoes,
        camara.camara_votacoes_proposicao,
        camara.camara_agenda,
        camara.camara_tramitacao,
        senado.senado_senadores,
        senado.senado_materias,
        senado.senado_votacoes,
    ]
    for tool in tools:
        mcp.tool()(tool)
    return mcp


def _configurar_logging() -> None:
    nivel = os.environ.get("MCP_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, nivel, logging.WARNING),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _servir_http(servidor: MCPServer) -> None:
    # Padrão do SDK é 127.0.0.1, correto para uso local. Em container é
    # preciso escutar em 0.0.0.0 para a porta publicada responder.
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    porta = int(os.environ.get("MCP_PORTA", "8000"))
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        if host not in _HOSTS_LOCAIS:
            logger.warning(
                "Transporte streamable-http escutando em %s sem MCP_AUTH_TOKEN: "
                "qualquer um que alcance a porta %d pode chamar as tools.",
                host,
                porta,
            )
        servidor.run(transport="streamable-http", host=host, port=porta)
        return

    import uvicorn

    app = ExigirBearer(servidor.streamable_http_app(host=host), token)
    uvicorn.run(app, host=host, port=porta, log_level=servidor.settings.log_level.lower())


def main() -> None:
    _configurar_logging()
    servidor = create_server()
    transporte = os.environ.get("MCP_TRANSPORTE", "stdio")
    if transporte == "streamable-http":
        _servir_http(servidor)
    else:
        servidor.run()


if __name__ == "__main__":
    main()
