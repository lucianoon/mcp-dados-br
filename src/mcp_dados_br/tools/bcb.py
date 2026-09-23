from datetime import date, datetime, timedelta
from typing import Annotated, Any

from mcp.types import CallToolResult
from pydantic import BaseModel, Field

from mcp_dados_br.http import get_json
from mcp_dados_br.saida import resultado
from mcp_dados_br.validacao import (
    EntradaInvalida,
    validar_data,
    validar_id,
    validar_inteiro,
    validar_moeda,
)

_SGS_URL = "https://api.bcb.gov.br/dados/serie"
_OLINDA_URL = "https://olinda.bcb.gov.br/olinda/servico"
_PTAX_URL = f"{_OLINDA_URL}/PTAX/versao/v1/odata"
_FOCUS_URL = f"{_OLINDA_URL}/Expectativas/versao/v1/odata"

_FOCUS_ENTIDADES = {
    "selic": ("ExpectativasMercadoSelic", None),
    "ipca": ("ExpectativasMercadoTop5Inflacao12Meses", "Indicador eq 'IPCA'"),
    "pib": ("ExpectativasMercadoTop5Anuais", "Indicador eq 'PIB Total'"),
    "cambio": ("ExpectativasMercadoTop5Anuais", "Indicador eq 'Câmbio'"),
}

_INDICADORES_SGS = {
    "selic": 1178,
    "cdi": 4390,
    "ipca": 433,
    "ipca_12m": 13522,
    "igpm": 189,
    "inpc": 206,
    "salario_minimo": 36,
}

_CAMBIO_DIAS_MAX = 30
# Cada dia útil tem até 5 boletins PTAX (abertura, 3 intermediários e
# fechamento); o $top precisa cobrir todos os da janela, senão o OData corta
# os dias mais recentes.
_PTAX_BOLETINS_POR_DIA = 5
_SGS_MAX_EXIBIDOS = 60


class RegistroSGS(BaseModel):
    data: date
    valor: float | None = Field(description="Valor publicado; null se vier vazio do SGS.")


class SerieSGS(BaseModel):
    """Série do SGS. `registros` traz os últimos 60 do período."""

    codigo: int
    data_inicial: date
    data_final: date
    total_registros: int
    registros: list[RegistroSGS]


class CotacaoPTAX(BaseModel):
    data: date
    compra: float
    venda: float


class CambioPTAX(BaseModel):
    """Cotações PTAX de fechamento (ou do último boletim do dia, na falta dele)."""

    moeda: str
    cotacoes: list[CotacaoPTAX]
    ultima: CotacaoPTAX | None
    compra_min: float | None
    compra_max: float | None
    compra_media: float | None
    venda_min: float | None
    venda_max: float | None


def _valor_sgs(valor: Any) -> float | None:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _data_sgs(iso: str) -> str:
    ano, mes, dia = iso.split("-")
    return f"{dia}/{mes}/{ano}"


def _data_ptax(iso: str) -> str:
    ano, mes, dia = iso.split("-")
    return f"{mes}-{dia}-{ano}"


