from datetime import date, timedelta
from typing import Annotated, Any

from mcp.types import CallToolResult
from pydantic import BaseModel, Field

from mcp_dados_br.http import get_json
from mcp_dados_br.payload import campo, lendo, lista, objeto, texto
from mcp_dados_br.saida import resultado
from mcp_dados_br.validacao import (
    ANO_MINIMO,
    validar_ano,
    validar_id,
    validar_inteiro,
    validar_partido,
    validar_sigla_tipo,
    validar_texto,
    validar_uf,
)

_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
_FONTE = "Câmara dos Deputados"

_TRUNCAR = 140
_AGENDA_DIAS_MAX = 14
_TRAMITACAO_MAX = 100
_LEGISLATURA_MAX = 99

_Id = Annotated[int, Field(ge=1)]


class Deputado(BaseModel):
    id: int
    nome: str
    partido: str
    uf: str
    url_foto: str | None = None


class ListaDeputados(BaseModel):
    """Até 20 deputados que atendem aos filtros."""

    deputados: list[Deputado]


def _registros(resposta: Any, contexto: str) -> list[dict[str, Any]]:
    """Lista `dados` da resposta paginada da API da Câmara, cada item um objeto."""
    itens = lista(objeto(resposta, _FONTE).get("dados"), _FONTE, "dados")
    return [objeto(item, _FONTE, contexto) for item in itens]


def _truncar(valor: Any, limite: int = _TRUNCAR) -> str:
    if not valor:
        return ""
    conteudo = str(valor)
    if len(conteudo) <= limite:
        return conteudo
    return f"{conteudo[:limite]}..."


async def camara_deputados(
    uf: str | None = None,
    partido: str | None = None,
    nome: str | None = None,
    legislatura: Annotated[int | None, Field(ge=1, le=_LEGISLATURA_MAX)] = None,
) -> Annotated[CallToolResult, ListaDeputados]:
    """Lista deputados federais da Câmara com filtros opcionais.

    Além do texto, devolve os deputados em structuredContent (id, nome, partido, UF).

    Args:
        uf: Sigla da unidade federativa, ex.: "SP", "MG".
        partido: Sigla do partido, ex.: "PT", "PSDB".
        nome: Nome (total ou parcial) do parlamentar, com pelo menos 3 letras.
        legislatura: Número da legislatura (ex.: 57 para a atual). Padrão: atual.
    """
    if legislatura is not None:
        validar_inteiro("legislatura", legislatura, 1, _LEGISLATURA_MAX)
    dados = await get_json(
        f"{_BASE_URL}/deputados",
        params={
            "siglaUf": validar_uf(uf) if uf else None,
            "siglaPartido": validar_partido(partido) if partido else None,
            "nome": validar_texto("nome", nome, minimo=3, maximo=100) if nome else None,
            "idLegislatura": legislatura,
            "itens": 20,
        },
    )
    with lendo(_FONTE):
        estruturado = ListaDeputados(
            deputados=[
                Deputado(
                    id=campo(d, "id", _FONTE),
                    nome=texto(d, "nome", _FONTE),
                    partido=str(d.get("siglaPartido") or ""),
                    uf=str(d.get("siglaUf") or ""),
                    url_foto=d.get("urlFoto"),
                )
                for d in _registros(dados, "deputado")
            ]
        )
    deputados = estruturado.deputados
    if not deputados:
        return resultado("Nenhum deputado encontrado para os filtros informados.", estruturado)
    linhas = [f"{d.id} — {d.nome} ({d.partido or '?'}/{d.uf or '?'})" for d in deputados]
    return resultado("\n".join(linhas), estruturado)


async def camara_detalhes_deputado(id_deputado: _Id) -> str:
    """Detalhes de um deputado federal pelo ID: nome civil, partido, UF e gabinete.

    Args:
        id_deputado: ID numérico do deputado (obtido via camara_deputados).
    """
    id_deputado = validar_id("id_deputado", id_deputado)
    dados = await get_json(f"{_BASE_URL}/deputados/{id_deputado}")
    conteudo = objeto(objeto(dados, _FONTE).get("dados") or {}, _FONTE, "dados")
    ultimo = objeto(conteudo.get("ultimoStatus") or {}, _FONTE, "ultimoStatus")
    if not ultimo:
        return f"Nenhum deputado encontrado com o ID {id_deputado}."
    gabinete = objeto(ultimo.get("gabinete") or {}, _FONTE, "gabinete")
    linhas = [
        f"Nome eleitoral: {ultimo.get('nomeEleitoral')}",
        f"Nome civil: {conteudo.get('nomeCivil')}",
        f"Situação: {ultimo.get('situacao')}",
        f"Partido/UF: {ultimo.get('siglaPartido')}/{ultimo.get('siglaUf')}",
        f"E-mail: {ultimo.get('email') or 'não informado'}",
        (
            f"Gabinete: {gabinete.get('predio', '?')}, sala {gabinete.get('sala', '?')}, "
            f"andar {gabinete.get('andar', '?')}, tel. {gabinete.get('telefone', '?')}"
        ),
        f"Foto: {ultimo.get('urlFoto')}",
    ]
    return "\n".join(linhas)


