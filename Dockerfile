# Dockerfile para MCP Server independente (root repo)
FROM node:20-alpine AS builder

WORKDIR /app

# Copia package e tsconfig da pasta mcp-server
COPY mcp-server/package.json ./
COPY mcp-server/package-lock.json* ./
COPY mcp-server/tsconfig.json ./

# Instala dependências
RUN npm ci

# Copia código fonte
COPY mcp-server/src ./src

# Build TypeScript
RUN npm run build

# Runtime image
FROM node:20-alpine AS runtime
WORKDIR /app

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist

EXPOSE 8001

ENV NODE_ENV=production
CMD ["node", "dist/server.js"]
