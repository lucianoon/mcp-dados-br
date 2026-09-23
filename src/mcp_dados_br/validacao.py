"""Validação dos argumentos das tools antes de montar qualquer URL.

Os valores chegam de um modelo de linguagem e são interpolados em caminhos e
filtros OData das APIs públicas. Cada função normaliza o valor aceito e, se
ele for inválido, levanta `EntradaInvalida` com uma mensagem que diz o que foi
recebido e o que é aceito. Como a exceção herda de `ToolError`, o SDK MCP
devolve essa mensagem ao cliente (`isError: true`) em vez do genérico
"Error executing tool".
"""

import re
from datetime import date

from mcp.server.mcpserver.exceptions import ToolError

UF_CODIGOS: dict[str, str] = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15",
    "AP": "16", "TO": "17", "MA": "21", "PI": "22", "CE": "23",
    "RN": "24", "PB": "25", "PE": "26", "AL": "27", "SE": "28",
    "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35",
    "PR": "41", "SC": "42", "RS": "43", "MS": "50", "MT": "51",
    "GO": "52", "DF": "53",
}

ANO_MINIMO = 1900

_MOEDA = re.compile(r"[A-Z]{3}")
_SIGLA_TIPO = re.compile(r"[A-Z]{1,10}")
# Siglas de partido podem ter acento (UNIÃO) e dígitos, mas nunca pontuação.
_PARTIDO = re.compile(r"[^\W_]{1,20}")


class EntradaInvalida(ToolError, ValueError):
    """Argumento de tool fora do formato ou do intervalo aceito."""


def validar_uf(uf: str, *, permitir_br: bool = False) -> str:
    sigla = uf.strip().upper()
    if sigla in UF_CODIGOS or (permitir_br and sigla == "BR"):
        return sigla
    extra = ' ou "BR" para o Brasil' if permitir_br else ""
    validas = ", ".join(sorted(UF_CODIGOS))
    raise EntradaInvalida(f"UF desconhecida: {uf!r}. Use uma das 27 siglas{extra}: {validas}")


def codigo_uf(uf: str) -> str:
    return UF_CODIGOS[validar_uf(uf)]


def validar_inteiro(nome: str, valor: int, minimo: int, maximo: int | None = None) -> int:
    # bool é subclasse de int; True como "dias" é quase certamente um engano.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise EntradaInvalida(f"{nome} deve ser um número inteiro, recebido {valor!r}.")
    if valor < minimo or (maximo is not None and valor > maximo):
        faixa = f"entre {minimo} e {maximo}" if maximo is not None else f"maior ou igual a {minimo}"
        raise EntradaInvalida(f"{nome} deve estar {faixa}, recebido {valor}.")
    return valor


def validar_id(nome: str, valor: int) -> int:
    return validar_inteiro(nome, valor, 1)


def validar_ano(nome: str, valor: int) -> int:
    return validar_inteiro(nome, valor, ANO_MINIMO, date.today().year + 1)


def validar_data(nome: str, valor: str) -> date:
    texto = valor.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", texto):
        raise EntradaInvalida(
            f"{nome} deve estar no formato ISO AAAA-MM-DD (ex.: 2026-01-31), recebido {valor!r}."
        )
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise EntradaInvalida(f"{nome} não é uma data válida: {valor!r}.") from None


def validar_moeda(moeda: str) -> str:
    codigo = moeda.strip().upper()
    if not _MOEDA.fullmatch(codigo):
        raise EntradaInvalida(
            f"Moeda inválida: {moeda!r}. Informe o código ISO 4217 de 3 letras "
            '(ex.: "USD", "EUR"); a tool bcb_moedas lista as disponíveis.'
        )
    return codigo


def validar_sigla_tipo(nome: str, sigla: str) -> str:
    valor = sigla.strip().upper()
    if not _SIGLA_TIPO.fullmatch(valor):
        raise EntradaInvalida(
            f"{nome} inválida: {sigla!r}. Use só letras, até 10 (ex.: PL, PEC, MPV)."
        )
    return valor


def validar_partido(partido: str) -> str:
    valor = partido.strip().upper()
    if not _PARTIDO.fullmatch(valor):
        raise EntradaInvalida(
            f"Sigla de partido inválida: {partido!r}. Use letras e dígitos, até 20 (ex.: PT, PSDB)."
        )
    return valor


def validar_texto(nome: str, valor: str, *, minimo: int = 1, maximo: int = 200) -> str:
    texto = valor.strip()
    if not minimo <= len(texto) <= maximo:
        raise EntradaInvalida(
            f"{nome} deve ter entre {minimo} e {maximo} caracteres, recebido {len(texto)}."
        )
    return texto


def validar_padrao(nome: str, valor: str, padrao: re.Pattern[str], exemplo: str) -> str:
    texto = valor.strip()
    if not padrao.fullmatch(texto):
        raise EntradaInvalida(f"{nome} em formato inválido: {valor!r}. Exemplo: {exemplo}.")
    return texto
