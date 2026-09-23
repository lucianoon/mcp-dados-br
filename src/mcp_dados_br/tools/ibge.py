import re
from typing import Annotated, Any

from pydantic import Field

from mcp_dados_br.http import ApiError, get_json
from mcp_dados_br.validacao import (
    ANO_MINIMO,
    codigo_uf,
    validar_ano,
    validar_padrao,
    validar_texto,
    validar_uf,
)

_SIDRA_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"
_LOCALIDADES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades"

_MAX_LINHAS = 40

# agregado, variavel e periodos viram segmentos do caminho da URL: só dígitos e
# os separadores da sintaxe SIDRA, nunca "/" ou "?".
_AGREGADO = re.compile(r"\d{1,6}")
_VARIAVEL = re.compile(r"\d{1,8}(\|\d{1,8})*|all|allxp")
_PERIODOS = re.compile(r"-?\d{1,6}([|-]\d{1,6})*")
# Níveis geográficos, ex.: N1[1], N3[35,33], N6[N3[35]], N3[all]|N1[all].
_LOCALIDADES = re.compile(r"N\d{1,3}\[[A-Za-z0-9\[\],]+\](\|N\d{1,3}\[[A-Za-z0-9\[\],]+\])*")


def _localidade_sidra(uf: str) -> str:
    sigla = validar_uf(uf, permitir_br=True)
    if sigla == "BR":
        return "N1[1]"
    return f"N3[{codigo_uf(sigla)}]"


async def _consultar_sidra(
    agregado: str, variavel: str, localidades: str, periodos: str
) -> Any:
    url = f"{_SIDRA_URL}/{agregado}/periodos/{periodos}/variaveis/{variavel}"
    return await get_json(url, params={"localidades": localidades})


def _sufixo_classificacao(resultado: dict[str, Any]) -> str:
    partes: list[str] = []
    for classificacao in resultado.get("classificacoes") or []:
        categorias = classificacao.get("categoria") or {}
        for nome in categorias.values():
            if nome != "Total":
                partes.append(nome)
    if not partes:
        return ""
    return f" ({'/'.join(partes)})"


def _formatar_sidra(dados: Any, max_linhas: int = _MAX_LINHAS) -> str:
    if not isinstance(dados, list):
        raise ApiError(f"Resposta inesperada do SIDRA: {str(dados)[:200]}")
    linhas: list[str] = []
    for item in dados:
        nome_variavel = item.get("variavel", "?")
        unidade = item.get("unidade", "")
        for resultado in item.get("resultados") or []:
            sufixo = _sufixo_classificacao(resultado)
            for serie in resultado.get("series") or []:
                localidade = serie.get("localidade", {}).get("nome", "?")
                for periodo, valor in (serie.get("serie") or {}).items():
                    if valor in (None, "", "..."):
                        continue
                    linhas.append(
                        f"{nome_variavel}{sufixo} ({unidade}) — "
                        f"{localidade} [{periodo}]: {valor}"
                    )
    if not linhas:
        return "Nenhum dado encontrado para os parâmetros informados."
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas] + [f"... (+{len(linhas) - max_linhas} linhas omitidas)"]
    return "\n".join(linhas)


_Ano = Annotated[int | None, Field(ge=ANO_MINIMO)]


async def ibge_populacao(uf: str = "BR", ano: _Ano = None) -> str:
    """População residente de uma unidade da federação ou do Brasil (IBGE/SIDRA).

    Args:
        uf: Sigla da UF (ex.: "SP", "RJ") ou "BR" para o total nacional.
        ano: Ano de referência. Se omitido, retorna o período mais recente disponível.
    """
    periodos = str(validar_ano("ano", ano)) if ano is not None else "-1"
    dados = await _consultar_sidra("4709", "93", _localidade_sidra(uf), periodos)
    return _formatar_sidra(dados)


async def ibge_pib(uf: str = "BR", ano: _Ano = None) -> str:
    """PIB a preços correntes de uma unidade da federação ou do Brasil (IBGE/SIDRA).

    Args:
        uf: Sigla da UF (ex.: "MG", "BA") ou "BR" para o total nacional.
        ano: Ano de referência. Se omitido, retorna o período mais recente disponível.
    """
    periodos = str(validar_ano("ano", ano)) if ano is not None else "-1"
    dados = await _consultar_sidra("5938", "37", _localidade_sidra(uf), periodos)
    return _formatar_sidra(dados)


async def ibge_municipios(nome: str, uf: str | None = None) -> str:
    """Busca municípios brasileiros pelo nome (IBGE), com filtro opcional por UF.

    Args:
        nome: Nome (total ou parcial) do município, ex.: "campinas".
        uf: Sigla opcional da UF para restringir a busca, ex.: "SP".
    """
    termo = validar_texto("nome", nome, minimo=2, maximo=100).casefold()
    if uf:
        url = f"{_LOCALIDADES_URL}/estados/{validar_uf(uf)}/municipios"
        dados = await get_json(url)
    else:
        dados = await get_json(f"{_LOCALIDADES_URL}/municipios")
    correspondencias = [
        m for m in dados
        if termo in str(m.get("nome", "")).casefold()
    ]
    if not correspondencias:
        return f"Nenhum município encontrado com o nome {nome!r}."

    def _sigla_uf(m: dict[str, Any]) -> str:
        uf_info = (m.get("microrregiao") or {}).get("mesorregiao", {}).get("UF", {})
        return str(uf_info.get("sigla") or "?")

    linhas = [
        f"{m['id']} — {m['nome']} — {_sigla_uf(m)}"
        for m in correspondencias[:20]
    ]
    if len(correspondencias) > 20:
        linhas.append(f"... (+{len(correspondencias) - 20} resultados omitidos)")
    return "\n".join(linhas)


async def ibge_sidra(
    agregado: str,
    variavel: str,
    localidades: str = "N1[1]",
    periodos: str = "-1",
) -> str:
    """Consulta genérica à API SIDRA do IBGE para qualquer indicador.

    Args:
        agregado: ID do agregado SIDRA (ex.: "4709" população, "5938" PIB, "1737" inflação INPC).
            Consulte https://servicodados.ibge.gov.br/api/v3/agregados para a lista completa.
        variavel: ID da variável dentro do agregado (ex.: "93").
        localidades: Filtro de localidades no formato SIDRA, ex.: "N1[1]" Brasil,
            "N3[35]" São Paulo (estado), "N6[3550308]" Campinas (município).
        periodos: Períodos, ex.: "-1" (último), "-5" (últimos 5), "2022",
            "2020-2024" (intervalo) ou "2020|2022" (lista).
    """
    agregado = validar_padrao("agregado", agregado, _AGREGADO, '"4709"')
    variavel = validar_padrao("variavel", variavel, _VARIAVEL, '"93" ou "93|1000093"')
    localidades = validar_padrao(
        "localidades", localidades, _LOCALIDADES, '"N1[1]", "N3[35]" ou "N6[3550308]"'
    )
    periodos = validar_padrao("periodos", periodos, _PERIODOS, '"-1", "2022" ou "2020-2024"')
    dados = await _consultar_sidra(agregado, variavel, localidades, periodos)
    return _formatar_sidra(dados)
