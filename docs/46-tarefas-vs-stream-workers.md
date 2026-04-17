# Tarefas (`@task`) vs stream workers (`@worker`)

No Strider existem **dois mecanismos distintos**. O nome “worker” aparece nos dois contextos, o que gera confusão. Este guia define **um caminho por tipo** e os comandos corretos.

## Resumo rápido

| | **Tarefas em background** | **Stream worker (mensagens)** |
|---|---------------------------|-------------------------------|
| **Objetivo** | Jobs enfileirados (`delay`), retries, filas nomeadas | Consumir **tópico** Kafka (ou broker configurado), pipelines de eventos |
| **Decorator / API** | `from strider.tasks import task` → `@task(queue="...")` | `from strider.messaging import worker` → `@worker(topic="...")` |
| **Registro** | `strider.tasks.registry` (ao importar o módulo) | `strider.messaging.workers` (subclasse `Worker` ou `@worker`) |
| **Arquivo sugerido** | `src/tasks.py` ou `src/apps/<app>/tasks.py` | `src/workers.py` ou módulo em `workers_module` |
| **CLI para executar processo** | `strider worker` (consome `tasks.<fila>`) | `strider runworker <Nome>` ou `strider runworker all` |
| **Listar o que registrou** | `strider tasks` | `strider workers` |
| **Agendamento** | `strider scheduler` + `@periodic_task` | Não é o mesmo sistema; use cron externo ou lógica no tópico |

**Regra mnemônica:** se você usou **`@task`**, o processo é **`strider worker`**. Se usou **`@worker` do `strider.messaging`**, o processo é **`strider runworker`**.

## Validação no registo (import do módulo)

Não são dois “mundos” com regras diferentes: **o mesmo contrato** é validado ao registar.

- **Stream workers** (`@worker` ou subclasse de `Worker`): validação em `WorkerRegistrationError` — `input_topic` obrigatório, nomes de tópico estilo Kafka, **proibido** prefixo `tasks.` (reservado a `strider.tasks`), `group_id` não vazio, `concurrency` / `batch_*` / retry coerentes. Classe `Worker` **sem** `input_topic` não regista (base intermédia; ver aviso em log).
- **Tarefas** (`@task` / `@periodic_task`): `TaskRegistrationError` — fila com nome seguro para `tasks.<queue>`, nomes únicos entre task e periodic, `timeout` ≥ 1, etc.

Se o módulo falha ao importar, leia a mensagem da exceção — costuma indicar colisão de nome ou tópico inválido.

## Checklist — “não está registrando”

### Tarefas (`@task`)

1. A função está decorada com **`@task`** (import de **`strider.tasks`**, não de `strider.messaging`)?
2. O módulo onde ela está definido **é importado antes** de subir o worker? O `strider worker` passa a usar a mesma descoberta que `strider tasks` (`tasks_module`, `tasks.py`, `src/**/tasks.py`, `app_module`).
3. Rodou `strider tasks` e aparece a task na lista?
4. `task_enabled` e Kafka (ou broker de tasks) estão coerentes com [Workers e tarefas](31-workers.md)?

### Stream workers (`@worker` / `Worker`)

1. Usa **`from strider.messaging import worker, Worker`**?
2. O arquivo está em padrão descoberto por **`strider runworker`** (ex.: `workers.py`, `src/workers.py`) ou em `workers_module` no settings?
3. Rodou `strider workers` e aparece o nome da classe ou do handler?

## Evite

- Nomear tópico Kafka **`tasks`** para stream worker se você já usa o sistema de **tópicos `tasks.<fila>`** das tarefas em background — prefira nomes como `billing-events`, `imports-jobs`, etc.
- Colocar `@worker` (messaging) no mesmo arquivo que `@task` sem comentar qual CLI sobe cada coisa — pode funcionar, mas separar `tasks.py` e `workers.py` deixa o deploy mais claro.

## Documentação relacionada

- [Workers e configuração detalhada](31-workers.md) — settings, exemplos de `Worker` em classe, batch, DLQ
- [Messaging](30-messaging.md) — publicação, tópicos, brokers
