# Dockerfile para MCP Server independente (root repo)
FROM node:20-alpine AS builder

WORKDIR /app

# Copia package e tsconfig da pasta mcp-server
COPY mcp-server/package.json ./
COPY mcp-server/package-lock.json* ./
COPY mcp-server/tsconfig.json ./

# Copia código fonte e documentação (para indexação)
COPY mcp-server/src ./src
COPY docs ./docs
COPY strider ./strider

# Instala dependências
RUN npm ci

# Build TypeScript
RUN npm run build

# Runtime image
FROM node:20-alpine AS runtime
WORKDIR /app

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/docs ./docs
COPY --from=builder /app/strider ./strider

EXPOSE 8001

ENV NODE_ENV=production
ENV DOCS_ROOT=/app/docs
ENV DATA_DIR=/app/data
CMD ["node", "dist/server.js"]
