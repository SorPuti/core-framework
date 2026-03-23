import { buildQueryVector, cosineSimilarity, DocChunk, IndexData } from "./indexer";

export interface QueryResult {
  chunk: DocChunk;
  score: number;
}

export interface QueryOptions {
  topK?: number;
  sourcePrefix?: string;
  sourcePrefixes?: string[];
  excludeSources?: Set<string>;
  boostPrefixes?: string[];
  intentTerms?: string[];
}

export interface CodeReference {
  score: number;
  source: string;
  text: string;
}

export interface AnswerItem {
  score: number;
  source: string;
  text: string;
  code_references: CodeReference[];
}

export interface AnswerPayload {
  question: string;
  domain: string;
  implementation_steps: string[];
  files_to_touch: string[];
  validation_checks: string[];
  pitfalls: string[];
  answers: AnswerItem[];
}

interface DomainProfile {
  name: string;
  strongKeywords: string[];
  keywords: string[];
  docPrefixes: string[];
  codePrefixes: string[];
  implementationSteps: string[];
  filesToTouch: string[];
  validationChecks: string[];
  pitfalls: string[];
}

const DOMAIN_PROFILES: DomainProfile[] = [
  {
    name: "routing",
    strongKeywords: ["viewset", "custom action", "register_viewset", "router", "basename"],
    keywords: ["rota", "endpoint", "action", "url"],
    docPrefixes: ["docs/23-routing", "docs/01-quickstart", "docs/04-viewsets"],
    codePrefixes: ["code/routing.py", "code/views.py", "code/urls.py"],
    implementationSteps: [
      "Defina o ViewSet com serializer_class e permission_classes.",
      "Registre o ViewSet no Router com basename consistente.",
      "Inclua as URLs no módulo principal e valide ações customizadas.",
    ],
    filesToTouch: ["strider/views.py", "strider/routing.py", "strider/urls.py"],
    validationChecks: [
      "Confirmar rotas no OpenAPI com métodos corretos.",
      "Garantir ausência de conflitos de path e basename.",
      "Testar create/list/retrieve/update/delete e custom actions.",
    ],
    pitfalls: [
      "Registrar rota duplicada para o mesmo prefixo.",
      "Misturar serializer do viewset com schemas conflitantes.",
    ],
  },
  {
    name: "auth",
    strongKeywords: ["jwt", "login", "logout", "refresh", "permission", "permissao", "autentic"],
    keywords: ["auth", "token"],
    docPrefixes: ["docs/05-auth", "docs/06-auth-backends", "docs/08-permissions"],
    codePrefixes: ["code/auth/", "code/permissions.py", "code/auth/views.py"],
    implementationSteps: [
      "Configure user model e backend de token no settings.",
      "Exponha endpoints de login/refresh/logout e endpoint de identidade.",
      "Aplique permission_classes por endpoint e por ação.",
    ],
    filesToTouch: ["strider/auth/views.py", "strider/auth/tokens.py", "strider/permissions.py"],
    validationChecks: [
      "Validar fluxo login -> token -> acesso autenticado.",
      "Verificar refresh token e revogação/logout.",
      "Cobrir casos 401/403 em testes.",
    ],
    pitfalls: [
      "Esquecer de proteger endpoints sensíveis.",
      "Não validar token_type ao fazer refresh.",
    ],
  },
  {
    name: "data",
    strongKeywords: ["queryset", "tenancy", "tenant", "relation", "relations", "paginacao"],
    keywords: ["filtro", "orden", "model", "workspace", "isolamento", "schema"],
    docPrefixes: ["docs/03-models", "docs/12-querysets", "docs/11-relations", "docs/32-tenancy"],
    codePrefixes: ["code/models.py", "code/querysets.py", "code/relations.py", "code/tenancy.py"],
    implementationSteps: [
      "Modele entidades com chaves e relações explícitas.",
      "Implemente filtros/ordenação/paginação via QuerySet.",
      "Rode migrações e valide consistência de schema.",
    ],
    filesToTouch: ["strider/models.py", "strider/querysets.py", "strider/migrations/"],
    validationChecks: [
      "Executar migrações em ambiente limpo e com dados existentes.",
      "Validar índices e cardinalidade das relações.",
      "Confirmar isolamento de tenancy quando habilitado.",
    ],
    pitfalls: [
      "Alterar tipo de coluna sem plano de migração de dados.",
      "N+1 em relações sem estratégia de carregamento.",
    ],
  },
  {
    name: "migrations",
    strongKeywords: ["migration", "migrations", "migracao", "migracoes", "schema drift", "alembic"],
    keywords: ["ddl", "backfill", "rollback", "downgrade", "upgrade", "coluna", "indice"],
    docPrefixes: ["docs/41-migrations", "docs/03-models", "docs/99-faq-troubleshooting"],
    codePrefixes: ["code/migrations/", "code/models.py", "code/database.py"],
    implementationSteps: [
      "Defina a alteracao de schema e avalie impacto em dados existentes.",
      "Crie migracao incremental com plano de rollback/backfill quando necessario.",
      "Execute migrate em base limpa e em base com dados para validar compatibilidade.",
    ],
    filesToTouch: ["strider/migrations/", "strider/models.py", "strider/database.py"],
    validationChecks: [
      "Testar upgrade e downgrade em ambiente de homologacao.",
      "Validar tempo de execucao e locks em tabelas grandes.",
      "Garantir compatibilidade com replicas durante rollout.",
    ],
    pitfalls: [
      "Aplicar alteracao destrutiva sem backfill/rollback planejado.",
      "Assumir que migracao funciona sem testar com dados reais.",
    ],
  },
  {
    name: "dependencies",
    strongKeywords: ["dependency", "dependencies", "injecao", "inject", "provider", "container"],
    keywords: ["di", "bind", "resolver", "factory", "wiring", "inversao de controle"],
    docPrefixes: ["docs/24-dependencies", "docs/01-quickstart", "docs/02-settings"],
    codePrefixes: ["code/dependencies.py", "code/config.py", "code/views.py"],
    implementationSteps: [
      "Defina a dependencia como provider/factory com contrato claro.",
      "Registre a dependencia no ponto de composicao da aplicacao.",
      "Injete no endpoint/servico e cubra override em testes.",
    ],
    filesToTouch: ["strider/dependencies.py", "strider/config.py", "strider/views.py"],
    validationChecks: [
      "Validar ciclo de vida (singleton/request/transient) quando aplicavel.",
      "Garantir que testes conseguem sobrescrever providers.",
      "Verificar falhas de resolucao com mensagens claras.",
    ],
    pitfalls: [
      "Criar dependencia com estado global nao controlado.",
      "Acoplar regra de negocio ao container em vez de contrato.",
    ],
  },
  {
    name: "exceptions",
    strongKeywords: ["exception", "exceptions", "erro", "errors", "raise", "handler", "traceback"],
    keywords: ["status code", "422", "400", "500", "custom exception", "validation error"],
    docPrefixes: ["docs/34-exceptions", "docs/14-validators", "docs/99-faq-troubleshooting"],
    codePrefixes: ["code/exceptions.py", "code/validation.py", "code/validators.py"],
    implementationSteps: [
      "Modele excecoes de dominio com mensagens e codigos consistentes.",
      "Mapeie excecoes para respostas HTTP no handler central.",
      "Cubra erros esperados com testes de contrato e observabilidade.",
    ],
    filesToTouch: ["strider/exceptions.py", "strider/validation.py", "strider/validators.py"],
    validationChecks: [
      "Confirmar payload de erro (code/message/details) em todos os endpoints.",
      "Garantir que erros de validacao retornem 4xx, nao 5xx.",
      "Verificar logs com contexto sem expor dados sensiveis.",
    ],
    pitfalls: [
      "Lancar excecoes genericas sem mapeamento para HTTP adequado.",
      "Vazar stacktrace ou dados sensiveis para o cliente.",
    ],
  },
  {
    name: "realtime-workers",
    strongKeywords: ["websocket", "sse", "worker", "kafka", "messaging", "queue"],
    keywords: ["task", "stream", "consumer", "producer"],
    docPrefixes: ["docs/25-realtime", "docs/30-messaging", "docs/31-workers"],
    codePrefixes: ["code/realtime.py", "code/messaging/", "code/tasks/", "code/cli/main.py"],
    implementationSteps: [
      "Defina contrato de eventos e canais de publicação/consumo.",
      "Implemente worker/task com retry, timeout e idempotência.",
      "Exponha stream realtime com autenticação adequada.",
    ],
    filesToTouch: ["strider/realtime.py", "strider/messaging/", "strider/tasks/"],
    validationChecks: [
      "Testar reconexão e retomada de consumidores.",
      "Medir latência e throughput em carga.",
      "Validar dead-letter/retry para falhas transitórias.",
    ],
    pitfalls: [
      "Processamento não idempotente em retries.",
      "Acoplamento forte entre payload de evento e implementação interna.",
    ],
  },
  {
    name: "testing",
    strongKeywords: ["pytest", "authenticatedclient", "fixture", "mock", "permission test"],
    keywords: ["teste", "test", "client"],
    docPrefixes: ["docs/testing", "docs/05-auth", "docs/08-permissions", "docs/04-viewsets"],
    codePrefixes: ["code/testing/", "code/auth/", "code/permissions.py", "code/views.py"],
    implementationSteps: [
      "Monte fixtures de app, banco e usuário autenticado.",
      "Cubra casos de sucesso, autenticação e autorização (401/403).",
      "Valide payload, contrato de resposta e efeitos colaterais.",
    ],
    filesToTouch: ["tests/", "strider/testing/", "strider/auth/"],
    validationChecks: [
      "Executar suite com e sem autenticação para o mesmo endpoint.",
      "Garantir asserts de permissões por ação e por papel.",
      "Validar regressões em endpoints críticos com smoke tests.",
    ],
    pitfalls: [
      "Testes acoplados a estado global sem reset de contexto.",
      "Cobrir apenas caminho feliz sem validar 401/403/422.",
    ],
  },
];

