# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e versionamento semântico.

## [Não lançado]

### Planejado

- Busca no Diário Oficial da União (aguardando API pública estável)
- Resultados eleitorais do TSE

## [0.6.0] — ainda não publicada

### Adicionado

- Autenticação bearer opcional no transporte `streamable-http`: com
  `MCP_AUTH_TOKEN` definido, toda requisição precisa de
  `Authorization: Bearer <token>` (comparação com `secrets.compare_digest`);
  sem token o servidor responde `401` com `WWW-Authenticate: Bearer`. Sem a
  variável e escutando fora do loopback, o servidor registra um aviso no log
- Validação de entrada em todas as tools (`validacao.py`): UF entre as 27
  siglas, moeda ISO 4217 de 3 letras, datas ISO `AAAA-MM-DD`, agregado,
  variável, períodos e localidades SIDRA no formato da API, código de estação
  do INMET, siglas de tipo e de partido, IDs positivos, anos e tamanho de
  textos. Nada é interpolado em caminho ou filtro OData sem passar por ela
- Limites de `dias`, `ultimas`, `legislatura` e IDs também publicados no
  `inputSchema` das tools (`minimum`/`maximum`)
- Saída estruturada em `bcb_serie`, `bcb_cambio` e `camara_deputados`:
  `structuredContent` validado por `outputSchema` (datas ISO, valores
  numéricos), com o texto de antes mantido em `content` como fallback
- `SECURITY.md` com política de reporte e escopo sensível
- Dependabot também para as dependências Python (grupo mensal de minor/patch)
- Job de CI que constrói a imagem Docker, sobe o transporte `streamable-http`
  e confirma que o processo atende HTTP sem rodar como root
- README em inglês (`README.en.md`)

### Alterado

- O cliente HTTP repete a chamada em `429`, `502`, `503` e `504`, com o mesmo
  backoff usado para falhas de rede. Antes qualquer 5xx transitório do upstream
  virava erro imediato (foi o caso do 504 da Câmara em 31/08/2026)
- CI sincroniza com `--locked`, falhando se o `uv.lock` estiver desatualizado
- Imagem Docker executa como usuário sem privilégios
- Erros de validação e de API upstream agora chegam ao cliente MCP com a
  mensagem original. Antes o SDK trocava qualquer `ValueError` pelo genérico
  "Error executing tool", e o modelo não sabia o que corrigir
- `dias` fora da faixa em `camara_agenda` (1 a 14), `inmet_dados` (1 a 7) e
  `bcb_cambio` (1 a 30) passa a ser erro explícito, em vez de ajustado em
  silêncio
- `bcb_serie`, `bcb_cambio` e `camara_deputados` devolvem `CallToolResult`
  (texto + dados); quem chama a função direto do Python lê o texto com
  `mcp_dados_br.saida.texto_de`
- Chave do cache serializa URL e parâmetros como JSON ordenado: um valor com
  `&` ou `=` não colide mais com outra combinação de parâmetros
- User-Agent e `mcp_dados_br.__version__` vêm de `importlib.metadata` (estavam
  fixos em `0.1`)
- `starlette` e `uvicorn` declarados como dependências diretas

### Corrigido

- `bcb_cambio` perdia os dias mais recentes: o `$top` do OData (`dias * 2`)
  não cobria os até 5 boletins PTAX por dia útil, e com `dias=7` a "última
  cotação" podia ser de uma semana antes
- Docstring de `ibge_sidra` sugeria `"2020/2024"` para intervalo de períodos,
  o que quebraria o caminho da URL; a sintaxe da API é `2020-2024`
- A imagem Docker escutava só em `127.0.0.1`, então `docker run -p 8000:8000`
  nunca respondia. Novo `MCP_HOST` (padrão `127.0.0.1`; a imagem define
  `0.0.0.0`). Encontrado pelo smoke novo do CI

## [0.5.1] — 2026-08-25

### Adicionado

- `server.json` para o MCP Registry oficial e `smithery.yaml` para a Smithery
- Workflow publica automaticamente no MCP Registry após o deploy no PyPI
- Marcador de verificação de propriedade no README (`mcp-name`)

## [0.5.0] — 2026-08-25

### Adicionado

- Módulo Senado Federal sobre a API LegisSaber:
  `senado_senadores` (81 senadores, filtros por UF e nome),
  `senado_materias` (pesquisa por sigla, ano e palavras-chave) e
  `senado_votacoes` (placar nominal e resultado por sessão)

### Adotado do benchmark DeHor Labs

- Badges de CI/Python/licença no README
- `CHANGELOG.md` (este arquivo)
- Logging opcional em stderr via `MCP_LOG_LEVEL`
- `CONTRIBUTING.md` e templates de issue

## [0.4.0] — 2026-08-25

### Adicionado

- Tool `camara_tramitacao`: histórico de tramitação de uma proposição
- Atalhos nomeados em `bcb_serie`: `selic`, `cdi`, `ipca`, `ipca_12m`,
  `igpm`, `inpc`, `salario_minimo`
- Dockerfile com transporte streamable-http padrão
- Dependabot para GitHub Actions

### Alterado

- Timeout HTTP de 15s para 30s com 3 tentativas (APIs governamentais lentas)

## [0.3.0] — 2026-08-25

### Adicionado

- Tool `camara_agenda`: eventos da Câmara dos próximos dias
- Transporte `streamable-http` configurável via `MCP_TRANSPORTE`
- Job de integração no CI (cron semanal) contra as APIs reais

## [0.2.0] — 2026-08-25

### Adicionado

- Tools `inmet_estacoes` (aberta) e `inmet_dados` (requer token INMET opcional)
- Tool `bcb_focus`: expectativas do Boletim Focus para Selic, IPCA, PIB e câmbio

### Corrigido

- Encoding de queries OData (`%20` em vez de `+`) para o serviço Olinda do BCB

## [0.1.0] — 2026-08-24

### Adicionado

- Servidor MCP inicial com 11 ferramentas: IBGE/SIDRA (população, PIB,
  municípios, consulta genérica), Banco Central (séries SGS, PTAX, moedas)
  e Câmara dos Deputados (deputados, proposições, votações)
- Cache TTL de 10 minutos e retry automático
- CI em Python 3.12 e 3.14 (ruff, mypy strict, pytest)
