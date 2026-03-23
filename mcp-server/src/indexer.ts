import fs from "fs";
import path from "path";
import { globby } from "globby";

export interface DocChunk {
  id: string;
  source: string;
  text: string;
  tokens: string[];
  vector: Record<string, number>;
}

export interface IndexData {
  chunks: DocChunk[];
  idf: Record<string, number>;
}

const DOCS_DIR = path.resolve(__dirname, "..", "..", "..", "docs");
const DATA_DIR = path.resolve(__dirname, "..", "..", "data");
const INDEX_FILE = path.join(DATA_DIR, "index.json");

function normalizeText(raw: string): string {
  return raw
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .replace(/\n+/g, "\n")
    .replace(/```[\s\S]*?```/g, "")
    .toLowerCase();
}

function tokenize(text: string): string[] {
  return text
    .split(/[^a-z0-9]+/i)
    .map((token) => token.trim())
    .filter((token) => token.length > 2);
}

function buildTF(tokens: string[]): Record<string, number> {
  const tf: Record<string, number> = {};
  for (const token of tokens) {
    tf[token] = (tf[token] || 0) + 1;
  }
  const size = tokens.length || 1;
  for (const key of Object.keys(tf)) {
    tf[key] = tf[key] / size;
  }
  return tf;
}

async function loadDocsAndCode(): Promise<{ path: string; text: string }[]> {
  const docsPatterns = ["**/*.md"];
  const codePatterns = ["**/*.py"];

  const docFiles = await globby(docsPatterns, { cwd: DOCS_DIR, absolute: true });
  const codeFiles = await globby(codePatterns, { cwd: path.resolve(__dirname, "..", "..", "strider"), absolute: true });

  const files: { path: string; text: string }[] = [];

  for (const file of docFiles) {
    const text = await fs.promises.readFile(file, "utf-8");
    files.push({ path: path.relative(DOCS_DIR, file), text });
  }

  for (const file of codeFiles) {
    const text = await fs.promises.readFile(file, "utf-8");
    files.push({ path: path.relative(path.resolve(__dirname, "..", "..", "strider"), file), text });
  }

  return files;
}

function buildDocChunks(docs: { path: string; text: string }[]): DocChunk[] {
  const chunks: DocChunk[] = [];

  for (const doc of docs) {
    const normalized = normalizeText(doc.text);
    const sections = normalized.split(/\n##?\s+/g); // split by headings

    for (let i = 0; i < sections.length; i++) {
      const text = sections[i].trim();
      if (!text) continue;
      const source = `docs/${doc.path}`;
      const id = `${source}#section_${i}`;

      const tokens = tokenize(text);
      if (tokens.length === 0) continue;

      const tf = buildTF(tokens);
      chunks.push({ id, source, text, tokens, vector: tf });
    }
  }

  return chunks;
}

function calcIdf(chunks: DocChunk[]): Record<string, number> {
  const df: Record<string, number> = {};
  for (const chunk of chunks) {
    const unique = new Set(chunk.tokens);
    for (const term of unique) {
      df[term] = (df[term] || 0) + 1;
    }
  }
  const N = chunks.length || 1;
  const idf: Record<string, number> = {};
  for (const term of Object.keys(df)) {
    idf[term] = Math.log((N + 1) / (df[term] + 1)) + 1;
  }
  return idf;
}

function applyIdf(chunks: DocChunk[], idf: Record<string, number>): void {
  for (const chunk of chunks) {
    const tfidf: Record<string, number> = {};
    for (const term of Object.keys(chunk.vector)) {
      tfidf[term] = chunk.vector[term] * (idf[term] || 0);
    }
    chunk.vector = tfidf;
  }
}

export function cosineSimilarity(a: Record<string, number>, b: Record<string, number>): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (const key of Object.keys(a)) {
    dot += a[key] * (b[key] || 0);
    normA += a[key] * a[key];
  }
  for (const key of Object.keys(b)) {
    normB += b[key] * b[key];
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

export async function createIndex(): Promise<IndexData> {
  const docs = await loadDocsAndCode();
  const chunks = buildDocChunks(docs);
  const idf = calcIdf(chunks);
  applyIdf(chunks, idf);

  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  const index: IndexData = { chunks, idf };
  await fs.promises.writeFile(INDEX_FILE, JSON.stringify(index, null, 2), "utf-8");
  return index;
}

export async function loadIndex(): Promise<IndexData> {
  if (!fs.existsSync(INDEX_FILE)) {
    return createIndex();
  }
  const raw = await fs.promises.readFile(INDEX_FILE, "utf-8");
  const index: IndexData = JSON.parse(raw);
  return index;
}

export function buildQueryVector(query: string, idf: Record<string, number>): Record<string, number> {
  const tokens = tokenize(normalizeText(query));
  const tf = buildTF(tokens);
  const vector: Record<string, number> = {};
  for (const term of Object.keys(tf)) {
    vector[term] = tf[term] * (idf[term] || Math.log(2));
  }
  return vector;
}

if (require.main === module) {
  createIndex()
    .then(() => {
      console.log("Index created successfully.");
    })
    .catch((err) => {
      console.error("Failed to create index:", err);
      process.exit(1);
    });
}
