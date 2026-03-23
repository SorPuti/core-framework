import { createIndex, IndexData, loadIndex } from "./indexer";
import { buildAnswerPayload } from "./query";
import { createServer } from "http";

type JsonRpcId = string | number | null;

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id?: JsonRpcId;
  method: string;
  params?: unknown;
}

interface JsonRpcError {
  code: number;
  message: string;
}

interface ToolCallArgs {
  question?: string;
  topK?: number;
}

let indexData: IndexData | null = null;
let inputBuffer = Buffer.alloc(0);

async function initializeIndex(): Promise<void> {
  try {
    indexData = await loadIndex();
  } catch {
    indexData = await createIndex();
  }
  console.error(`MCP stdio index loaded: ${indexData.chunks.length} chunks`);
}

function writeMessage(payload: unknown): void {
  const body = Buffer.from(JSON.stringify(payload), "utf8");
  const header = Buffer.from(`Content-Length: ${body.length}\r\n\r\n`, "utf8");
  process.stdout.write(Buffer.concat([header, body]));
}

function rpcResult(id: JsonRpcId, result: unknown): unknown {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(id: JsonRpcId, error: JsonRpcError): unknown {
  return { jsonrpc: "2.0", id, error };
}

function parseMessages(chunk: Buffer): JsonRpcRequest[] {
  inputBuffer = Buffer.concat([inputBuffer, chunk]);
  const messages: JsonRpcRequest[] = [];

  while (true) {
    const headerEnd = inputBuffer.indexOf("\r\n\r\n");
    if (headerEnd === -1) break;

    const headerRaw = inputBuffer.slice(0, headerEnd).toString("utf8");
    const contentLengthMatch = headerRaw.match(/Content-Length:\s*(\d+)/i);
    if (!contentLengthMatch) {
      inputBuffer = inputBuffer.slice(headerEnd + 4);
      continue;
    }

    const contentLength = Number(contentLengthMatch[1]);
    const totalLength = headerEnd + 4 + contentLength;
    if (inputBuffer.length < totalLength) break;

    const body = inputBuffer.slice(headerEnd + 4, totalLength).toString("utf8");
    inputBuffer = inputBuffer.slice(totalLength);

    try {
      const parsed = JSON.parse(body) as JsonRpcRequest;
      messages.push(parsed);
    } catch {
      // Ignore malformed JSON and continue reading next frames.
    }
  }

  return messages;
}

function toolsListResult() {
  return {
    tools: [
      {
        name: "search_framework",
        description: "Busca semantica no core-framework com retorno de docs e referencias de codigo.",
        inputSchema: {
          type: "object",
          properties: {
            question: { type: "string", description: "Pergunta em linguagem natural sobre o framework." },
            topK: { type: "integer", minimum: 1, maximum: 10, description: "Quantidade de respostas (padrao 5)." },
          },
          required: ["question"],
        },
      },
      {
        name: "status",
        description: "Retorna status do indice (docs/code chunks).",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ],
  };
}

function statusResult() {
  const total = indexData?.chunks.length ?? 0;
  const docsChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("docs/")).length ?? 0;
  const codeChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("code/")).length ?? 0;

  return {
    content: [
      {
        type: "text",
        text: JSON.stringify(
          {
            status: "ready",
            indexed_chunks: total,
            docs_chunks: docsChunks,
            code_chunks: codeChunks,
          },
          null,
          2
        ),
      },
    ],
  };
}

function callToolResult(params: unknown) {
  const p = (params ?? {}) as {
    name?: string;
    arguments?: ToolCallArgs;
  };

  if (p.name === "status") {
    return statusResult();
  }

  if (p.name === "search_framework") {
    const question = (p.arguments?.question ?? "").toString().trim();
    const topK = Number(p.arguments?.topK ?? 5);

    if (!question) {
      return {
        isError: true,
        content: [{ type: "text", text: "question e obrigatoria" }],
      };
    }

    if (!indexData) {
      return {
        isError: true,
        content: [{ type: "text", text: "Indice nao inicializado" }],
      };
    }

    const payload = buildAnswerPayload(indexData, question, topK);

    return {
      content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    };
  }

  return {
    isError: true,
    content: [{ type: "text", text: `Tool desconhecida: ${p.name ?? ""}` }],
  };
}

