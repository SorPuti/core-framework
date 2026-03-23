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
    keywords: ["rota", "router", "endpoint", "viewset", "action", "url"],
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
    keywords: ["auth", "jwt", "login", "logout", "token", "refresh", "permission"],
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
    keywords: ["queryset", "filtro", "orden", "pagin", "model", "relation", "migrat", "tenant"],
    docPrefixes: ["docs/03-models", "docs/12-querysets", "docs/11-relations", "docs/41-migrations", "docs/32-tenancy"],
    codePrefixes: ["code/models.py", "code/querysets.py", "code/relations.py", "code/migrations/", "code/tenancy.py"],
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
    name: "realtime-workers",
    keywords: ["websocket", "sse", "worker", "task", "kafka", "messaging", "queue"],
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
];

const DEFAULT_PROFILE: DomainProfile = {
  name: "general",
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
  const normalized = question.toLowerCase();
  let best: DomainProfile = DEFAULT_PROFILE;
  let bestScore = 0;

  for (const profile of DOMAIN_PROFILES) {
    let score = 0;
    for (const keyword of profile.keywords) {
      if (normalized.includes(keyword)) score += 1;
    }
    if (score > bestScore) {
      best = profile;
      bestScore = score;
    }
  }

  return best;
}

function matchesPrefix(source: string, prefixes: string[]): boolean {
  for (const prefix of prefixes) {
    if (source.startsWith(prefix)) return true;
  }
  return false;
}

function sourceBoost(source: string, boostPrefixes: string[] | undefined): number {
  if (!boostPrefixes || boostPrefixes.length === 0) return 1;
  return matchesPrefix(source, boostPrefixes) ? 1.35 : 1;
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

    const score = cosineSimilarity(queryVector, chunk.vector) * sourceBoost(chunk.source, options.boostPrefixes);
    if (score > 0) {
      hits.push({ chunk, score });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, topK);
}

export function buildAnswerPayload(index: IndexData, question: string, topK = 5): AnswerPayload {
  const profile = detectDomainProfile(question);

  const docResults = queryIndex(index, question, {
    topK,
    sourcePrefix: "docs/",
    boostPrefixes: profile.docPrefixes,
  });
  const results = docResults.length > 0 ? docResults : queryIndex(index, question, { topK });

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
