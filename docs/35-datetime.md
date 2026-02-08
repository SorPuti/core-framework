# DateTime

Timezone-aware datetime handling.

## Configuration

```python
# src/settings.py
class AppSettings(Settings):
    timezone: str = "UTC"
    use_tz: bool = True
    datetime_format: str = "%Y-%m-%dT%H:%M:%S%z"
    date_format: str = "%Y-%m-%d"
    time_format: str = "%H:%M:%S"
```

## timezone API

Django-style API for datetime operations.

### Current Time

```python
from core.datetime import timezone

# Current UTC datetime
now = timezone.now()

# Current datetime in specific timezone
now_sp = timezone.now("America/Sao_Paulo")

# Current UTC datetime (explicit)
utc_now = timezone.utcnow()

# Current date
today = timezone.today()
```

### Timezone Conversion

```python
from core.datetime import timezone

dt = timezone.now()

# Convert to timezone
local = timezone.localtime(dt, "America/Sao_Paulo")

# Convert to UTC
utc = timezone.make_aware(naive_dt, "UTC")
```

### Timezone Management

```python
from core.datetime import timezone

# Set default timezone
timezone.activate("America/Sao_Paulo")

# Reset to UTC
timezone.deactivate()

# Get current timezone
tz = timezone.get_current_timezone()
```

### Aware/Naive Check

```python
from core.datetime import timezone

timezone.is_aware(dt)   # True if has timezone
timezone.is_naive(dt)   # True if no timezone

# Make aware
aware_dt = timezone.make_aware(naive_dt, "UTC")

# Make naive
naive_dt = timezone.make_naive(aware_dt)
```

### Comparisons

```python
from core.datetime import timezone

timezone.is_past(dt)       # True if before now
timezone.is_future(dt)     # True if after now
timezone.is_today(dt)      # True if same day
timezone.is_yesterday(dt)  # True if yesterday
timezone.is_tomorrow(dt)   # True if tomorrow
```

### Formatting

```python
from core.datetime import timezone

# Format datetime
formatted = timezone.format(dt, "%Y-%m-%d %H:%M:%S")

# Parse string
dt = timezone.parse("2024-01-15 10:30:00", "%Y-%m-%d %H:%M:%S")
```

### Calculations

```python
from core.datetime import timezone

# Add time
future = timezone.add(dt, days=7, hours=3)

# Subtract time
past = timezone.subtract(dt, days=30)

# Difference
seconds = timezone.diff(dt1, dt2, unit="seconds")
minutes = timezone.diff(dt1, dt2, unit="minutes")
hours = timezone.diff(dt1, dt2, unit="hours")
days = timezone.diff(dt1, dt2, unit="days")
```

### Range Helpers

```python
from core.datetime import timezone

# Start/end of day
start = timezone.start_of_day(dt)
end = timezone.end_of_day(dt)

# Start/end of month
start = timezone.start_of_month(dt)
end = timezone.end_of_month(dt)

# Start/end of year
start = timezone.start_of_year(dt)
end = timezone.end_of_year(dt)
```

### Create DateTime

```python
from core.datetime import timezone

# Create datetime
dt = timezone.datetime(2024, 1, 15, 10, 30, 0, tz="UTC")

# From timestamp
dt = timezone.from_timestamp(1705315800)

# From ISO string
dt = timezone.from_iso("2024-01-15T10:30:00Z")
```

## DateTime Class

Custom datetime subclass.

```python
from core.datetime import DateTime

# Create
dt = DateTime.now()
dt = DateTime.from_timestamp(1705315800)
dt = DateTime.from_iso("2024-01-15T10:30:00Z")

# Convert
dt.to_timezone("America/Sao_Paulo")
dt.to_utc()
dt.to_iso()
dt.to_timestamp()
```

## In Models

### Auto Timestamps

```python
from core import Model, Field
from core.datetime import DateTime
from sqlalchemy.orm import Mapped

class Post(Model):
    __tablename__ = "posts"
    
    # Set on INSERT only
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    
    # Set on INSERT and UPDATE
    updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
    
    # Optional datetime
    published_at: Mapped[DateTime | None] = Field.datetime(nullable=True)
```

### Storage

All datetimes are stored in UTC:

- PostgreSQL: `TIMESTAMP WITH TIME ZONE`
- SQLite: `DATETIME`
- MySQL: `DATETIME`

## Querying

```python
from core.datetime import timezone

# Filter by date
posts = await Post.objects.using(db).filter(
    created_at__gte=timezone.start_of_day(),
    created_at__lt=timezone.end_of_day(),
).all()

# Filter by range
start = timezone.datetime(2024, 1, 1)
end = timezone.datetime(2024, 12, 31)
posts = await Post.objects.using(db).filter(
    created_at__range=(start, end)
).all()
```

## Standalone Functions

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

# Usage
current = now()
formatted = format_datetime(current, "%Y-%m-%d")
tomorrow = add_days(current, 1)
```

## Timezone Names

Supported formats:

```python
# Standard names
timezone.now("UTC")
timezone.now("America/Sao_Paulo")
timezone.now("Europe/London")

# Offset strings
timezone.now("+03:00")
timezone.now("-05:00")
```

## Best Practices

1. **Always use UTC for storage**
   ```python
   # Good
   created_at = timezone.now()  # UTC
   
   # Bad
   created_at = datetime.now()  # Local time
   ```

2. **Convert for display only**
   ```python
   # Store in UTC
   post.created_at = timezone.now()
   
   # Convert for user display
   local_time = timezone.localtime(post.created_at, user.timezone)
   ```

3. **Use auto timestamps**
   ```python
   # Good
   created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
   
   # Avoid manual setting
   ```

4. **Always use aware datetimes**
   ```python
   # Good
   dt = timezone.now()
   
   # Bad
   dt = datetime.utcnow()  # Naive datetime
   ```

## Next

- [Fields](10-fields.md) — Field types
- [Models](03-models.md) — Model basics
