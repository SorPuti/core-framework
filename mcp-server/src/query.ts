import { buildQueryVector, cosineSimilarity, DocChunk, IndexData } from "./indexer";

export interface QueryResult {
  chunk: DocChunk;
  score: number;
}

export function queryIndex(index: IndexData, question: string, topK = 3): QueryResult[] {
  const queryVector = buildQueryVector(question, index.idf);
  const hits: QueryResult[] = [];

  for (const chunk of index.chunks) {
    const score = cosineSimilarity(queryVector, chunk.vector);
    if (score > 0) {
      hits.push({ chunk, score });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, topK);
}
