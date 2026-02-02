# DateTime

Utilitarios para manipulacao de datas e timezones.

## Configuracao

```python
# src/main.py
from core.datetime import configure_datetime

configure_datetime(
    default_timezone="America/Sao_Paulo",
    use_tz=True,  # Usar datetimes aware
)
```

Ou via .env:

```env
TIMEZONE=America/Sao_Paulo
USE_TZ=true
```

## Uso Basico

```python
from core.datetime import timezone, DateTime

# Agora (com timezone)
now = timezone.now()

# Hoje
today = timezone.today()

# Criar datetime aware
dt = DateTime(2026, 2, 1, 12, 0, 0)

# Converter para timezone
dt_sp = timezone.localtime(dt, "America/Sao_Paulo")
dt_utc = timezone.localtime(dt, "UTC")
```

## Funcoes Disponiveis

### timezone

```python
from core.datetime import timezone

# Agora
now = timezone.now()

# Hoje
today = timezone.today()

# Converter para timezone
local = timezone.localtime(dt, "America/Sao_Paulo")

# Tornar aware
aware = timezone.make_aware(naive_dt, "America/Sao_Paulo")

# Tornar naive
naive = timezone.make_naive(aware_dt)

# Verificar se e aware
is_aware = timezone.is_aware(dt)
```

### DateTime

```python
from core.datetime import DateTime

# Criar
dt = DateTime(2026, 2, 1, 12, 0, 0)

# Agora
dt = DateTime.now()

# UTC
dt = DateTime.utcnow()

# De string
dt = DateTime.fromisoformat("2026-02-01T12:00:00-03:00")

# De timestamp
dt = DateTime.fromtimestamp(1706792400)
```

## No Model

```python
from core import Model
from core.datetime import DateTime
from sqlalchemy.orm import Mapped, mapped_column

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    
    # Campos de data
    created_at: Mapped[DateTime] = mapped_column(default=DateTime.now)
    updated_at: Mapped[DateTime | None] = mapped_column(
        default=None,
        onupdate=DateTime.now,
    )
    published_at: Mapped[DateTime | None] = mapped_column(default=None)
```

## Formatacao

```python
from core.datetime import timezone

now = timezone.now()

# ISO format
iso = now.isoformat()  # "2026-02-01T12:00:00-03:00"

# Formato customizado
formatted = now.strftime("%d/%m/%Y %H:%M")  # "01/02/2026 12:00"

# Formato brasileiro
br = now.strftime("%d/%m/%Y")  # "01/02/2026"
```

## Comparacoes

```python
from core.datetime import timezone, DateTime
from datetime import timedelta

now = timezone.now()

# Adicionar/subtrair
tomorrow = now + timedelta(days=1)
yesterday = now - timedelta(days=1)
next_week = now + timedelta(weeks=1)

# Comparar
if post.created_at < now - timedelta(days=30):
    print("Post antigo")

# Verificar se e hoje
if post.created_at.date() == timezone.today():
    print("Criado hoje")
```

## Queries com Data

```python
from core.datetime import timezone
from datetime import timedelta

now = timezone.now()
last_week = now - timedelta(days=7)

# Posts da ultima semana
posts = await Post.objects.using(db).filter(
    created_at__gte=last_week
).all()

# Posts de hoje
today_start = timezone.today()
posts = await Post.objects.using(db).filter(
    created_at__gte=today_start
).all()

# Posts entre datas
posts = await Post.objects.using(db).filter(
    created_at__range=(start_date, end_date)
).all()
```

## Timezones Comuns

| Timezone | Descricao |
|----------|-----------|
| `UTC` | Coordinated Universal Time |
| `America/Sao_Paulo` | Brasilia (BRT/BRST) |
| `America/New_York` | Eastern Time |
| `Europe/London` | GMT/BST |
| `Asia/Tokyo` | Japan Standard Time |

## Boas Praticas

1. Sempre armazene em UTC no banco
2. Converta para timezone local apenas na exibicao
3. Use `timezone.now()` ao inves de `datetime.now()`
4. Configure timezone padrao no inicio da aplicacao

```python
# Salvar em UTC
post.created_at = timezone.now()  # Automaticamente UTC se USE_TZ=true

# Exibir em local
local_time = timezone.localtime(post.created_at, "America/Sao_Paulo")
```

## Resumo

1. Configure timezone em `main.py` ou `.env`
2. Use `timezone.now()` para datetime atual
3. Use `DateTime` para criar datetimes
4. Use `timezone.localtime()` para converter
5. Armazene em UTC, exiba em local