async def camara_proposicoes(
    ano: Annotated[int | None, Field(ge=ANO_MINIMO)] = None,
    palavras_chave: str | None = None,
    sigla_tipo: str | None = None,
) -> str:
    """Busca proposições legislativas na Câmara (projetos de lei, emendas etc.).

    Args:
        ano: Ano de apresentação, ex.: 2025.
        palavras_chave: Palavras-chave na ementa, ex.: "saude mental".
        sigla_tipo: Sigla do tipo, ex.: "PL", "PEC", "MPV".
    """
    dados = await get_json(
        f"{_BASE_URL}/proposicoes",
        params={
            "ano": validar_ano("ano", ano) if ano is not None else None,
            "keywords": (
                validar_texto("palavras_chave", palavras_chave) if palavras_chave else None
            ),
            "siglaTipo": validar_sigla_tipo("sigla_tipo", sigla_tipo) if sigla_tipo else None,
            "itens": 10,
        },
    )
    proposicoes = _registros(dados, "proposição")
    if not proposicoes:
        return "Nenhuma proposição encontrada para os filtros informados."
    linhas = [
        f"{texto(p, 'id', _FONTE)} — {texto(p, 'siglaTipo', _FONTE)} "
        f"{texto(p, 'numero', _FONTE)}/{texto(p, 'ano', _FONTE)} — "
        f"{_truncar(p.get('ementa'))}"
        for p in proposicoes
    ]
    return "\n".join(linhas)


async def camara_votacoes_proposicao(id_proposicao: _Id) -> str:
    """Lista as votações realizadas para uma proposição específica da Câmara.

    Args:
        id_proposicao: ID numérico da proposição (obtido via camara_proposicoes).
    """
    id_proposicao = validar_id("id_proposicao", id_proposicao)
    dados = await get_json(
        f"{_BASE_URL}/votacoes",
        params={"idProposicao": id_proposicao, "itens": 15},
    )
    votacoes = _registros(dados, "votação")
    if not votacoes:
        return f"Nenhuma votação encontrada para a proposição {id_proposicao}."
    linhas = [
        f"{texto(v, 'id', _FONTE)} — {v.get('data', '?')} — "
        f"{_truncar(v.get('descricao') or v.get('aprovacao') or 'sem descrição')}"
        for v in votacoes
    ]
    return "\n".join(linhas)


async def camara_agenda(dias: Annotated[int, Field(ge=1, le=_AGENDA_DIAS_MAX)] = 3) -> str:
    """Agenda de eventos da Câmara dos Deputados (sessões, audiências públicas).

    Args:
        dias: Quantidade de dias a partir de hoje (padrão 3, de 1 a 14).
    """
    dias = validar_inteiro("dias", dias, 1, _AGENDA_DIAS_MAX)
    hoje = date.today()
    fim = hoje + timedelta(days=dias)
    dados = await get_json(
        f"{_BASE_URL}/eventos",
        params={
            "dataInicio": hoje.isoformat(),
            "dataFim": fim.isoformat(),
            "itens": 30,
        },
    )
    eventos = _registros(dados, "evento")
    if not eventos:
        return "Nenhum evento agendado na Câmara para os próximos dias."
    linhas = [f"Agenda da Câmara ({hoje} a {fim}):"]
    for e in eventos:
        inicio = str(e.get("dataHoraInicio", "?")).replace("T", " ")
        situacao = e.get("situacao")
        situacao_txt = f" [{situacao}]" if situacao else ""
        linhas.append(
            f"{inicio} — {_truncar(e.get('descricao'), 100)}{situacao_txt} "
            f"(id {texto(e, 'id', _FONTE)})"
        )
    return "\n".join(linhas)


async def camara_tramitacao(
    id_proposicao: _Id,
    ultimas: Annotated[int, Field(ge=1, le=_TRAMITACAO_MAX)] = 10,
) -> str:
    """Histórico de tramitação de uma proposição na Câmara.

    Args:
        id_proposicao: ID numérico da proposição (obtido via camara_proposicoes).
        ultimas: Quantidade de movimentações recentes a exibir (padrão 10, de 1 a 100).
    """
    id_proposicao = validar_id("id_proposicao", id_proposicao)
    ultimas = validar_inteiro("ultimas", ultimas, 1, _TRAMITACAO_MAX)
    dados = await get_json(
        f"{_BASE_URL}/proposicoes/{id_proposicao}/tramitacoes",
        params={"itens": max(ultimas * 2, 20)},
    )
    tramitacoes = _registros(dados, "tramitação")
    if not tramitacoes:
        return f"Nenhuma tramitação encontrada para a proposição {id_proposicao}."
    recentes = tramitacoes[-ultimas:]
    linhas = [f"Tramitação da proposição {id_proposicao} ({len(tramitacoes)} movimentações):"]
    for t in recentes:
        quando = str(t.get("dataHora", "?")).replace("T", " ")[:16]
        orgao = t.get("siglaOrgao") or "?"
        descricao = t.get("descricaoTramitacao") or t.get("texto") or "sem descrição"
        situacao = t.get("descricaoSituacao")
        situacao_txt = f" [{situacao}]" if situacao else ""
        linhas.append(f"{quando} — {orgao}: {_truncar(descricao, 100)}{situacao_txt}")
    return "\n".join(linhas)
