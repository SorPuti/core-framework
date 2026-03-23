import fs from "fs";
import path from "path";
import { spawnSync } from "child_process";
import { createServer } from "http";
import { createIndex, IndexData, loadIndex } from "./indexer";
import { buildAnswerPayload } from "./query";

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
  [key: string]: unknown;
  question?: string;
  topK?: number;
  model?: string;
  include_fields?: boolean;
  action?: string;
  resource_type?: string;
  resource_name?: string;
  operation?: string;
  filters?: Record<string, unknown>;
  command?: string;
  args?: string[];
  confirm?: string;
  timeout_ms?: number;
  test_target?: string;
  with_coverage?: boolean;
}

interface ModelMetadata {
  name: string;
  source: string;
  fields: string[];
  relations: string[];
}

interface ClassMetadata {
  name: string;
  source: string;
}

interface FrameworkSnapshot {
  projectRoot: string;
  striderRoot: string;
  models: ModelMetadata[];
  views: ClassMetadata[];
  permissions: ClassMetadata[];
  services: string[];
  workers: string[];
  runners: string[];
  tasks: string[];
}

interface CommandResult {
  ok: boolean;
  command: string;
  args: string[];
  cwd: string;
  exitCode: number;
  stdout: string;
  stderr: string;
  timedOut: boolean;
}

const CRITICAL_CONFIRMATION_TOKEN = "CONFIRMO_EXECUCAO_CRITICA";
const DEFAULT_TIMEOUT_MS = 60_000;

let indexData: IndexData | null = null;
let inputBuffer = Buffer.alloc(0);
let snapshotCache: FrameworkSnapshot | null = null;
let snapshotCacheKey = "";

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

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function asNumber(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function asBoolean(value: unknown, fallback = false): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asString(item)).filter((item) => item.length > 0);
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function textResult(payload: unknown): { content: Array<{ type: "text"; text: string }> } {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
  };
}

function toolError(message: string, details?: unknown): { isError: true; content: Array<{ type: "text"; text: string }> } {
  return textResult({ error: message, details }) as {
    isError: true;
    content: Array<{ type: "text"; text: string }>;
  };
}

function normalizeToken(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
}

function isIgnoredDir(dirName: string): boolean {
  return [
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "site",
    ".pytest_cache",
  ].includes(dirName);
}

function walkPythonFiles(root: string): string[] {
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) return [];

  const result: string[] = [];
  const stack: string[] = [root];

  while (stack.length > 0) {
    const current = stack.pop() as string;
    const entries = fs.readdirSync(current, { withFileTypes: true });

    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (!isIgnoredDir(entry.name)) {
          stack.push(fullPath);
        }
        continue;
      }
      if (entry.isFile() && entry.name.endsWith(".py")) {
        result.push(fullPath);
      }
    }
  }

  return result;
}

function extractClassMetadata(content: string): Array<{ name: string; bases: string; line: number }> {
  const lines = content.split("\n");
  const out: Array<{ name: string; bases: string; line: number }> = [];
  const classRegex = /^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\(([^)]*)\)\s*:/;

  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(classRegex);
    if (!match) continue;
    out.push({
      name: match[1],
      bases: match[2],
      line: i,
    });
  }

  return out;
}

function parseModelsInFile(content: string, source: string): ModelMetadata[] {
  const lines = content.split("\n");
  const classes = extractClassMetadata(content);
  const models: ModelMetadata[] = [];

  for (const cls of classes) {
    if (!cls.bases.includes("Model")) continue;

    const fields: string[] = [];
    const relations: string[] = [];
    const classLine = lines[cls.line] ?? "";
    const classIndent = classLine.length - classLine.trimStart().length;

    for (let i = cls.line + 1; i < lines.length; i++) {
      const line = lines[i];
      if (line.trim().length === 0) continue;
      const indent = line.length - line.trimStart().length;

      if (indent <= classIndent) break;

      const fieldMatch = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_\.]*)\(/);
      if (!fieldMatch) continue;

      const fieldName = fieldMatch[1];
      if (fieldName.toUpperCase() === fieldName) continue;

      fields.push(fieldName);

      const ctor = fieldMatch[2].toLowerCase();
      if (
        ctor.includes("foreign") ||
        ctor.includes("manyto") ||
        ctor.includes("onetone") ||
        ctor.includes("relation")
      ) {
        relations.push(fieldName);
      }
    }

    models.push({
      name: cls.name,
      source,
      fields: Array.from(new Set(fields)),
      relations: Array.from(new Set(relations)),
    });
  }

  return models;
}

