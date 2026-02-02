# DateTime

Utilitarios para manipulacao de datas e timezones. Garante consistencia no tratamento de datas em toda a aplicacao.

## Configuracao

```python
# src/main.py
from core.datetime import configure_datetime

configure_datetime(
    # Timezone padrao para exibicao
    default_timezone="America/Sao_Paulo",
    
    # Se True, todos os datetimes sao "aware" (com timezone)
    # Se False, datetimes sao "naive" (sem timezone)
    use_tz=True,
)
```

Alternativa via .env:

```env
TIMEZONE=America/Sao_Paulo
USE_TZ=true
```

**Recomendacao**: Sempre use `USE_TZ=true` em producao. Datetimes naive causam bugs sutis em aplicacoes com usuarios em fusos diferentes.

## Uso Basico

```python
from core.datetime import timezone, DateTime

# Datetime atual com timezone configurado
now = timezone.now()

# Data atual (sem horario)
today = timezone.today()

# Criar datetime especifico (aware se USE_TZ=true)
dt = DateTime(2026, 2, 1, 12, 0, 0)

# Converter para outro timezone
dt_sp = timezone.localtime(dt, "America/Sao_Paulo")
dt_utc = timezone.localtime(dt, "UTC")
```

## Funcoes do timezone

```python
from core.datetime import timezone

# Datetime atual
now = timezone.now()

# Data atual
today = timezone.today()

# Converter datetime para timezone especifico
local = timezone.localtime(dt, "America/Sao_Paulo")

# Tornar datetime naive em aware
# Assume que o datetime naive esta no timezone especificado
aware = timezone.make_aware(naive_dt, "America/Sao_Paulo")

# Tornar datetime aware em naive
# Remove informacao de timezone
naive = timezone.make_naive(aware_dt)

# Verificar se datetime e aware
is_aware = timezone.is_aware(dt)  # True se tem timezone
```

## Classe DateTime

Wrapper sobre `datetime.datetime` com metodos de conveniencia.

```python
from core.datetime import DateTime

# Construtor - cria datetime aware se USE_TZ=true
dt = DateTime(2026, 2, 1, 12, 0, 0)

# Datetime atual
dt = DateTime.now()

# Datetime atual em UTC
dt = DateTime.utcnow()

# Parse de string ISO
dt = DateTime.fromisoformat("2026-02-01T12:00:00-03:00")

# De timestamp Unix
dt = DateTime.fromtimestamp(1706792400)
```

## Uso em Models

```python
from core import Model
from core.datetime import DateTime
from sqlalchemy.orm import Mapped, mapped_column

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    
    # default= executa funcao ao criar registro
    created_at: Mapped[DateTime] = mapped_column(default=DateTime.now)
    
    # onupdate= executa funcao ao atualizar registro
    updated_at: Mapped[DateTime | None] = mapped_column(
        default=None,
        onupdate=DateTime.now,
    )
    
    # Campo nullable para data futura
    published_at: Mapped[DateTime | None] = mapped_column(default=None)
```

**Nota sobre default**: `default=DateTime.now` (sem parenteses) passa a funcao. `default=DateTime.now()` (com parenteses) passaria o valor no momento da definicao da classe.

## Formatacao

```python
from core.datetime import timezone

now = timezone.now()

# ISO 8601 - padrao para APIs
iso = now.isoformat()  # "2026-02-01T12:00:00-03:00"

# Formato customizado
formatted = now.strftime("%d/%m/%Y %H:%M")  # "01/02/2026 12:00"

# Formato brasileiro
br = now.strftime("%d/%m/%Y")  # "01/02/2026"

# Formato americano
us = now.strftime("%m/%d/%Y")  # "02/01/2026"
```

## Aritmetica de Datas

```python
from core.datetime import timezone
from datetime import timedelta

now = timezone.now()

# Adicionar tempo
tomorrow = now + timedelta(days=1)
next_week = now + timedelta(weeks=1)
in_2_hours = now + timedelta(hours=2)

# Subtrair tempo
yesterday = now - timedelta(days=1)
last_month = now - timedelta(days=30)

# Diferenca entre datas
diff = now - post.created_at  # Retorna timedelta
days_old = diff.days
```

## Comparacoes

```python
from core.datetime import timezone
from datetime import timedelta

now = timezone.now()

# Comparar datas
if post.created_at < now - timedelta(days=30):
    print("Post tem mais de 30 dias")

# Verificar se e hoje
if post.created_at.date() == timezone.today():
    print("Post criado hoje")

# Verificar se esta no futuro
if post.published_at and post.published_at > now:
    print("Post agendado para o futuro")
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

# Posts nao publicados (published_at no futuro ou NULL)
from sqlalchemy import or_
posts = await Post.objects.using(db).filter(
    or_(
        Post.published_at.is_(None),
        Post.published_at > now,
    )
).all()
```

## Timezones Comuns

| Timezone | Descricao | Offset |
|----------|-----------|--------|
| `UTC` | Coordinated Universal Time | +00:00 |
| `America/Sao_Paulo` | Brasilia | -03:00 |
| `America/New_York` | Eastern Time | -05:00/-04:00 |
| `Europe/London` | GMT/BST | +00:00/+01:00 |
| `Asia/Tokyo` | Japan Standard Time | +09:00 |

**Nota sobre DST**: Alguns timezones tem horario de verao. O offset muda automaticamente.

## Boas Praticas

### Armazene em UTC

```python
# Ao salvar no banco, use UTC
# O framework faz isso automaticamente se USE_TZ=true
post.created_at = timezone.now()
```

### Converta para Local na Exibicao

```python
# Ao exibir para usuario, converta para timezone local
local_time = timezone.localtime(post.created_at, "America/Sao_Paulo")
```

### Use timezone.now() ao inves de datetime.now()

```python
# ERRADO - datetime naive, sem timezone
from datetime import datetime
now = datetime.now()

# CORRETO - datetime aware, com timezone
from core.datetime import timezone
now = timezone.now()
```

### Configure Timezone no Inicio

```python
# src/main.py
from core.datetime import configure_datetime

# Primeira coisa no main.py
configure_datetime(
    default_timezone="America/Sao_Paulo",
    use_tz=True,
)
```

**Por que UTC no banco**: Evita ambiguidade. Quando usuario em SP e usuario em NY acessam o mesmo registro, ambos veem a data correta convertida para seu timezone local.
