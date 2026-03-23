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