function parseNamedClasses(content: string, source: string): { views: ClassMetadata[]; permissions: ClassMetadata[] } {
  const classes = extractClassMetadata(content);
  const views: ClassMetadata[] = [];
  const permissions: ClassMetadata[] = [];

  for (const cls of classes) {
    const baseNorm = normalizeToken(cls.bases);
    const nameNorm = normalizeToken(cls.name);

    const isView =
      nameNorm.endsWith("view") ||
      nameNorm.endsWith("viewset") ||
      baseNorm.includes("view") ||
      baseNorm.includes("viewset");

    const isPermission =
      nameNorm.includes("permission") ||
      baseNorm.includes("permission") ||
      source.includes("permissions");

    if (isView) {
      views.push({ name: cls.name, source });
    }
    if (isPermission) {
      permissions.push({ name: cls.name, source });
    }
  }

  return { views, permissions };
}

function guessServices(striderRoot: string, pyFiles: string[]): string[] {
  const services: string[] = [];

  for (const file of pyFiles) {
    const rel = path.relative(striderRoot, file).replace(/\\/g, "/");
    const normalized = rel.toLowerCase();
    if (normalized.startsWith("services/") || normalized.includes("/services/") || normalized.includes("service")) {
      services.push(rel);
    }
  }

  return Array.from(new Set(services)).sort();
}

function extractNamedFunctionResults(content: string, functionName: string): string[] {
  const regex = new RegExp(`def\\s+${functionName}\\([^)]*\\):[\\s\\S]*?return\\s+([^\\n]+)`);
  const match = content.match(regex);
  if (!match) return [];
  const returned = match[1];
  const literalList = returned.match(/\[([^\]]*)\]/);
  if (!literalList) return [];

  return literalList[1]
    .split(",")
    .map((item) => item.replace(/[\"'\s]/g, "").trim())
    .filter((item) => item.length > 0);
}

function resolveProjectRoot(): string {
  const envRoot = asString(process.env.FRAMEWORK_ROOT);
  const candidates = [
    envRoot,
    process.cwd(),
    path.resolve(__dirname, "..", "..", ".."),
    path.resolve(__dirname, "..", ".."),
    path.resolve(__dirname, ".."),
    "/app",
  ].filter((item) => item.length > 0);

  for (const candidate of candidates) {
    let current = path.resolve(candidate);
    for (let i = 0; i < 6; i++) {
      const hasPyproject = fs.existsSync(path.join(current, "pyproject.toml"));
      const hasStrider = fs.existsSync(path.join(current, "strider"));
      if (hasPyproject && hasStrider) {
        return current;
      }
      const parent = path.dirname(current);
      if (parent === current) break;
      current = parent;
    }
  }

  const fallback = path.resolve(process.cwd());
  return fallback;
}

function resolveStriderRoot(projectRoot: string): string {
  const envStriderRoot = asString(process.env.STRIDER_ROOT);
  if (envStriderRoot.length > 0 && fs.existsSync(envStriderRoot)) {
    return path.resolve(envStriderRoot);
  }

  const direct = path.join(projectRoot, "strider");
  if (fs.existsSync(direct)) return direct;

  const appDirect = path.join("/app", "strider");
  if (fs.existsSync(appDirect)) return appDirect;

  return direct;
}

function buildFrameworkSnapshot(): FrameworkSnapshot {
  const projectRoot = resolveProjectRoot();
  const striderRoot = resolveStriderRoot(projectRoot);
  const cacheKey = `${projectRoot}|${striderRoot}`;

  if (snapshotCache && snapshotCacheKey === cacheKey) {
    return snapshotCache;
  }

  const pyFiles = walkPythonFiles(striderRoot);

  const models: ModelMetadata[] = [];
  const views: ClassMetadata[] = [];
  const permissions: ClassMetadata[] = [];

  for (const file of pyFiles) {
    let content = "";
    try {
      content = fs.readFileSync(file, "utf8");
    } catch {
      continue;
    }

    const rel = path.relative(striderRoot, file).replace(/\\/g, "/");

    models.push(...parseModelsInFile(content, rel));

    const classes = parseNamedClasses(content, rel);
    views.push(...classes.views);
    permissions.push(...classes.permissions);
  }

  const services = guessServices(striderRoot, pyFiles);

  const workersFile = path.join(striderRoot, "messaging", "workers.py");
  const runnerFile = path.join(striderRoot, "messaging", "runner.py");
  const tasksFile = path.join(striderRoot, "tasks", "registry.py");

  const workers = fs.existsSync(workersFile)
    ? extractNamedFunctionResults(fs.readFileSync(workersFile, "utf8"), "list_workers")
    : [];
  const runners = fs.existsSync(runnerFile)
    ? extractNamedFunctionResults(fs.readFileSync(runnerFile, "utf8"), "list_runners")
    : [];

  let tasks: string[] = [];
  if (fs.existsSync(tasksFile)) {
    const content = fs.readFileSync(tasksFile, "utf8");
    const taskNameMatches = content.match(/_tasks\[[^\]]+\]/g) ?? [];
    const periodicMatches = content.match(/_periodic_tasks\[[^\]]+\]/g) ?? [];
    tasks = [...taskNameMatches, ...periodicMatches].map((item) => item.trim());
  }

  const snapshot: FrameworkSnapshot = {
    projectRoot,
    striderRoot,
    models: dedupeByNameAndSource(models),
    views: dedupeByNameAndSource(views),
    permissions: dedupeByNameAndSource(permissions),
    services,
    workers,
    runners,
    tasks,
  };

  snapshotCache = snapshot;
  snapshotCacheKey = cacheKey;
  return snapshot;
}