async def bcb_serie(
    indicador: str | None = None,
    data_inicial: str | None = None,
    data_final: str | None = None,
    codigo: Annotated[int | None, Field(ge=1)] = None,
) -> Annotated[CallToolResult, SerieSGS]:
    """Consulta séries temporais do Sistema Gerenciador de Séries (SGS) do Banco Central.

    Args:
        indicador: Atalho nomeado, um de: "selic", "cdi", "ipca", "ipca_12m",
            "igpm", "inpc" ou "salario_minimo". Prefira este parâmetro.
        data_inicial: Data inicial ISO "AAAA-MM-DD". Padrão: últimos 90 dias.
        data_final: Data final ISO "AAAA-MM-DD". Padrão: hoje.
        codigo: Código bruto da série SGS para séries sem atalho
            (catálogo: https://www3.bcb.gov.br/sgspub/). Ignorado se indicador for informado.

    Além do texto, devolve os registros em structuredContent (data ISO e valor numérico).
    """
    if indicador:
        chave = indicador.strip().casefold()
        codigo_resolvido = _INDICADORES_SGS.get(chave)
        if codigo_resolvido is None:
            validos = ", ".join(sorted(_INDICADORES_SGS))
            raise EntradaInvalida(
                f"Indicador desconhecido: {indicador!r}. Válidos: {validos}"
            )
        codigo = codigo_resolvido
    elif codigo is None:
        atalhos = ", ".join(sorted(_INDICADORES_SGS))
        raise EntradaInvalida(
            "Informe o parâmetro indicador (atalhos: "
            f"{atalhos}) ou o código bruto da série SGS."
        )
    else:
        codigo = validar_id("codigo", codigo)
    fim = validar_data("data_final", data_final) if data_final else date.today()
    inicio = (
        validar_data("data_inicial", data_inicial)
        if data_inicial
        else fim - timedelta(days=90)
    )
    if inicio > fim:
        raise EntradaInvalida("data_inicial deve ser anterior ou igual a data_final.")
    url = f"{_SGS_URL}/bcdata.sgs.{codigo}/dados"
    dados: list[dict[str, Any]] = await get_json(url, params={
        "formato": "json",
        "dataInicial": _data_sgs(inicio.isoformat()),
        "dataFinal": _data_sgs(fim.isoformat()),
    })
    exibidos = dados[-_SGS_MAX_EXIBIDOS:]
    estruturado = SerieSGS(
        codigo=codigo,
        data_inicial=inicio,
        data_final=fim,
        total_registros=len(dados),
        registros=[
            RegistroSGS(
                data=datetime.strptime(item["data"], "%d/%m/%Y").date(),
                valor=_valor_sgs(item.get("valor")),
            )
            for item in exibidos
        ],
    )
    if not dados:
        texto = f"Nenhum dado retornado para a série {codigo} no período informado."
        return resultado(texto, estruturado)
    linhas = [f"{item['data']}: {item['valor']}" for item in exibidos]
    if len(dados) > _SGS_MAX_EXIBIDOS:
        linhas.insert(
            0, f"Série {codigo}: {len(dados)} registros; exibindo os últimos {_SGS_MAX_EXIBIDOS}."
        )
    else:
        linhas.insert(0, f"Série {codigo}:")
    return resultado("\n".join(linhas), estruturado)


async def bcb_cambio(
    moeda: str = "USD",
    dias: Annotated[int, Field(ge=1, le=_CAMBIO_DIAS_MAX)] = 7,
) -> Annotated[CallToolResult, CambioPTAX]:
    """Cotações de câmbio PTAX do Banco Central para uma moeda nos últimos N dias.

    Args:
        moeda: Código ISO 4217 de 3 letras (ex.: "USD", "EUR", "GBP"). Use a tool
            bcb_moedas para listar as moedas disponíveis.
        dias: Quantidade de dias úteis de cotação a retornar (padrão 7, de 1 a 30).

    Além do texto, devolve cotações e resumo numérico em structuredContent.
    """
    moeda = validar_moeda(moeda)
    dias = validar_inteiro("dias", dias, 1, _CAMBIO_DIAS_MAX)
    fim = date.today()
    # Janela em dias corridos com folga para fins de semana e feriados.
    janela = dias * 2 + 5
    inicio = fim - timedelta(days=janela)
    url = (
        f"{_PTAX_URL}/CotacaoMoedaPeriodo(moeda=@moeda,"
        f"dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
    )
    dados: dict[str, Any] = await get_json(url, params={
        "@moeda": f"'{moeda}'",
        "@dataInicial": f"'{_data_ptax(inicio.isoformat())}'",
        "@dataFinalCotacao": f"'{_data_ptax(fim.isoformat())}'",
        "$format": "json",
        "$top": janela * _PTAX_BOLETINS_POR_DIA,
    })
    cotacoes = dados.get("value") or []
    if not cotacoes:
        vazio = CambioPTAX(
            moeda=moeda, cotacoes=[], ultima=None, compra_min=None, compra_max=None,
            compra_media=None, venda_min=None, venda_max=None,
        )
        texto = (
            f"Nenhuma cotação encontrada para {moeda}. "
            "Verifique o símbolo com a tool bcb_moedas."
        )
        return resultado(texto, vazio)
    fechamentos = [c for c in cotacoes if c.get("tipoBoletim") == "Fechamento"]
    base = fechamentos if fechamentos else cotacoes
    ultimas = base[-dias:] if dias < len(base) else base
    compras = [float(c["cotacaoCompra"]) for c in ultimas]
    vendas = [float(c["cotacaoVenda"]) for c in ultimas]
    ultima = ultimas[-1]
    resumo = [
        f"PTAX {moeda} — última cotação ({ultima['dataHoraCotacao'][:10]}): "
        f"compra R$ {ultima['cotacaoCompra']}, venda R$ {ultima['cotacaoVenda']}",
        f"Período ({len(ultimas)} cotações): compra mín. R$ {min(compras)}, "
        f"máx. R$ {max(compras)}, média R$ {sum(compras) / len(compras):.4f}; "
        f"venda mín. R$ {min(vendas)}, máx. R$ {max(vendas)}",
    ]
    historico = [
        (
            f"{c['dataHoraCotacao'][:10]}: compra R$ {c['cotacaoCompra']} / "
            f"venda R$ {c['cotacaoVenda']}"
        )
        for c in ultimas
    ]
    estruturadas = [
        CotacaoPTAX(
            data=date.fromisoformat(c["dataHoraCotacao"][:10]),
            compra=float(c["cotacaoCompra"]),
            venda=float(c["cotacaoVenda"]),
        )
        for c in ultimas
    ]
    estruturado = CambioPTAX(
        moeda=moeda,
        cotacoes=estruturadas,
        ultima=estruturadas[-1],
        compra_min=min(compras),
        compra_max=max(compras),
        compra_media=round(sum(compras) / len(compras), 4),
        venda_min=min(vendas),
        venda_max=max(vendas),
    )
    return resultado("\n".join(resumo + [""] + historico), estruturado)