function handleRequest(req: JsonRpcRequest): unknown | null {
  const id = req.id ?? null;

  if (req.jsonrpc !== "2.0" || !req.method) {
    if (req.id !== undefined) {
      return rpcError(id, { code: -32600, message: "Invalid Request" });
    }
    return null;
  }

  if (req.method === "initialize") {
    return rpcResult(id, {
      protocolVersion: "2024-11-05",
      capabilities: {
        tools: {},
      },
      serverInfo: {
        name: "core-framework-mcp",
        version: "0.1.0",
      },
    });
  }

  if (req.method === "notifications/initialized") {
    return null;
  }

  if (req.method === "tools/list") {
    return rpcResult(id, toolsListResult());
  }

  if (req.method === "tools/call") {
    return rpcResult(id, callToolResult(req.params));
  }

  if (req.id !== undefined) {
    return rpcError(id, { code: -32601, message: `Method not found: ${req.method}` });
  }

  return null;
}

function runStdio(): void {
  console.error("Core Framework MCP server running via stdio");

  process.stdin.on("data", (chunk: Buffer) => {
    for (const req of parseMessages(chunk)) {
      const response = handleRequest(req);
      if (response) {
        writeMessage(response);
      }
    }
  });
}

function runHttp(port: number): void {
  const server = createServer((req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "content-type, accept");
    res.setHeader("Access-Control-Allow-Methods", "POST, GET, OPTIONS");

    if (req.method === "OPTIONS") {
      res.statusCode = 204;
      res.end();
      return;
    }

    if (req.method === "GET" && req.url === "/status") {
      const total = indexData?.chunks.length ?? 0;
      const docsChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("docs/")).length ?? 0;
      const codeChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("code/")).length ?? 0;
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(
        JSON.stringify({
          status: "ready",
          indexed_chunks: total,
          docs_chunks: docsChunks,
          code_chunks: codeChunks,
          transport: "mcp-http",
        })
      );
      return;
    }

    if (req.method !== "POST" || req.url !== "/mcp") {
      res.statusCode = 404;
      res.end("Not found");
      return;
    }

    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    req.on("end", () => {
      let payload: unknown;
      try {
        payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      } catch {
        res.statusCode = 400;
        res.setHeader("Content-Type", "application/json; charset=utf-8");
        res.end(JSON.stringify(rpcError(null, { code: -32700, message: "Parse error" })));
        return;
      }

      const requests = Array.isArray(payload) ? payload : [payload];
      const responses: unknown[] = [];

      for (const item of requests) {
        const response = handleRequest(item as JsonRpcRequest);
        if (response) {
          responses.push(response);
        }
      }

      if (responses.length === 0) {
        res.statusCode = 202;
        res.end();
        return;
      }

      res.statusCode = 200;
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(JSON.stringify(Array.isArray(payload) ? responses : responses[0]));
    });
  });

  server.listen(port, () => {
    console.error(`Core Framework MCP server running on http://0.0.0.0:${port}/mcp`);
  });
}

async function main(): Promise<void> {
  await initializeIndex();
  const args = process.argv.slice(2);
  const forceHttp = args.includes("--http");
  const forceStdio = args.includes("--stdio");
  const portArg = args.find((arg) => arg.startsWith("--port="));
  const argPort = portArg ? Number(portArg.split("=")[1]) : 0;
  const transport = (process.env.MCP_TRANSPORT || "stdio").toLowerCase();
  const port = argPort || Number(process.env.PORT || 0);

  if (forceStdio) {
    runStdio();
    return;
  }

  if (forceHttp) {
    runHttp(port || 8080);
    return;
  }

  if (transport === "stdio") {
    runStdio();
    return;
  }

  if (transport === "http" || port > 0) {
    runHttp(port || 8080);
    return;
  }

  runStdio();
}

main().catch((err) => {
  console.error("Failed to start MCP stdio server:", err);
  process.exit(1);
});
