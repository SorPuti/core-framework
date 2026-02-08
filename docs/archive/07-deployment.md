# Deployment

Configuracao para ambientes de producao. O framework fornece geradores para Docker, Kubernetes e PM2.

## Gerar Arquivos Docker

```bash
core docker generate
```

Arquivos criados:
- `Dockerfile`: Imagem otimizada para producao
- `docker-compose.yml`: Orquestracao completa com dependencias
- `.dockerignore`: Exclui arquivos desnecessarios da imagem

## Estrutura do Docker Compose

O compose gerado inclui todos os servicos necessarios para uma aplicacao completa.

```yaml
services:
  # API HTTP - ponto de entrada para clientes
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      # Variaveis de ambiente sobrescrevem .env
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      # condition: service_healthy aguarda healthcheck passar
      # Evita erros de conexao durante startup
      db:
        condition: service_healthy
      kafka:
        condition: service_healthy

  # Workers processam tarefas em background
  worker:
    build: .
    command: core worker --queue default --concurrency 4
    deploy:
      # replicas cria multiplas instancias para alta disponibilidade
      replicas: 2
    depends_on:
      kafka:
        condition: service_healthy

  # Scheduler dispara tarefas periodicas
  # IMPORTANTE: Apenas 1 instancia para evitar duplicacao
  scheduler:
    build: .
    command: core scheduler
    depends_on:
      kafka:
        condition: service_healthy

  # PostgreSQL com persistencia
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres  # ALTERE em producao
      POSTGRES_DB: app
    volumes:
      # Volume nomeado persiste dados entre restarts
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      # Verifica se Postgres aceita conexoes
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Kafka em modo KRaft (sem Zookeeper)
  kafka:
    image: bitnami/kafka:latest
    environment:
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    healthcheck:
      # Verifica se Kafka responde a comandos
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 10s
      retries: 5

  # Redis para cache e filas
  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Dozzle: visualizador de logs em tempo real
  # Acesse http://localhost:9999
  dozzle:
    image: amir20/dozzle:latest
    ports:
      - "9999:8080"
    volumes:
      # Acesso read-only ao socket Docker
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  # Volume nomeado para persistencia do Postgres
  postgres_data:
```

## Build e Execucao

```bash
# Build das imagens
docker compose build

# Iniciar todos os servicos em background
docker compose up -d

# Acompanhar logs da API
docker compose logs -f api

# Escalar workers conforme demanda
docker compose up -d --scale worker=4
```

**Ordem de startup**: O Docker Compose respeita `depends_on` com `condition: service_healthy`. Servicos so iniciam quando dependencias estao saudaveis.

## Variaveis de Ambiente para Producao

Crie arquivo `.env.production` separado do `.env` de desenvolvimento.

```env
# .env.production

# Aplicacao
APP_NAME=My API
ENVIRONMENT=production
DEBUG=false  # NUNCA true em producao

# Chave secreta - gere com: openssl rand -hex 32
SECRET_KEY=your-production-secret-key-minimum-32-characters

# Banco de dados - credenciais de producao
DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/myapp

# Messaging
KAFKA_BOOTSTRAP_SERVERS=kafka-host:9092
REDIS_URL=redis://redis-host:6379/0

# Auth - tokens mais curtos em producao por seguranca
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=15
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
```

**Seguranca de SECRET_KEY**: Nunca commite em repositorio. Use secrets manager (AWS Secrets Manager, HashiCorp Vault) ou variaveis de ambiente do CI/CD.

## Migracoes em Producao

Migracoes devem ser executadas ANTES de iniciar a aplicacao.

```bash
# Opcao 1: Comando manual antes do deploy
docker compose run --rm api core migrate

# Opcao 2: Entrypoint script
```

Entrypoint recomendado:

```bash
#!/bin/sh
# entrypoint.sh

set -e  # Falha se qualquer comando falhar

echo "Running migrations..."
core migrate

echo "Starting application..."
exec "$@"  # Executa comando passado (core run)
```

No Dockerfile:

```dockerfile
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["core", "run"]
```

## Health Checks

O framework expoe endpoint `/health` automaticamente.

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production"
}
```

Use para:
- Load balancer health checks
- Kubernetes liveness/readiness probes
- Monitoramento externo

## Kubernetes

```bash
core k8s generate
```

Arquivos gerados em `k8s/`:
- `deployment.yaml`: Pods da aplicacao
- `service.yaml`: Exposicao de rede
- `configmap.yaml`: Configuracoes nao-sensiveis
- `secrets.yaml`: Template para secrets (preencha manualmente)

**Nota**: O gerador cria templates basicos. Ajuste replicas, resources e probes conforme sua infraestrutura.

## PM2 (Alternativa a Docker)

Para deploy em VMs sem containers.

```bash
core pm2 generate
```

Gera `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [
    {
      name: "api",
      script: "core",
      args: "run --host 0.0.0.0 --port 8000",
      // "max" usa todos os CPUs disponiveis
      instances: "max",
      exec_mode: "cluster",
    },
    {
      name: "worker",
      script: "core",
      args: "worker --queue default",
      instances: 2,
    },
    {
      name: "scheduler",
      script: "core",
      args: "scheduler",
      instances: 1,  # Sempre 1
    },
  ],
};
```

Comandos PM2:

```bash
pm2 start ecosystem.config.js
pm2 status
pm2 logs
pm2 reload all  # Zero-downtime restart
```

## Visualizador de Logs

Dozzle esta incluido no compose padrao em `http://localhost:9999`.

Funcionalidades:
- Logs em tempo real de todos os containers
- Filtro por container
- Busca em logs
- Visualizacao agregada

**Producao**: Considere substituir Dozzle por solucao de log aggregation (ELK, Loki, CloudWatch).

## Checklist de Producao

Antes de ir para producao, verifique:

**Seguranca**:
- [ ] `DEBUG=false`
- [ ] `SECRET_KEY` forte e unico
- [ ] Credenciais de banco seguras
- [ ] SSL/TLS configurado (HTTPS)
- [ ] CORS restrito a dominios permitidos

**Infraestrutura**:
- [ ] Healthchecks configurados
- [ ] Monitoramento (Prometheus, Grafana, etc)
- [ ] Agregacao de logs
- [ ] Backups de banco automatizados
- [ ] Rate limiting configurado

**Aplicacao**:
- [ ] Migracoes testadas
- [ ] Permissoes revisadas
- [ ] Tokens com expiracao adequada
- [ ] Error handling em producao (sem stack traces)

---

Proximo: [Complete Example](08-complete-example.md) - Aplicacao completa de e-commerce.
