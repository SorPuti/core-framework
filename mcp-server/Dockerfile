# Dockerfile para MCP Server independente
FROM node:20-alpine AS builder

WORKDIR /app

# Copia package e tsconfig do diretório do mcp-server (root dir = mcp-server)
COPY package.json ./
COPY package-lock.json* ./
COPY tsconfig.json ./

# Copia código fonte
COPY src ./src

# Se não houver docs/strider no contexto (root_dir=mcp-server), baixa do GitHub
RUN if [ ! -d /app/docs ] || [ ! -d /app/strider ]; then \
  apk add --no-cache git && \
  git clone --depth 1 https://github.com/SorPuti/core-framework.git /tmp/core-framework && \
  cp -R /tmp/core-framework/docs /app/docs && \
  cp -R /tmp/core-framework/strider /app/strider && \
  rm -rf /tmp/core-framework && \
  apk del git; \
  fi

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
COPY --from=builder /app/docs ./docs
COPY --from=builder /app/strider ./strider

EXPOSE 8001

ENV NODE_ENV=production
ENV DOCS_ROOT=/app/docs
ENV DATA_DIR=/app/data
CMD ["node", "dist/mcp.js"]
