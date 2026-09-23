import os
import re
from datetime import date, timedelta
from typing import Annotated, Any

from pydantic import Field

from mcp_dados_br.http import get_json
from mcp_dados_br.payload import lista, objeto, texto
from mcp_dados_br.validacao import EntradaInvalida, validar_inteiro, validar_padrao, validar_uf

_INMET_URL = "https://apitempo.inmet.gov.br"

_TIPOS = {
    "t": "T",
    "automatica": "T",
    "automaticas": "T",
    "m": "M",
    "convencional": "M",
    "convencionais": "M",
}

_MAX_LINHAS = 40
_DADOS_DIAS_MAX = 7
# Automáticas: letra + 3 dígitos (A001). Convencionais: código OMM de 5 dígitos.
_ESTACAO = re.compile(r"[A-Z]\d{3}|\d{5}")

_CAMPOS_OBSERVADOS = [
    ("TEM_INS", "temp °C"),
    ("UMD_INS", "ur %"),
    ("VEN_VEL", "vento m/s"),
    ("PRE_INS", "pressão hPa"),
    ("CHUVA", "chuva mm"),
]


def _normalizar_tipo(tipo: str) -> str:
    codigo = _TIPOS.get(tipo.strip().casefold())
    if codigo is None:
        validos = ", ".join(sorted(set(_TIPOS.values())))
        raise EntradaInvalida(
            f"Tipo desconhecido: {tipo!r}. "
            f"Use T (automática) ou M (convencional). Válidos: {validos}"
        )
    return codigo


def _altitude(valor: Any) -> str:
    # Altitude é informativa: valor fora do formato é omitido, não derruba a lista.
    try:
        return f", {float(valor):.0f} m" if valor else ""
    except (TypeError, ValueError):
        return ""


async def inmet_estacoes(tipo: str = "T", uf: str | None = None) -> str:
    """Lista estações meteorológicas do INMET (não requer autenticação).

    Args:
        tipo: "T" para estações automáticas ou "M" para convencionais.
        uf: Sigla opcional da UF para filtrar, ex.: "SP".
    """
    codigo_tipo = _normalizar_tipo(tipo)
    sigla = validar_uf(uf) if uf else None
    fonte = "INMET/estações"
    dados = await get_json(f"{_INMET_URL}/estacoes/{codigo_tipo}")
    estacoes = [objeto(e, fonte, "estação") for e in lista(dados, fonte)]
    if sigla:
        estacoes = [e for e in estacoes if e.get("SG_ESTADO") == sigla]
    operantes = [e for e in estacoes if e.get("CD_SITUACAO") != "Desativada"]
    rotulo = "automáticas" if codigo_tipo == "T" else "convencionais"
    if not operantes:
        return f"Nenhuma estação {rotulo} encontrada para os filtros informados."
    linhas = [f"{len(operantes)} estações {rotulo}:"]
    for e in operantes[:_MAX_LINHAS]:
        altitude_txt = _altitude(e.get("VL_ALTITUDE"))
        capital = " [capital]" if e.get("FL_CAPITAL") == "S" else ""
        linhas.append(
            f"{texto(e, 'CD_ESTACAO', fonte)} — {e.get('DC_NOME')} "
            f"({e.get('SG_ESTADO')}{capital}{altitude_txt})"
        )
    if len(operantes) > _MAX_LINHAS:
        linhas.append(f"... (+{len(operantes) - _MAX_LINHAS} estações omitidas)")
    return "\n".join(linhas)


def _formatar_registro(registro: dict[str, Any]) -> str:
    data_m = str(registro.get("DT_MEDICAO", "?"))
    hora_m = str(registro.get("HR_MEDICAO", "")).zfill(4)
    momento = f"{data_m} {hora_m[:2]}:{hora_m[2:]}" if hora_m else data_m
    partes = [
        f"{rotulo} {registro[campo]}"
        for campo, rotulo in _CAMPOS_OBSERVADOS
        if registro.get(campo) not in (None, "")
    ]
    return f"{momento} UTC — " + (" | ".join(partes) if partes else "sem medições")


async def inmet_dados(
    estacao: str,
    dias: Annotated[int, Field(ge=1, le=_DADOS_DIAS_MAX)] = 2,
) -> str:
    """Dados horários observados de uma estação automática do INMET (últimos dias).

    Requer o ambiente INMET_TOKEN com token fornecido pelo INMET
    (solicite em https://portal.inmet.gov.br). Sem token, use inmet_estacoes.

    Args:
        estacao: Código da estação, ex.: "A001". Liste códigos com inmet_estacoes.
        dias: Quantidade de dias retroativos a consultar (padrão 2, de 1 a 7).
    """
    estacao = validar_padrao("estacao", estacao.upper(), _ESTACAO, '"A001" ou "83377"')
    dias = validar_inteiro("dias", dias, 1, _DADOS_DIAS_MAX)
    token = os.environ.get("INMET_TOKEN")
    if not token:
        return (
            "Consulta indisponível: os dados observacionais do INMET exigem um token. "
            "Solicite em https://portal.inmet.gov.br e configure a variável de "
            "ambiente INMET_TOKEN no servidor MCP."
        )
    fim = date.today()
    inicio = fim - timedelta(days=dias)
    url = (
        f"{_INMET_URL}/token/estacao/{inicio.isoformat()}/"
        f"{fim.isoformat()}/{estacao}/{token}"
    )
    fonte = "INMET/observações"
    dados = await get_json(url)
    registros = [objeto(r, fonte, "registro") for r in lista(dados, fonte)]
    if not registros:
        return f"Nenhum dado retornado para a estação {estacao} no período."
    ultimos = registros[-72:]
    cabecalho = (
        f"Estação {estacao}: {len(registros)} registros; "
        f"exibindo os últimos {len(ultimos)}:"
    )
    return "\n".join([cabecalho] + [_formatar_registro(r) for r in ultimos])
