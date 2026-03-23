import express, { Request, Response } from "express";
import cors from "cors";

import { createIndex, loadIndex, IndexData } from "./indexer";
import { queryIndex } from "./query";

const DOCS_ROOT = process.env.DOCS_ROOT || "../docs"; // path based on project root

const app = express();
app.use(cors());
app.use(express.json({ limit: "1mb" }));

let indexData: IndexData | null = null;

async function initialize(): Promise<void> {
  try {
    indexData = await loadIndex();
  } catch (err) {
    console.warn("Index not found or failed to load, building index...");
    indexData = await createIndex();
  }
  console.info(`MCP index loaded: ${indexData.chunks.length} chunks`);
}

app.get("/status", async (req: Request, res: Response) => {
  res.json({
    status: "ready",
    docs_root: process.env.DOCS_ROOT || DOCS_ROOT,
    indexed_chunks: indexData?.chunks.length ?? 0,
    available: Boolean(indexData),
  });
});

app.post("/query", async (req: Request, res: Response) => {
  if (!indexData) {
    return res.status(503).json({ error: "Index not initialized" });
  }

  const question = (req.body?.question || "").toString().trim();
  if (!question) {
    return res.status(400).json({ error: "question is required" });
  }

  const results = queryIndex(indexData, question, 5);

  if (results.length === 0) {
    return res.status(404).json({
      answer: "Nenhuma correspondência encontrada no índice de documentação.",
      sources: [],
    });
  }

  return res.json({
    question,
    answers: results.map((hit) => ({
      score: hit.score,
      source: hit.chunk.source,
      text: hit.chunk.text.slice(0, 1200),
    })),
  });
});

const PORT = Number(process.env.PORT || 8001);

initialize()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`MCP server running on http://localhost:${PORT}`);
    });
  })
  .catch((err) => {
    console.error("Failed to initialize MCP server:", err);
    process.exit(1);
  });

export default app;
