# Core Framework MCP Server

Servidor MCP (Model Context Protocol) via stdio para busca semantica em:

- `docs/**/*.md`
- `strider/**/*.py`

Sem API REST. Este projeto e MCP puro para integrar com VS Code Copilot e Cursor.

## Requisitos

- Node.js 20+
- npm

## Instalar e buildar

```bash
cd /home/workstation/Projetos/core-framework/mcp-server
npm install
npm run build
```

## Rodar local (stdio)

```bash
npm start
```

Para forcar modo stdio:

```bash
MCP_TRANSPORT=stdio npm start
```

## Rodar remoto (MCP HTTP)

No Railway, `PORT` e injetada automaticamente. O servidor sobe em:

- `POST /mcp` (JSON-RPC MCP)
- `GET /status` (health/debug)

Para forcar localmente:

```bash
MCP_TRANSPORT=http PORT=8080 npm start
```

Handshake de validacao:

```bash
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0.0"}}}'
```

## Tools MCP expostas

- `search_framework`
: Busca semantica por pergunta em linguagem natural e retorna respostas com referencias de codigo.
- `status`
: Retorna status do indice (`indexed_chunks`, `docs_chunks`, `code_chunks`).

### Core de seguranca e introspeccao

- `introspect_framework`
: Retorna inventario de models, views, permissoes, servicos e recursos operacionais.
- `list_models`
: Lista models disponiveis (com campos e relacionamentos, quando solicitado).
- `describe_model`
: Detalha campos, relacionamentos e regras de uso seguro de um model.
- `list_capabilities`
: Indica o que o sistema suporta (CRUD, workers, runners, tasks, camada de permissao).
- `validate_action`
: Valida uma acao antes da execucao (existencia de recurso e guardrails).
- `generate_safe_query`
: Gera padrao de query usando somente abstrações do framework (`Model.objects.*`).
- `explain_usage`
: Explica o fluxo recomendado para agentes consumidores e boas praticas obrigatorias.

### CLI com execucao local e validacoes

Politica obrigatoria:
- MCP remoto (HTTP): apenas valida e instrui, sem executar comandos.
- Execucao de comandos: somente em MCP local (stdio), no computador do desenvolvedor.

Fluxo operacional obrigatorio para agentes:
1. MCP remoto analisa e recomenda comando.
2. Agente local solicita confirmacao explicita do usuario.
3. Agente local executa no projeto local do cliente.
4. Agente local valida saida e reporta resultado.

- `cli_list_commands`
: Lista comandos operacionais e classifica comandos criticos.
- `cli_execute`
: Executa CLI no projeto local. Para comandos criticos, exige confirmacao explicita:
`confirm=CONFIRMO_EXECUCAO_CRITICA`.
- `cli_registry_health` e `cli_run_tests`
: Tambem exigem `confirm=CONFIRMO_EXECUCAO_CRITICA` para qualquer execucao local.
- `cli_registry_health`
: Roda checks de saude e valida registries de workers/runners/tasks.
- `cli_run_tests`
: Executa testes via CLI local (alvo e cobertura opcionais).

## Configurar no VS Code Copilot Chat

Adicione no `settings.json`:

```json
{
  "mcp": {
    "servers": {
      "core-framework": {
        "command": "node",
        "args": [
          "/home/workstation/Projetos/core-framework/mcp-server/dist/mcp.js"
        ],
        "env": {
          "DOCS_ROOT": "/home/workstation/Projetos/core-framework/docs",
          "STRIDER_ROOT": "/home/workstation/Projetos/core-framework/strider",
          "DATA_DIR": "/home/workstation/Projetos/core-framework/mcp-server/data"
        }
      }
    }
  }
}
```

Depois, recarregue a janela do VS Code.

## Configurar no Cursor

No arquivo de MCP do Cursor (normalmente `.cursor/mcp.json` no projeto), use:

```json
{
  "mcpServers": {
    "core-framework": {
      "command": "node",
      "args": [
        "/home/workstation/Projetos/core-framework/mcp-server/dist/mcp.js"
      ],
      "env": {
        "DOCS_ROOT": "/home/workstation/Projetos/core-framework/docs",
        "STRIDER_ROOT": "/home/workstation/Projetos/core-framework/strider",
        "DATA_DIR": "/home/workstation/Projetos/core-framework/mcp-server/data"
      }
    }
  }
}
```

Reinicie o Cursor apos salvar.

## Notas de operacao

- O indice e carregado no startup.
- Se `data/index.json` nao existir, ele e criado automaticamente.
- Se `docs` e `strider` mudarem, reinicie o processo para reindexar.
