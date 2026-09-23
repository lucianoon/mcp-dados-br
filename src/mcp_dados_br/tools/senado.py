from collections import Counter
from datetime import date
from typing import Annotated, Any

from pydantic import Field

from mcp_dados_br.http import get_json
from mcp_dados_br.validacao import (
    ANO_MINIMO,
    validar_ano,
    validar_id,
    validar_sigla_tipo,
    validar_texto,
    validar_uf,
)

_SENADO_URL = "https://legis.senado.leg.br/dadosabertos"

_TRUNCAR = 140

_SIGLAS_VOTO = {"S": "sim", "N": "não", "P": "abst.", "L": "liberado"}
_ORDEM_VOTO = ["S", "N", "P", "L"]


def _lista_ou_unica(valor: Any) -> list[dict[str, Any]]:
    if valor is None:
        return []
    if isinstance(valor, dict):
        return [valor]
    return list(valor)


def _truncar(texto: str | None, limite: int = _TRUNCAR) -> str:
    if not texto:
        return ""
    if len(texto) <= limite:
        return texto
    return f"{texto[:limite]}..."


async def senado_senadores(uf: str | None = None, busca: str | None = None) -> str:
    """Lista os senadores em exercício no Senado Federal.

    Args:
        uf: Sigla da unidade federativa para filtrar, ex.: "MG", "RS".
        busca: Nome (total ou parcial) do senador.
    """
    sigla_uf = validar_uf(uf) if uf else ""
    termo = validar_texto("busca", busca, maximo=100).casefold() if busca else ""
    dados: dict[str, Any] = await get_json(f"{_SENADO_URL}/senador/lista/atual.json")
    parlamentares = _lista_ou_unica(
        dados.get("ListaParlamentarEmExercicio", {}).get("Parlamentares", {}).get("Parlamentar")
    )
    correspondentes: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for parlamentar in parlamentares:
        identificacao = parlamentar.get("IdentificacaoParlamentar") or {}
        if sigla_uf and identificacao.get("UfParlamentar") != sigla_uf:
            continue
        nome = (
            f"{identificacao.get('NomeParlamentar', '')} "
            f"{identificacao.get('NomeCompletoParlamentar', '')}"
        ).casefold()
        if termo and termo not in nome:
            continue
        correspondentes.append((parlamentar, identificacao))
    if not correspondentes:
        return "Nenhum senador encontrado para os filtros informados."
    linhas = [f"{len(correspondentes)} senadores:"]
    for _, i in correspondentes[:40]:
        linhas.append(
            f"{i.get('CodigoParlamentar')} — {i.get('NomeParlamentar')} "
            f"({i.get('SiglaPartidoParlamentar', '?')}/{i.get('UfParlamentar', '?')})"
        )
    if len(correspondentes) > 40:
        linhas.append(f"... (+{len(correspondentes) - 40} senadores omitidos)")
    return "\n".join(linhas)


async def senado_materias(
    sigla: str = "PL",
    ano: Annotated[int | None, Field(ge=ANO_MINIMO)] = None,
    palavras_chave: str | None = None,
) -> str:
    """Pesquisa matérias legislativas do Senado (projetos, PECs, requerimentos).

    Args:
        sigla: Tipo da matéria, ex.: "PL", "PEC", "MPV", "REQ".
        ano: Ano de apresentação. Padrão: ano corrente.
        palavras_chave: Palavras-chave filtradas na ementa localmente.
    """
    sigla = validar_sigla_tipo("sigla", sigla)
    ano_referencia = validar_ano("ano", ano) if ano is not None else date.today().year
    termo = (
        validar_texto("palavras_chave", palavras_chave).casefold() if palavras_chave else ""
    )
    dados: dict[str, Any] = await get_json(
        f"{_SENADO_URL}/materia/pesquisa/lista.json",
        params={"sigla": sigla, "ano": ano_referencia},
    )
    materias = _lista_ou_unica(
        dados.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia")
    )
    if termo:
        materias = [m for m in materias if termo in str(m.get("Ementa", "")).casefold()]
    if not materias:
        return "Nenhuma matéria encontrada para os filtros informados."
    linhas = [f"{len(materias)} matérias {sigla} de {ano_referencia}:"]
    for m in materias[:20]:
        linhas.append(
            f"{m.get('Codigo')} — {m.get('Sigla')} "
            f"{str(m.get('Numero', '')).lstrip('0')}/{m.get('Ano')} — {_truncar(m.get('Ementa'))}"
        )
    if len(materias) > 20:
        linhas.append(f"... (+{len(materias) - 20} matérias omitidas)")
    return "\n".join(linhas)


def _placar_votos(votos: dict[str, Any]) -> str:
    individuais = _lista_ou_unica(votos.get("VotoParlamentar"))
    contagem = Counter(str(v.get("SiglaVoto") or "?").strip() for v in individuais)
    ordenadas = sorted(
        contagem,
        key=lambda s: (
            _ORDEM_VOTO.index(s) if s in _ORDEM_VOTO else len(_ORDEM_VOTO),
            s,
        ),
    )
    partes = [
        f"{_SIGLAS_VOTO.get(sigla, sigla.lower())}: {contagem[sigla]}"
        for sigla in ordenadas
    ]
    return " | ".join(partes) if partes else "sem votos registrados"


async def senado_votacoes(codigo_materia: Annotated[int, Field(ge=1)]) -> str:
    """Lista as votações realizadas no plenário do Senado para uma matéria.

    Args:
        codigo_materia: Código numérico da matéria (obtido via senado_materias).
    """
    codigo_materia = validar_id("codigo_materia", codigo_materia)
    dados: dict[str, Any] = await get_json(
        f"{_SENADO_URL}/materia/votacoes/{codigo_materia}.json"
    )
    materia = dados.get("VotacaoMateria", {}).get("Materia") or {}
    votacoes = _lista_ou_unica(materia.get("Votacoes", {}).get("Votacao"))
    if not votacoes:
        return f"Nenhuma votação registrada para a matéria {codigo_materia}."
    linhas = [f"{len(votacoes)} votações da matéria {codigo_materia}:"]
    for vo in votacoes[:10]:
        sessao = vo.get("SessaoPlenaria") or {}
        quando = str(sessao.get("DataSessao", "?"))
        resultado = vo.get("DescricaoResultado") or "sem resultado"
        linhas.append(
            f"{quando} — {_placar_votos(vo.get('Votos') or {})} — "
            f"resultado: {resultado}"
        )
        descricao = _truncar(vo.get("DescricaoVotacao"), 120)
        if descricao:
            linhas.append(f"  {descricao}")
    return "\n".join(linhas)
