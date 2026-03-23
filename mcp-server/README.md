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

## Deploy no Railway

### 1. Criar projeto

- Acesse https://railway.app
- New Project -> Deploy from GitHub repo

### 2. Root Directory

- Se seu repo contém o MCP em subpasta, informe:

```
Root Directory: mcp-server
```

### 3. Build & Start Variables

- Build command:

```
npm install && npm run build && npm run index-docs
```

- Start command:

```
npm start
```

- Environment variables:

```
NODE_ENV=production
```

(se usar embeddings, adicione `OPENAI_API_KEY` etc.)

### 4. Docker (opcional)

- Railway suporta Dockerfile no diretório raiz (`mcp-server/Dockerfile`).
- Ao deploy, Railway detecta automaticamente.

### 5. Teste

```
curl https://<YOUR_APP>.up.railway.app/status
curl -X POST https://<YOUR_APP>.up.railway.app/query -H 'Content-Type: application/json' -d '{"question":"como funciona?"}'
```

### Observações

- A indexação lê também `../strider/**/*.py` e `../docs/**/*.md`.
- `/query` usa TF-IDF + cosine sem hardcoded.