async def bcb_moedas() -> str:
    """Lista as moedas com cotação PTAX disponíveis no Banco Central."""
    dados: dict[str, Any] = await get_json(
        f"{_PTAX_URL}/Moedas", params={"$format": "json"}
    )
    moedas = dados.get("value") or []
    linhas = [f"{m['simbolo']} — {m['nomeFormatado']}" for m in moedas]
    return "\n".join(linhas)


def _periodo_focus(registro: dict[str, Any]) -> str:
    if registro.get("Reuniao"):
        return f"reunião {registro['Reuniao']}"
    if registro.get("DataReferencia"):
        return f"referência {registro['DataReferencia']}"
    return "próximos 12 meses"


def _formatar_focus(indicador: str, registros: list[dict[str, Any]]) -> str:
    data_pesquisa = max(str(r.get("Data")) for r in registros)
    do_dia = [r for r in registros if str(r.get("Data")) == data_pesquisa]

    def mediana(r: dict[str, Any]) -> float:
        valor = r.get("Mediana")
        return float(valor) if valor is not None else float("inf")

    ordenados = sorted(do_dia, key=mediana)
    linhas = [
        f"Focus BCB ({data_pesquisa}) — expectativas para {indicador.upper()}:"
    ]
    for r in ordenados:
        partes = [
            _periodo_focus(r),
            f"mediana {r.get('Mediana')}",
            f"média {r.get('Media')}",
            f"mín {r.get('Minimo')}",
            f"máx {r.get('Maximo')}",
        ]
        respondentes = r.get("numeroRespondentes")
        if respondentes:
            partes.append(f"{respondentes} analistas")
        linhas.append(" | ".join(partes))
    return "\n".join(linhas)


async def bcb_focus(indicador: str = "selic") -> str:
    """Expectativas de mercado do Boletim Focus (Boletim Focus) do Banco Central.

    Mostra a projeção média dos analistas de mercado para os próximos períodos.

    Args:
        indicador: Um de: "selic", "ipca", "pib" ou "cambio".
    """
    chave = indicador.strip().casefold()
    entidade_info = _FOCUS_ENTIDADES.get(chave)
    if entidade_info is None:
        validos = ", ".join(sorted(_FOCUS_ENTIDADES))
        raise EntradaInvalida(f"Indicador desconhecido: {indicador!r}. Válidos: {validos}")
    entidade, filtro_indicador = entidade_info
    desde = (date.today() - timedelta(days=7)).isoformat()
    filtro = f"Data ge '{desde}'"
    if filtro_indicador:
        filtro += f" and {filtro_indicador}"
    dados: dict[str, Any] = await get_json(
        f"{_FOCUS_URL}/{entidade}",
        params={
            "$format": "json",
            "$filter": filtro,
            "$orderby": "Data desc",
            "$top": 60,
        },
    )
    registros = dados.get("value") or []
    if chave == "selic":
        registros = [r for r in registros if r.get("baseCalculo") == 0]
    if not registros:
        return (
            f"Nenhuma expectativa recente encontrada para {chave}. "
            "O boletim Focus pode não ter sido publicado nos últimos 7 dias."
        )
    return _formatar_focus(chave, registros)