function dedupeByNameAndSource<T extends { name: string; source: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  const result: T[] = [];

  for (const item of items) {
    const key = `${item.name}|${item.source}`;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }

  return result;
}

function commandExists(command: string): boolean {
  const probe = spawnSync(command, ["--version"], {
    encoding: "utf8",
    timeout: 5_000,
    env: process.env,
  });
  return !probe.error;
}

function resolvePythonExecutable(projectRoot: string): string {
  const candidates = [
    path.join(projectRoot, ".venv", "bin", "python"),
    path.join(projectRoot, "venv", "bin", "python"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  const envPython = asString(process.env.PYTHON_BIN);
  if (envPython && commandExists(envPython)) {
    return envPython;
  }

  if (commandExists("python3")) return "python3";
  if (commandExists("python")) return "python";

  return envPython || "python3";
}

function resolveStrideInvocation(projectRoot: string): { command: string; prefixArgs: string[] } {
  const candidates = [
    path.join(projectRoot, ".venv", "bin", "stride"),
    path.join(projectRoot, ".venv", "bin", "strider"),
    path.join(projectRoot, "venv", "bin", "stride"),
    path.join(projectRoot, "venv", "bin", "strider"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return { command: candidate, prefixArgs: [] };
    }
  }

  return {
    command: resolvePythonExecutable(projectRoot),
    prefixArgs: ["-m", "strider"],
  };
}

function runCommand(command: string, args: string[], cwd: string, timeoutMs: number): CommandResult {
  const completed = spawnSync(command, args, {
    cwd,
    encoding: "utf8",
    timeout: timeoutMs,
    env: process.env,
  });

  const stdout = (completed.stdout ?? "").toString();
  const stderr = (completed.stderr ?? "").toString();
  const timedOut = completed.signal === "SIGTERM" && !completed.error && completed.status === null;

  if (completed.error) {
    return {
      ok: false,
      command,
      args,
      cwd,
      exitCode: -1,
      stdout,
      stderr: `${stderr}\n${completed.error.message}`.trim(),
      timedOut,
    };
  }

  return {
    ok: completed.status === 0,
    command,
    args,
    cwd,
    exitCode: completed.status ?? -1,
    stdout,
    stderr,
    timedOut,
  };
}

function runStride(args: string[], timeoutMs: number): CommandResult {
  const snapshot = buildFrameworkSnapshot();
  const invocation = resolveStrideInvocation(snapshot.projectRoot);

  if (!commandExists(invocation.command)) {
    return {
      ok: false,
      command: invocation.command,
      args: [...invocation.prefixArgs, ...args],
      cwd: snapshot.projectRoot,
      exitCode: -1,
      stdout: "",
      stderr:
        "Python/stride nao encontrado no runtime. Instale python3 no container ou defina PYTHON_BIN para um executavel valido.",
      timedOut: false,
    };
  }

  const commandArgs = [...invocation.prefixArgs, ...args];
  return runCommand(invocation.command, commandArgs, snapshot.projectRoot, timeoutMs);
}

function isCriticalCliRequest(command: string, args: string[]): boolean {
  const joined = normalizeToken([command, ...args].join(" "));
  const criticalPatterns = [
    /\bmakemigrations\b/,
    /\bmigrate\b/,
    /\brollback\b/,
    /\breset_db\b/,
    /\bdelete-topic\b/,
    /\bpublish\b/,
    /\bdrop\b/,
    /\btruncate\b/,
    /\bpurge\b/,
    /\b--yes\b/,
  ];

  return criticalPatterns.some((pattern) => pattern.test(joined));
}

function formatCommandResult(result: CommandResult): Record<string, unknown> {
  const stdout = result.stdout.length > 8000 ? `${result.stdout.slice(0, 8000)}\n...<truncated>` : result.stdout;
  const stderr = result.stderr.length > 8000 ? `${result.stderr.slice(0, 8000)}\n...<truncated>` : result.stderr;

  return {
    ok: result.ok,
    command: result.command,
    args: result.args,
    cwd: result.cwd,
    exit_code: result.exitCode,
    timed_out: result.timedOut,
    stdout,
    stderr,
  };
}

function statusResult() {
  const total = indexData?.chunks.length ?? 0;
  const docsChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("docs/")).length ?? 0;
  const codeChunks = indexData?.chunks.filter((chunk) => chunk.source.startsWith("code/")).length ?? 0;

  return textResult({
    status: "ready",
    indexed_chunks: total,
    docs_chunks: docsChunks,
    code_chunks: codeChunks,
  });
}

function toolIntrospectFramework() {
  const snapshot = buildFrameworkSnapshot();
  return textResult({
    project_root: snapshot.projectRoot,
    strider_root: snapshot.striderRoot,
    models_count: snapshot.models.length,
    views_count: snapshot.views.length,
    permissions_count: snapshot.permissions.length,
    services_count: snapshot.services.length,
    workers_count: snapshot.workers.length,
    runners_count: snapshot.runners.length,
    tasks_count: snapshot.tasks.length,
    models: snapshot.models.map((model) => ({ name: model.name, source: model.source })),
    views: snapshot.views,
    permissions: snapshot.permissions,
    services: snapshot.services,
  });
}

function toolListModels(args: ToolCallArgs) {
  const snapshot = buildFrameworkSnapshot();
  const includeFields = asBoolean(args.include_fields, true);

  return textResult({
    count: snapshot.models.length,
    models: snapshot.models.map((model) => ({
      name: model.name,
      source: model.source,
      fields: includeFields ? model.fields : undefined,
      relations: includeFields ? model.relations : undefined,
    })),
  });
}

function toolDescribeModel(args: ToolCallArgs) {
  const modelName = asString(args.model);
  if (!modelName) {
    return toolError("Parametro obrigatorio ausente: model");
  }

  const snapshot = buildFrameworkSnapshot();
  const normalizedTarget = normalizeToken(modelName);
  const model = snapshot.models.find((item) => normalizeToken(item.name) === normalizedTarget);

  if (!model) {
    return toolError("Model nao encontrado", {
      model: modelName,
      available_models: snapshot.models.map((item) => item.name),
    });
  }

  return textResult({
    model: model.name,
    source: model.source,
    fields: model.fields,
    relationships: model.relations,
    rules: [
      "Use apenas APIs do framework: Model.objects.filter/get/create/update/delete.",
      "Nao use SQL manual nem acesso direto via SQLAlchemy no MCP.",
      "Valide permissao antes de acoes de escrita ou execucao.",
    ],
  });
}

function toolListCapabilities() {
  const snapshot = buildFrameworkSnapshot();

  const capabilities = {
    can_read_data: snapshot.models.length > 0,
    can_create: snapshot.models.length > 0 || snapshot.views.length > 0,
    can_update: snapshot.models.length > 0 || snapshot.views.length > 0,
    can_delete: snapshot.models.length > 0,
    can_execute_workers: snapshot.workers.length > 0,
    can_execute_runners: snapshot.runners.length > 0,
    can_dispatch_tasks: snapshot.tasks.length > 0,
    has_permissions_layer: snapshot.permissions.length > 0,
  };

  return textResult({
    capabilities,
    recommendations: [
      "Use validate_action antes de qualquer operacao de escrita/execucao.",
      "Use generate_safe_query para gerar padroes ORM sem SQL manual.",
      "Para comandos criticos de CLI, exija confirmacao explicita.",
    ],
  });
}

function toolValidateAction(args: ToolCallArgs) {
  const action = asString(args.action);
  const resourceType = normalizeToken(asString(args.resource_type) || "model");
  const resourceName = asString(args.resource_name);

  if (!action) {
    return toolError("Parametro obrigatorio ausente: action");
  }

  const snapshot = buildFrameworkSnapshot();
  const warnings: string[] = [];
  const checks: string[] = [];
  let exists = false;

  const targetNorm = normalizeToken(resourceName);

  if (resourceType === "model") {
    exists = snapshot.models.some((item) => normalizeToken(item.name) === targetNorm);
    checks.push("Model existe no framework");
  } else if (resourceType === "view") {
    exists = snapshot.views.some((item) => normalizeToken(item.name) === targetNorm);
    checks.push("View/ViewSet existe no framework");
  } else if (resourceType === "worker") {
    exists = snapshot.workers.some((item) => normalizeToken(item) === targetNorm);
    checks.push("Worker registrado");
  } else if (resourceType === "runner") {
    exists = snapshot.runners.some((item) => normalizeToken(item) === targetNorm);
    checks.push("Runner registrado");
  } else if (resourceType === "task") {
    exists = snapshot.tasks.length > 0;
    checks.push("Tasks registradas no sistema");
  } else {
    warnings.push(`resource_type desconhecido: ${resourceType}`);
  }

  if (!resourceName) {
    warnings.push("resource_name nao informado; validacao parcial");
    exists = true;
  }

  const writeLike = ["create", "update", "delete", "execute", "run", "dispatch"].includes(normalizeToken(action));
  if (writeLike && snapshot.permissions.length === 0) {
    warnings.push("Nao foram detectadas classes de permissao; valide middleware/policies antes de executar");
  }

  const valid = exists && warnings.filter((item) => item.includes("desconhecido")).length === 0;

  return textResult({
    action,
    resource_type: resourceType,
    resource_name: resourceName,
    valid,
    checks,
    warnings,
    guidance: [
      "Bloqueie execucao se valid=false.",
      "Em operacoes criticas, solicite confirmacao humana antes de executar.",
    ],
  });
}

function toolGenerateSafeQuery(args: ToolCallArgs) {
  const modelName = asString(args.model);
  const operation = normalizeToken(asString(args.operation) || "filter");
  const filters = asRecord(args.filters);

  if (!modelName) {
    return toolError("Parametro obrigatorio ausente: model");
  }

  const snapshot = buildFrameworkSnapshot();
  const model = snapshot.models.find((item) => normalizeToken(item.name) === normalizeToken(modelName));

  if (!model) {
    return toolError("Model nao encontrado para gerar query segura", {
      requested_model: modelName,
      available_models: snapshot.models.map((item) => item.name),
    });
  }

  const allowedOperations = new Set(["filter", "get", "all", "create", "update", "delete"]);
  if (!allowedOperations.has(operation)) {
    return toolError("Operacao nao suportada. Use: filter|get|all|create|update|delete", { operation });
  }

  const filterEntries = Object.entries(filters);
  const unknownFields = filterEntries
    .map(([key]) => key)
    .filter((key) => model.fields.length > 0 && !model.fields.includes(key));

  if (unknownFields.length > 0) {
    return toolError("Campos invalidos para o model informado", {
      model: model.name,
      invalid_fields: unknownFields,
      known_fields: model.fields,
    });
  }

  const safeFilter = filterEntries
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");

  let expression = "";
  if (operation === "all") {
    expression = `${model.name}.objects.all()`;
  } else if (operation === "filter") {
    expression = `${model.name}.objects.filter(${safeFilter || "..."})`;
  } else if (operation === "get") {
    expression = `${model.name}.objects.get(${safeFilter || "..."})`;
  } else if (operation === "create") {
    expression = `${model.name}.objects.create(${safeFilter || "..."})`;
  } else if (operation === "update") {
    expression = `${model.name}.objects.filter(${safeFilter || "..."}).update(campo=valor)`;
  } else {
    expression = `${model.name}.objects.filter(${safeFilter || "..."}).delete()`;
  }

  return textResult({
    model: model.name,
    operation,
    expression,
    constraints: [
      "Nao gerar SQL manual.",
      "Nao usar SQLAlchemy diretamente.",
      "Aplicar validate_action antes da execucao.",
    ],
  });
}

function toolExplainUsage() {
  return textResult({
    flow: [
      "1) introspect_framework",
      "2) list_models / describe_model",
      "3) list_capabilities",
      "4) validate_action",
      "5) generate_safe_query",
      "6) cli_* (somente quando necessario)",
    ],
    guardrails: [
      "Nunca use SQL manual.",
      "Nunca hardcode credenciais; use .env e settings.py.",
      "Nunca rode comando critico de CLI sem confirmacao explicita.",
      "Priorize execucao local no projeto do cliente para evitar divergencias.",
    ],
    scalability: {
      required_env: ["DB_HOST", "DB_REPLICA_HOST", "REDIS_URL", "KAFKA_BROKER"],
      recommendations: [
        "Configurar read replicas para leitura.",
        "Configurar pool de conexoes no banco.",
        "Usar Redis para cache e filas.",
        "Usar Kafka (ou equivalente) para eventos assincronos.",
      ],
    },
  });
}

function toolCliListCommands() {
  const snapshot = buildFrameworkSnapshot();
  const invocation = resolveStrideInvocation(snapshot.projectRoot);

  return textResult({
    cli_invocation: [invocation.command, ...invocation.prefixArgs],
    read_only_commands: [
      ["check"],
      ["routes"],
      ["showmigrations"],
      ["version"],
      ["test", "--help"],
    ],
    write_or_critical_commands: [
      ["makemigrations"],
      ["migrate"],
      ["rollback"],
      ["reset_db", "--yes"],
    ],
    notes: [
      `Comandos criticos exigem confirm='${CRITICAL_CONFIRMATION_TOKEN}'.`,
      "Priorize --dry-run quando suportado.",
    ],
  });
}

function toolCliExecute(args: ToolCallArgs) {
  const command = asString(args.command);
  const commandArgs = asStringArray(args.args);
  const confirm = asString(args.confirm);
  const timeoutMs = Math.max(1_000, asNumber(args.timeout_ms, DEFAULT_TIMEOUT_MS));

  if (!command) {
    return toolError("Parametro obrigatorio ausente: command");
  }

  const critical = isCriticalCliRequest(command, commandArgs);
  if (critical && confirm !== CRITICAL_CONFIRMATION_TOKEN) {
    return toolError("Comando critico bloqueado sem confirmacao explicita", {
      required_confirm: CRITICAL_CONFIRMATION_TOKEN,
      command,
      args: commandArgs,
    });
  }

  let result: CommandResult;

  if (["stride", "strider", "core", "framework-cli"].includes(command)) {
    result = runStride(commandArgs, timeoutMs);
  } else if (command === "python-strider") {
    result = runStride(commandArgs, timeoutMs);
  } else {
    const snapshot = buildFrameworkSnapshot();
    result = runCommand(command, commandArgs, snapshot.projectRoot, timeoutMs);

    if (!result.ok && /enoent/i.test(result.stderr) && ["stride", "strider", "core"].includes(command)) {
      result = runStride(commandArgs, timeoutMs);
    }
  }

  return textResult({
    critical,
    confirmation_used: confirm || null,
    result: formatCommandResult(result),
  });
}

function toolCliRegistryHealth(args: ToolCallArgs) {
  const timeoutMs = Math.max(1_000, asNumber(args.timeout_ms, DEFAULT_TIMEOUT_MS));
  const checks: Array<Record<string, unknown>> = [];

  const strideChecks: Array<{ name: string; args: string[] }> = [
    { name: "check", args: ["check"] },
    { name: "routes", args: ["routes"] },
    { name: "showmigrations", args: ["showmigrations"] },
  ];

  for (const check of strideChecks) {
    const result = runStride(check.args, timeoutMs);
    checks.push({
      name: check.name,
      ...formatCommandResult(result),
    });
  }

  const snapshot = buildFrameworkSnapshot();
  const python = resolvePythonExecutable(snapshot.projectRoot);
  const probe = [
    "import json",
    "payload = {}",
    "try:",
    "    from strider.messaging import list_workers, list_runners",
    "    payload['workers'] = list_workers()",
    "    payload['runners'] = list_runners()",
    "except Exception as exc:",
    "    payload['messaging_error'] = str(exc)",
    "try:",
    "    from strider.tasks.registry import list_tasks",
    "    payload['tasks'] = list_tasks()",
    "except Exception as exc:",
    "    payload['tasks_error'] = str(exc)",
    "print(json.dumps(payload, ensure_ascii=True))",
  ].join("\n");

  const registryProbe = runCommand(python, ["-c", probe], snapshot.projectRoot, timeoutMs);
  checks.push({ name: "registry_probe", ...formatCommandResult(registryProbe) });

  const ok = checks.every((item) => item.ok === true || item.name === "showmigrations");

  return textResult({
    ok,
    checks,
    guidance: [
      "Se registry_probe falhar, valide settings.py/.env e auto-discovery de workers/tasks.",
      "Para testes de carga de runners/workers, use cli_run_tests e comandos dedicados com confirmacao quando necessario.",
    ],
  });
}

function toolCliRunTests(args: ToolCallArgs) {
  const target = asString(args.test_target);
  const withCoverage = asBoolean(args.with_coverage, false);
  const timeoutMs = Math.max(1_000, asNumber(args.timeout_ms, 180_000));

  const commandArgs = ["test"];
  if (target) commandArgs.push(target);
  if (withCoverage) commandArgs.push("--cov");

  const result = runStride(commandArgs, timeoutMs);

  return textResult({
    target: target || "tests/",
    with_coverage: withCoverage,
    result: formatCommandResult(result),
  });
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
      {
        name: "introspect_framework",
        description: "Descobre models, views, permissoes, servicos e recursos operacionais do framework.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "list_models",
        description: "Lista todos os models disponiveis e seus campos basicos.",
        inputSchema: {
          type: "object",
          properties: {
            include_fields: { type: "boolean", description: "Inclui campos e relacionamentos no resultado." },
          },
        },
      },
      {
        name: "describe_model",
        description: "Detalha um model com campos, relacionamentos e regras de uso seguro.",
        inputSchema: {
          type: "object",
          properties: {
            model: { type: "string", description: "Nome do model a ser descrito." },
          },
          required: ["model"],
        },
      },
      {
        name: "list_capabilities",
        description: "Lista capacidades funcionais disponiveis no contexto atual.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "validate_action",
        description: "Valida se uma acao pode ser executada com seguranca para um recurso.",
        inputSchema: {
          type: "object",
          properties: {
            action: { type: "string", description: "Acao desejada: create/update/delete/execute/read." },
            resource_type: { type: "string", description: "Tipo: model/view/worker/runner/task." },
            resource_name: { type: "string", description: "Nome do recurso alvo." },
          },
          required: ["action"],
        },
      },
      {
        name: "generate_safe_query",
        description: "Gera query segura usando apenas abstrações do framework (Model.objects.*).",
        inputSchema: {
          type: "object",
          properties: {
            model: { type: "string", description: "Nome do model." },
            operation: { type: "string", description: "filter|get|all|create|update|delete" },
            filters: {
              type: "object",
              description: "Mapa de filtros para a query segura.",
              additionalProperties: true,
            },
          },
          required: ["model"],
        },
      },
      {
        name: "explain_usage",
        description: "Explica fluxo recomendado para agentes consumidores e guardrails obrigatorios.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "cli_list_commands",
        description: "Lista comandos CLI disponiveis e classifica comandos criticos.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "cli_execute",
        description: "Executa comando CLI local no projeto atual; exige confirmacao para comandos criticos.",
        inputSchema: {
          type: "object",
          properties: {
            command: { type: "string", description: "Comando base (ex.: stride, strider, core, python-strider)." },
            args: {
              type: "array",
              items: { type: "string" },
              description: "Argumentos do comando.",
            },
            confirm: { type: "string", description: `Use ${CRITICAL_CONFIRMATION_TOKEN} para comandos criticos.` },
            timeout_ms: { type: "integer", minimum: 1000, maximum: 900000 },
          },
          required: ["command"],
        },
      },
      {
        name: "cli_registry_health",
        description: "Valida registros e saude operacional de workers/runners/tasks e comandos de diagnostico.",
        inputSchema: {
          type: "object",
          properties: {
            timeout_ms: { type: "integer", minimum: 1000, maximum: 900000 },
          },
        },
      },
      {
        name: "cli_run_tests",
        description: "Executa suite de testes via CLI local (com alvo opcional).",
        inputSchema: {
          type: "object",
          properties: {
            test_target: { type: "string", description: "Arquivo/pasta alvo de teste." },
            with_coverage: { type: "boolean", description: "Executa com cobertura (--cov)." },
            timeout_ms: { type: "integer", minimum: 1000, maximum: 900000 },
          },
        },
      },
    ],
  };
}

