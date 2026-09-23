import httpx
import respx

from mcp_dados_br.saida import texto_de
from mcp_dados_br.tools import camara

BASE = "https://dadosabertos.camara.leg.br/api/v2"


@respx.mock
async def test_camara_deputados_formata_saida() -> None:
    respx.get(f"{BASE}/deputados").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": [
                    {
                        "id": 221328,
                        "nome": "Adilson Barroso",
                        "siglaPartido": "PL",
                        "siglaUf": "SP",
                    }
                ]
            },
        )
    )
    saida = texto_de(await camara.camara_deputados(uf="sp"))
    requisicao_url = str(respx.calls.last.request.url)
    assert "siglaUf=SP" in requisicao_url
    assert saida == "221328 — Adilson Barroso (PL/SP)"


@respx.mock
async def test_camara_deputados_sem_resultado() -> None:
    respx.get(f"{BASE}/deputados").mock(return_value=httpx.Response(200, json={"dados": []}))
    saida = texto_de(await camara.camara_deputados(nome="inexistente"))
    assert saida == "Nenhum deputado encontrado para os filtros informados."


@respx.mock
async def test_camara_detalhes_deputado() -> None:
    respx.get(f"{BASE}/deputados/221328").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": {
                    "nomeCivil": "ADILSON BARROSO OLIVEIRA",
                    "ultimoStatus": {
                        "nomeEleitoral": "Adilson Barroso",
                        "situacao": "Exercício",
                        "siglaPartido": "PL",
                        "siglaUf": "SP",
                        "email": None,
                        "urlFoto": "https://foto.test/221328.jpg",
                        "gabinete": {
                            "predio": "4", "sala": "603", "andar": "6", "telefone": "3215-5603",
                        },
                    },
                }
            },
        )
    )
    saida = await camara.camara_detalhes_deputado(221328)
    assert "Nome civil: ADILSON BARROSO OLIVEIRA" in saida
    assert "E-mail: não informado" in saida
    assert "sala 603" in saida


@respx.mock
async def test_camara_proposicoes_trunca_ementa() -> None:
    ementa_longa = "x" * 300
    respx.get(f"{BASE}/proposicoes").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": [
                    {
                        "id": 2482470,
                        "siglaTipo": "PL",
                        "numero": 130,
                        "ano": 2025,
                        "ementa": ementa_longa,
                    }
                ]
            },
        )
    )
    saida = await camara.camara_proposicoes(ano=2025, palavras_chave="saude")
    assert saida.startswith("2482470 — PL 130/2025 — ")
    assert saida.endswith("...")
    assert len(saida) < 200


@respx.mock
async def test_camara_votacoes_com_resultados() -> None:
    respx.get(f"{BASE}/votacoes").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": [
                    {
                        "id": "2642749-7",
                        "data": "2026-08-13",
                        "aprovacao": 1,
                        "descricao": "Aprovado por unanimidade.",
                    }
                ]
            },
        )
    )
    saida = await camara.camara_votacoes_proposicao(2642749)
    assert "2642749-7 — 2026-08-13 — Aprovado por unanimidade." in saida


@respx.mock
async def test_camara_votacoes_sem_resultados() -> None:
    respx.get(f"{BASE}/votacoes").mock(return_value=httpx.Response(200, json={"dados": []}))
    saida = await camara.camara_votacoes_proposicao(999)
    assert saida == "Nenhuma votação encontrada para a proposição 999."


@respx.mock
async def test_camara_agenda_formata_eventos() -> None:
    respx.get(f"{BASE}/eventos").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": [
                    {
                        "id": 82911,
                        "dataHoraInicio": "2026-08-25T14:00",
                        "descricao": "Audiência pública sobre universidades",
                        "situacao": "Convocada",
                    }
                ]
            },
        )
    )
    saida = await camara.camara_agenda(dias=3)
    assert "Agenda da Câmara (" in saida
    assert "2026-08-25 14:00 — Audiência pública sobre universidades [Convocada]" in saida
    assert "(id 82911)" in saida


@respx.mock
async def test_camara_agenda_vazia() -> None:
    respx.get(f"{BASE}/eventos").mock(return_value=httpx.Response(200, json={"dados": []}))
    saida = await camara.camara_agenda()
    assert saida == "Nenhum evento agendado na Câmara para os próximos dias."


@respx.mock
async def test_camara_tramitacao_exibe_ultimas_movimentacoes() -> None:
    respx.get(f"{BASE}/proposicoes/2482470/tramitacoes").mock(
        return_value=httpx.Response(
            200,
            json={
                "dados": [
                    {
                        "dataHora": "2025-02-03T15:58",
                        "siglaOrgao": "MESA",
                        "descricaoTramitacao": "Apresentação de Proposição",
                        "descricaoSituacao": "Pronta para Pauta",
                    },
                ]
            },
        )
    )
    saida = await camara.camara_tramitacao(2482470)
    assert "Tramitação da proposição 2482470" in saida
    assert "2025-02-03 15:58 — MESA: Apresentação de Proposição [Pronta para Pauta]" in saida


@respx.mock
async def test_camara_tramitacao_vazia() -> None:
    respx.get(f"{BASE}/proposicoes/1/tramitacoes").mock(
        return_value=httpx.Response(200, json={"dados": []})
    )
    saida = await camara.camara_tramitacao(1)
    assert saida == "Nenhuma tramitação encontrada para a proposição 1."
