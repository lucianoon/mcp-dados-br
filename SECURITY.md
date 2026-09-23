# Política de segurança

## Versões suportadas

A versão publicada no PyPI e o branch `main` recebem correções de segurança.
Versões anteriores não recebem backports garantidos.

## Reportar uma vulnerabilidade

Não abra uma issue pública. Use **Security → Report a vulnerability** neste
repositório para enviar o relato de forma privada.

Inclua a versão afetada, o impacto, os passos mínimos para reprodução e, se
possível, uma mitigação. O objetivo é confirmar o recebimento em até 3 dias
úteis e publicar uma avaliação inicial em até 7 dias úteis.

## Escopo sensível

Este servidor MCP consulta APIs públicas e devolve texto para um modelo de
linguagem. São especialmente relevantes relatos sobre:

- vazamento do `INMET_TOKEN` em logs, mensagens de erro ou respostas;
- injeção de conteúdo vindo das APIs upstream que possa manipular o modelo
  cliente (prompt injection via dados);
- consumo excessivo de recursos por parâmetros adversariais (por exemplo,
  intervalos de datas ou paginação sem limite);
- exposição indevida do transporte `streamable-http` quando publicado em rede
  (sem `MCP_AUTH_TOKEN` ele não tem autenticação; veja o README) ou falhas na
  verificação do token bearer.

Não inclua tokens reais nem dados pessoais no relato.
