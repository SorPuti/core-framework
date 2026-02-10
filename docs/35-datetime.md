# DateTime

Sistema de datetime timezone-aware com configuração plug-and-play. Defina timezone no Settings e tudo é configurado automaticamente.

## Configuração Plug-and-Play

```python
# src/settings.py
class AppSettings(Settings):
    timezone: str = "America/Sao_Paulo"  # Timezone padrão
    use_tz: bool = True                   # Usar datetimes aware
    datetime_format: str = "%Y-%m-%dT%H:%M:%S%z"
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M:%S"
```

**Zero configuração explícita**: Você NÃO precisa chamar `configure_datetime()`. O sistema é auto-configurado no startup.

```python
# Verificar se DateTime foi configurado
from core.config import is_datetime_configured

if is_datetime_configured():
    print("DateTime pronto!")
```

## Settings de DateTime

| Setting | Tipo | Default | Descrição |
|---------|------|---------|-----------|
| `timezone` | `str` | `"UTC"` | Timezone padrão da aplicação |
| `use_tz` | `bool` | `True` | Usar datetimes aware (com timezone) |
| `datetime_format` | `str` | `"%Y-%m-%dT%H:%M:%S%z"` | Formato padrão de datetime |
| `date_format` | `str` | `"%Y-%m-%d"` | Formato padrão de data |
| `time_format` | `str` | `"%H:%M:%S"` | Formato padrão de hora |

## API timezone (Django-style)

### Tempo Atual

```python
from core.datetime import timezone

# Datetime atual em UTC
now = timezone.now()

# Datetime atual em timezone específico
now_sp = timezone.now("America/Sao_Paulo")

# Datetime UTC (explícito)
utc_now = timezone.utcnow()

# Data atual
today = timezone.today()
```

### Conversão de Timezone

```python
from core.datetime import timezone

dt = timezone.now()

# Converter para timezone
local = timezone.localtime(dt, "America/Sao_Paulo")

# Converter para UTC
utc = timezone.make_aware(naive_dt, "UTC")
```

### Gerenciamento de Timezone

```python
from core.datetime import timezone

# Definir timezone padrão (thread-local)
timezone.activate("America/Sao_Paulo")

# Resetar para UTC
timezone.deactivate()

# Obter timezone atual
tz = timezone.get_current_timezone()
```

### Verificar Aware/Naive

```python
from core.datetime import timezone

timezone.is_aware(dt)   # True se tem timezone
timezone.is_naive(dt)   # True se não tem timezone

# Tornar aware
aware_dt = timezone.make_aware(naive_dt, "UTC")

# Tornar naive
naive_dt = timezone.make_naive(aware_dt)
```

### Comparações

```python
from core.datetime import timezone

timezone.is_past(dt)       # True se antes de agora
timezone.is_future(dt)     # True se depois de agora
timezone.is_today(dt)      # True se mesmo dia
timezone.is_yesterday(dt)  # True se ontem
timezone.is_tomorrow(dt)   # True se amanhã
```

### Formatação

```python
from core.datetime import timezone

# Formatar datetime
formatted = timezone.format(dt, "%Y-%m-%d %H:%M:%S")

# Parse de string
dt = timezone.parse("2024-01-15 10:30:00", "%Y-%m-%d %H:%M:%S")
```

### Cálculos

```python
from core.datetime import timezone

# Adicionar tempo
future = timezone.add(dt, days=7, hours=3)

# Subtrair tempo
past = timezone.subtract(dt, days=30)

# Diferença
seconds = timezone.diff(dt1, dt2, unit="seconds")
minutes = timezone.diff(dt1, dt2, unit="minutes")
hours = timezone.diff(dt1, dt2, unit="hours")
days = timezone.diff(dt1, dt2, unit="days")
```

### Helpers de Range

```python
from core.datetime import timezone

# Início/fim do dia
start = timezone.start_of_day(dt)
end = timezone.end_of_day(dt)

# Início/fim do mês
start = timezone.start_of_month(dt)
end = timezone.end_of_month(dt)

# Início/fim do ano
start = timezone.start_of_year(dt)
end = timezone.end_of_year(dt)
```

### Criar DateTime

```python
from core.datetime import timezone

# Criar datetime
dt = timezone.datetime(2024, 1, 15, 10, 30, 0, tz="UTC")

# De timestamp
dt = timezone.from_timestamp(1705315800)

# De string ISO
dt = timezone.from_iso("2024-01-15T10:30:00Z")
```

## Classe DateTime

Subclasse customizada de datetime.

```python
from core.datetime import DateTime

# Criar
dt = DateTime.now()
dt = DateTime.from_timestamp(1705315800)
dt = DateTime.from_iso("2024-01-15T10:30:00Z")

# Converter
dt.to_timezone("America/Sao_Paulo")
dt.to_utc()
dt.to_iso()
dt.to_timestamp()
```

## Em Models

### Auto Timestamps

```python
from core import Model, Field
from core.datetime import DateTime
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    # Definido apenas no INSERT
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    
    # Definido no INSERT e UPDATE
    updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
    
    # Datetime opcional
    published_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
```

### Armazenamento

Todos os datetimes são armazenados em UTC:

| Banco | Tipo |
|-------|------|
| PostgreSQL | `TIMESTAMP WITH TIME ZONE` |
| SQLite | `DATETIME` |
| MySQL | `DATETIME` |

## Queries

```python
from core.datetime import timezone

# Filtrar por data
posts = await Post.objects.using(db).filter(
    created_at__gte=timezone.start_of_day(),
    created_at__lt=timezone.end_of_day(),
).all()

# Filtrar por range
start = timezone.datetime(2024, 1, 1)
end = timezone.datetime(2024, 12, 31)
posts = await Post.objects.using(db).filter(
    created_at__range=(start, end)
).all()
```

## Funções Standalone

```python
from core.datetime import (
    now,
    utcnow,
    today,
    make_aware,
    make_naive,
    is_aware,
    is_naive,
    format_datetime,
    parse_datetime,
    add_days,
    add_hours,
    diff_days,
    start_of_day,
    end_of_day,
)

# Uso
current = now()
formatted = format_datetime(current, "%Y-%m-%d")
tomorrow = add_days(current, 1)
```

## Nomes de Timezone

Formatos suportados:

```python
# Nomes padrão
timezone.now("UTC")
timezone.now("America/Sao_Paulo")
timezone.now("Europe/London")

# Strings de offset
timezone.now("+03:00")
timezone.now("-05:00")
```

## Boas Práticas

### 1. Sempre use UTC para armazenamento

```python
# Bom
created_at = timezone.now()  # UTC

# Ruim
created_at = datetime.now()  # Hora local
```

### 2. Converta apenas para exibição

```python
# Armazene em UTC
post.created_at = timezone.now()

# Converta para exibição ao usuário
local_time = timezone.localtime(post.created_at, user.timezone)
```

### 3. Use auto timestamps

```python
# Bom
created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)

# Evite definição manual
```

### 4. Sempre use datetimes aware

```python
# Bom
dt = timezone.now()

# Ruim
dt = datetime.utcnow()  # Datetime naive
```

## Próximos Passos

- [Fields](10-fields.md) — Tipos de campos
- [Models](03-models.md) — Básico de models
- [Settings](02-settings.md) — Todas as configurações