const DEFAULT_PROFILE: DomainProfile = {
  name: "general",
  strongKeywords: [],
  keywords: [],
  docPrefixes: ["docs/01-quickstart", "docs/core-concepts", "docs/introduction"],
  codePrefixes: ["code/views.py", "code/routing.py", "code/config.py"],
  implementationSteps: [
    "Mapeie o caso de uso e selecione módulo principal do framework.",
    "Implemente a menor fatia funcional fim a fim (model -> endpoint -> teste).",
    "Valide contratos de entrada/saída e cobertura de erro.",
  ],
  filesToTouch: ["strider/views.py", "strider/routing.py", "strider/config.py"],
  validationChecks: [
    "Executar testes unitários e de integração para o fluxo principal.",
    "Conferir documentação OpenAPI e exemplos.",
  ],
  pitfalls: [
    "Responder com abstrações sem mapear arquivos reais.",
    "Ignorar validações e cenários de falha na implementação.",
  ],
};

function detectDomainProfile(question: string): DomainProfile {
  const normalized = normalizeSearchText(question);
  let best: DomainProfile = DEFAULT_PROFILE;
  let bestScore = 0;

  for (const profile of DOMAIN_PROFILES) {
    let score = 0;
    for (const keyword of profile.strongKeywords) {
      if (normalized.includes(normalizeSearchText(keyword))) score += 3;
    }
    for (const keyword of profile.keywords) {
      if (normalized.includes(normalizeSearchText(keyword))) score += 1;
    }
    if (score > bestScore) {
      best = profile;
      bestScore = score;
    }
  }

  return best;
}

