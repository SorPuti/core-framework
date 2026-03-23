import { buildQueryVector, cosineSimilarity, DocChunk, IndexData } from "./indexer";

export interface QueryResult {
  chunk: DocChunk;
  score: number;
}

export interface QueryOptions {
  topK?: number;
  sourcePrefix?: string;
  excludeSources?: Set<string>;
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
  answers: AnswerItem[];
}

export function queryIndex(index: IndexData, question: string, options: QueryOptions = {}): QueryResult[] {
  const topK = options.topK ?? 3;
  const queryVector = buildQueryVector(question, index.idf);
  const hits: QueryResult[] = [];

  for (const chunk of index.chunks) {
    if (options.sourcePrefix && !chunk.source.startsWith(options.sourcePrefix)) {
      continue;
    }
    if (options.excludeSources?.has(chunk.source)) {
      continue;
    }

    const score = cosineSimilarity(queryVector, chunk.vector);
    if (score > 0) {
      hits.push({ chunk, score });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, topK);
}

export function buildAnswerPayload(index: IndexData, question: string, topK = 5): AnswerPayload {
  const docResults = queryIndex(index, question, { topK, sourcePrefix: "docs/" });
  const results = docResults.length > 0 ? docResults : queryIndex(index, question, { topK });

  return {
    question,
    answers: results.map((hit) => ({
      score: hit.score,
      source: hit.chunk.source,
      text: hit.chunk.text.slice(0, 1200),
      code_references: queryIndex(index, `${question}\n${hit.chunk.text.slice(0, 800)}`, {
        topK: 3,
        sourcePrefix: "code/",
      }).map((codeHit) => ({
        score: codeHit.score,
        source: codeHit.chunk.source,
        text: codeHit.chunk.text.slice(0, 400),
      })),
    })),
  };
}
