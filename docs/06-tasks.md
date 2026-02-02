# Background Tasks

Sistema de execucao de tarefas assincronas. Tarefas sao enfileiradas e processadas por workers separados do processo da API.

## Definir Tarefa

Tarefas sao funcoes async decoradas com `@task`. O decorator registra a funcao no sistema de filas.

```python
# src/apps/reports/tasks.py
from core.tasks import task

@task(queue="default")
async def generate_report(user_id: int, report_type: str):
    """
    Tarefa executada em background por um worker.
    
    queue="default": Nome da fila. Workers escutam filas especificas.
    Use filas diferentes para prioridades diferentes.
    
    Parametros devem ser serializaveis (JSON).
    NAO passe objetos complexos - passe IDs e busque no banco.
    """
    # Processamento pesado que bloquearia a API
    data = await fetch_report_data(user_id, report_type)
    pdf = await create_pdf(data)
    await save_report(user_id, pdf)
    
    # Retorno e armazenado e pode ser consultado (se configurado)
    return {"status": "completed", "user_id": user_id}
```

**Importante sobre parametros**: Tarefas sao serializadas para JSON. Objetos como `datetime`, `Decimal`, ou models SQLAlchemy precisam ser convertidos antes de passar.

## Chamar Tarefa

```python
from src.apps.reports.tasks import generate_report

# .delay() enfileira a tarefa e retorna imediatamente
# A tarefa sera executada por um worker em outro processo
await generate_report.delay(user_id=1, report_type="monthly")

# Com opcoes adicionais
await generate_report.delay(
    user_id=1,
    report_type="monthly",
    countdown=60,  # Aguarda 60 segundos antes de executar
)
```

**Comportamento de .delay()**: Retorna imediatamente apos enfileirar. Nao aguarda execucao. Se precisar do resultado, implemente polling ou webhook.

## Tarefa em ViewSet

Padrao comum: endpoint enfileira tarefa e retorna resposta imediata.

```python
from core import ModelViewSet, action
from .tasks import generate_report

class ReportViewSet(ModelViewSet):
    model = Report
    
    @action(methods=["POST"], detail=False)
    async def generate(self, request, db, **kwargs):
        """
        POST /reports/generate
        
        Enfileira geracao de relatorio e retorna imediatamente.
        Cliente pode consultar status via outro endpoint.
        """
        user = request.state.user
        body = await request.json()
        
        # Enfileira tarefa - nao bloqueia a resposta
        await generate_report.delay(
            user_id=user.id,
            report_type=body["type"],
        )
        
        # Resposta imediata - relatorio sera gerado em background
        return {"message": "Report generation started"}
```

**UX recomendada**: Retorne um ID de job e implemente endpoint para consultar status. Ou use WebSocket/SSE para notificar quando pronto.

## Tarefas Periodicas

Tarefas executadas automaticamente em intervalos definidos.

```python
from core.tasks import periodic_task

@periodic_task(cron="0 0 * * *")  # Sintaxe cron: minuto hora dia mes dia_semana
async def cleanup_old_sessions():
    """
    Executada diariamente a meia-noite.
    
    Tarefas periodicas NAO recebem parametros.
    Precisam obter sessao de banco manualmente.
    """
    from core.models import get_session
    
    # get_session() como context manager garante cleanup
    async with get_session() as db:
        await Session.objects.using(db).filter(
            expired_at__lt=datetime.utcnow()
        ).delete()

@periodic_task(interval=300)  # Intervalo em segundos
async def sync_inventory():
    """
    Executada a cada 5 minutos.
    
    interval= e alternativa a cron para intervalos simples.
    NAO use ambos - cron tem precedencia.
    """
    pass
```

**Cron vs Interval**:
- `cron`: Horarios especificos (ex: "todo dia as 3h")
- `interval`: Frequencia fixa (ex: "a cada 5 minutos")

## Executar Workers

Workers sao processos que consomem tarefas das filas.

```bash
# Worker para fila especifica
core worker --queue default

# Worker para multiplas filas
# Processa de qualquer fila listada
core worker --queue default --queue high-priority

# Worker com concorrencia
# Processa ate 4 tarefas simultaneamente
core worker --queue default --concurrency 4
```

**Concorrencia**: Aumentar concorrencia melhora throughput, mas consome mais memoria. Ajuste baseado nos recursos do servidor.

## Executar Scheduler

O scheduler dispara tarefas periodicas. Deve haver exatamente UMA instancia rodando.

```bash
core scheduler
```

**Cuidado**: Multiplas instancias do scheduler causam execucoes duplicadas. Em ambiente distribuido, use lock distribuido ou garanta instancia unica.

## Opcoes de Tarefa

```python
@task(
    queue="high-priority",  # Fila especifica
    max_retries=3,          # Tentativas em caso de falha
    retry_delay=10,         # Segundos entre tentativas
    timeout=300,            # Tempo maximo de execucao (segundos)
)
async def critical_task(data: dict):
    """
    Tarefa com configuracao completa.
    
    Se exceder timeout, tarefa e cancelada e conta como falha.
    """
    pass
```

| Opcao | Tipo | Padrao | Descricao |
|-------|------|--------|-----------|
| `queue` | str | "default" | Fila onde a tarefa sera enfileirada |
| `max_retries` | int | 0 | Numero de retentativas apos falha |
| `retry_delay` | int | 0 | Segundos entre retentativas |
| `timeout` | int | None | Tempo maximo de execucao |

## Tratamento de Erros

Controle fino sobre quais erros devem acionar retry.

```python
from core.tasks import task, TaskError

@task(queue="default", max_retries=3)
async def risky_task(item_id: int):
    """
    TaskError permite controlar comportamento de retry.
    """
    try:
        result = await external_api.process(item_id)
        return result
        
    except ExternalAPIError as e:
        # retry=True (padrao): Tenta novamente
        # Erros transientes como timeout, rate limit
        raise TaskError(f"API failed: {e}")
        
    except ValidationError as e:
        # retry=False: Falha permanente, nao tenta novamente
        # Erros de dados que nao serao resolvidos com retry
        raise TaskError(f"Invalid data: {e}", retry=False)
```

**Quando usar retry=False**: Erros de validacao, dados invalidos, recursos nao encontrados. Retry so faz sentido para erros transientes.

## Tarefa com Banco de Dados

Tarefas executam em processo separado - nao tem acesso a sessao da API.

```python
@task(queue="default")
async def update_user_stats(user_id: int):
    """
    Tarefas precisam criar propria sessao de banco.
    
    NUNCA passe sessao como parametro - nao e serializavel.
    """
    from core.models import get_session
    
    # Context manager garante que sessao e fechada
    async with get_session() as db:
        user = await User.objects.using(db).get(id=user_id)
        user.login_count += 1
        await user.save(db)
```

## Deploy com Docker

```yaml
services:
  # API HTTP
  api:
    build: .
    command: core run
    
  # Workers processam tarefas
  # replicas: 2 significa 2 containers identicos
  worker:
    build: .
    command: core worker --queue default --concurrency 4
    deploy:
      replicas: 2
    
  # Scheduler dispara tarefas periodicas
  # APENAS UMA instancia
  scheduler:
    build: .
    command: core scheduler
```

**Escalonamento**:
- API: Escale horizontalmente conforme carga HTTP
- Workers: Escale conforme tamanho da fila
- Scheduler: Sempre 1 instancia

---

Proximo: [Deployment](07-deployment.md) - Configuracao completa para producao.