function normalizeSearchText(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim();
}

function matchesPrefix(source: string, prefixes: string[]): boolean {
  for (const prefix of prefixes) {
    if (source.startsWith(prefix)) return true;
  }
  return false;
}

function sourceBoost(source: string, boostPrefixes: string[] | undefined): number {
  if (!boostPrefixes || boostPrefixes.length === 0) return 1;
  return matchesPrefix(source, boostPrefixes) ? 1.4 : 0.9;
}

function extractIntentTerms(question: string): string[] {
  const stopWords = new Set([
    "como", "para", "com", "sem", "uma", "um", "das", "dos", "que", "this", "that", "when", "where",
    "qual", "quais", "sobre", "de", "do", "da", "the", "and", "with", "from", "into", "entre", "no", "na",
    "nos", "nas", "por", "porque", "why", "how", "what", "quero", "preciso", "implementar", "configurar",
  ]);

  const terms = normalizeSearchText(question)
    .split(/[^a-z0-9]+/i)
    .filter((token) => token.length >= 4 && !stopWords.has(token));

  return Array.from(new Set(terms)).slice(0, 12);
}

function intentBoost(source: string, text: string, intentTerms: string[] | undefined): number {
  if (!intentTerms || intentTerms.length === 0) return 1;

  const sourceNorm = normalizeSearchText(source);
  const textNorm = normalizeSearchText(text);
  let hits = 0;

  for (const term of intentTerms) {
    if (sourceNorm.includes(term) || textNorm.includes(term)) {
      hits += 1;
    }
  }

  if (hits === 0) return 0.86;
  return 1 + Math.min(0.48, hits * 0.08);
}

