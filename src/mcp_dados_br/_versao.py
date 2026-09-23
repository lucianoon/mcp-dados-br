from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-dados-br")
except PackageNotFoundError:  # pragma: no cover - só fora de um ambiente instalado
    __version__ = "0+desconhecida"
