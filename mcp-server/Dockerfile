# Dockerfile para MCP Server independente
FROM node:20-alpine AS builder

WORKDIR /app

# Copia package e tsconfig do diretório do mcp-server (root dir = mcp-server)
COPY package.json ./
COPY package-lock.json* ./
COPY tsconfig.json ./

# Copia código fonte
COPY src ./src

# Instala dependências (prepare rodará a build com src disponível)
RUN npm ci

# Build TypeScript (fallback caso prepare não execute)
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