export function queryIndex(index: IndexData, question: string, options: QueryOptions = {}): QueryResult[] {
  const topK = options.topK ?? 3;
  const queryVector = buildQueryVector(question, index.idf);
  const hits: QueryResult[] = [];

  for (const chunk of index.chunks) {
    if (options.sourcePrefix && !chunk.source.startsWith(options.sourcePrefix)) {
      continue;
    }
    if (options.sourcePrefixes && options.sourcePrefixes.length > 0 && !matchesPrefix(chunk.source, options.sourcePrefixes)) {
      continue;
    }
    if (options.excludeSources?.has(chunk.source)) {
      continue;
    }

    const score =
      cosineSimilarity(queryVector, chunk.vector) *
      sourceBoost(chunk.source, options.boostPrefixes) *
      intentBoost(chunk.source, chunk.text, options.intentTerms);
    if (score > 0) {
      hits.push({ chunk, score });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, topK);
}

export function buildAnswerPayload(index: IndexData, question: string, topK = 5): AnswerPayload {
  const profile = detectDomainProfile(question);
  const intentTerms = extractIntentTerms(question);

  const docResults = queryIndex(index, question, {
    topK,
    sourcePrefix: "docs/",
    boostPrefixes: profile.docPrefixes,
    intentTerms,
  });
  const results = docResults.length > 0 ? docResults : queryIndex(index, question, { topK, intentTerms });

  return {
    question,
    domain: profile.name,
    implementation_steps: profile.implementationSteps,
    files_to_touch: profile.filesToTouch,
    validation_checks: profile.validationChecks,
    pitfalls: profile.pitfalls,
    answers: results.map((hit) => ({
      score: hit.score,
      source: hit.chunk.source,
      text: hit.chunk.text.slice(0, 1200),
      code_references: (() => {
        const codeCandidates = queryIndex(index, `${question}\n${hit.chunk.text.slice(0, 800)}`, {
          topK: 8,
          sourcePrefix: "code/",
          boostPrefixes: profile.codePrefixes,
          intentTerms,
        });

        // Prefer unique code files to reduce repetition and improve actionable guidance.
        const seen = new Set<string>();
        const unique = [] as CodeReference[];
        for (const codeHit of codeCandidates) {
          if (seen.has(codeHit.chunk.source)) continue;
          seen.add(codeHit.chunk.source);
          unique.push({
            score: codeHit.score,
            source: codeHit.chunk.source,
            text: codeHit.chunk.text.slice(0, 400),
          });
          if (unique.length >= 3) break;
        }
        return unique;
      })(),
    })),
  };
}
