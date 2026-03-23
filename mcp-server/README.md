# MCP Server para Core Framework (independente)

## Objetivo

Serviço independente para responder queries baseadas na documentação Markdown de `../docs`.

## Estrutura do projeto

/mcp-server
  /src
    server.ts
    indexer.ts
    query.ts
  package.json
  tsconfig.json
  .gitignore
  README.md

## Instalação

```bash
cd /home/workstation/Projetos/core-framework/mcp-server
npm install
```

## Gerar índice

```bash
npm run index-docs
```

Isso cria `data/index.json` (cache para consultas rápidas).

## Executar local

```bash
npm run dev
```

No ambiente de produção:

```bash
npm run build
npm start
```

A API expõe:

- `GET /status` → status e contagem de chunks
- `POST /query` → pergunta de texto
  - body: `{ "question": "Seu texto" }`
  - response:
    - `answers`: lista ordenada de matches (sources, score, snippet)

## Deploy (example Vercel)

1. Criar projeto Vercel apontando para `mcp-server`.
2. Adicionar `vercel.json` no root se necessário:

```json
{
  "version": 2,
  "builds": [
    {
      "src": "mcp-server/src/server.ts",
      "use": "@vercel/node"
    }
  ],
  "routes": [
    {"src": "/(.*)", "dest": "/mcp-server/src/server.ts"}
  ]
}
```

3. Configure `NPM Build Command` para:

- `cd mcp-server && npm install && npm run build && npm run index-docs`
- `NPM Start Command`: `cd mcp-server && npm start`

### Observações

- A indexação é feita a partir de `../docs` (pasta do framework), não do runtime principal.
- Não há lógica hardcoded em `/query`; usa TF-IDF/semântica textual.
- API e docs são separados, alinhado com o requisito.