function callToolResult(params: unknown) {
  const p = (params ?? {}) as {
    name?: string;
    arguments?: ToolCallArgs;
  };

  const args = p.arguments ?? {};

  if (p.name === "status") {
    return statusResult();
  }

  if (p.name === "search_framework") {
    const question = asString(args.question);
    const topK = asNumber(args.topK, 5);

    if (!question) {
      return toolError("question e obrigatoria");
    }

    if (!indexData) {
      return toolError("Indice nao inicializado");
    }

    const payload = buildAnswerPayload(indexData, question, topK);
    return textResult(payload);
  }

  if (p.name === "introspect_framework") {
    return toolIntrospectFramework();
  }

  if (p.name === "list_models") {
    return toolListModels(args);
  }

  if (p.name === "describe_model") {
    return toolDescribeModel(args);
  }

  if (p.name === "list_capabilities") {
    return toolListCapabilities();
  }

  if (p.name === "validate_action") {
    return toolValidateAction(args);
  }

  if (p.name === "generate_safe_query") {
    return toolGenerateSafeQuery(args);
  }

  if (p.name === "explain_usage") {
    return toolExplainUsage();
  }

  if (p.name === "cli_list_commands") {
    return toolCliListCommands();
  }

  if (p.name === "cli_execute") {
    return toolCliExecute(args);
  }

  if (p.name === "cli_registry_health") {
    return toolCliRegistryHealth(args);
  }

  if (p.name === "cli_run_tests") {
    return toolCliRunTests(args);
  }

  return toolError(`Tool desconhecida: ${p.name ?? ""}`);
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
        version: "0.2.0",
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
  const transport = (process.env.MCP_TRANSPORT || "").toLowerCase();
  const port = argPort || Number(process.env.PORT || 0);

  if (forceStdio) {
    runStdio();
    return;
  }

  if (forceHttp) {
    runHttp(port || 8080);
    return;
  }

  if (transport === "http" || port > 0) {
    runHttp(port || 8080);
    return;
  }

  if (transport === "stdio") {
    runStdio();
    return;
  }

  runStdio();
}

main().catch((err) => {
  console.error("Failed to start MCP stdio server:", err);
  process.exit(1);
});
