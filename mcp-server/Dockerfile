# Dockerfile para MCP Server independente
FROM node:20-alpine AS builder

ARG APP_DIR=.
WORKDIR /app

# Copia package e tsconfig (suporta context root mcp-server ou repo root com build-arg)
COPY ${APP_DIR}/package.json ./
COPY ${APP_DIR}/package-lock.json* ./
COPY ${APP_DIR}/tsconfig.json ./

# Instala dependências
RUN npm ci

# Copia código fonte
COPY ${APP_DIR}/src ./src

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
