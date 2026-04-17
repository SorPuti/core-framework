# Citus (PostgreSQL distribuído)

[Citus](https://www.citusdata.com/overview/) é uma extensão open source que mantém **PostgreSQL** como motor e permite **escalar horizontalmente**: sharding por linha, *schema-based sharding* (a partir do Citus 12, útil para multi-tenant SaaS), consultas paralelas em cluster, tabelas de referência, rebalanceamento de shards, etc.

O Strider **não substitui** o Citus nem exige fork de ORM: a aplicação usa a mesma stack **SQLAlchemy 2 async + asyncpg**. O **coordinator** Citus expõe uma URL PostgreSQL normal — configure `DATABASE_URL` apontando para ele.

## O que o framework faz

| Recurso | Descrição |
|--------|-----------|
| `database_citus_application_name` | Opcional: define `application_name` no asyncpg (`server_settings`) para correlacionar sessões em `pg_stat_activity` e monitoração em cluster. |
| `database_citus_probe_on_startup` | Se `True`, após conectar executa um probe em `pg_extension` por `citus` e registra a versão ou ausência. |
| `database_citus_require` | Se `True`, a subida **falha** se o banco for PostgreSQL **sem** a extensão `citus` (útil para garantir ambiente Hyperscale/Citus em produção). |

API Python (health checks manuais, scripts):

```python
from sqlalchemy.ext.asyncio import create_async_engine
from strider.citus import probe_citus_on_engine, CitusStatus

engine = create_async_engine("postgresql+asyncpg://...")
status: CitusStatus = await probe_citus_on_engine(engine)
```

Constante `CITUS_OVERVIEW_URL` aponta para a visão geral oficial.

## Variáveis de ambiente (.env)

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@citus-coordinator:5432/mydb

# Opcional — observabilidade
DATABASE_CITUS_APPLICATION_NAME=my-api-production

# Log na subida se Citus está presente
DATABASE_CITUS_PROBE_ON_STARTUP=true

# Falha na subida se não houver extensão citus (PostgreSQL apenas)
DATABASE_CITUS_REQUIRE=false
```

## Réplicas de leitura + Citus

O modo [`database_read_url`](21-replicas.md) do Strider separa **write** e **read** em URLs distintas. Em um cluster Citus gerenciado, leituras e escritos costumam passar pelo **coordinator** (ou seguir o desenho do provedor). Antes de apontar `DATABASE_READ_URL` para um nó diferente do coordinator, valide com a documentação do seu provedor (latência, consistência, roteamento de consultas distribuídas).

## Modelagem de dados (fora do framework)

Definir **coluna de distribuição**, `create_distributed_table`, *schema-based sharding*, tabelas de referência e migrações Citus continua responsabilidade do **DDL/migrations** e da equipe de dados. Para apps multi-tenant, alinhar a chave de shard com o campo usado em [`tenancy_field`](32-tenancy.md) costuma simplificar filtros e co-localização.

## Referência

- [Citus Open Source Overview](https://www.citusdata.com/overview/)
