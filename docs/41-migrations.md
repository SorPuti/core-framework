# Migrations

Database schema management.

## Workflow

```bash
# 1. Edit models
# 2. Generate migration
core makemigrations --name add_posts

# 3. Review migration file
cat migrations/0001_add_posts.py

# 4. Apply migration
core migrate
```

## Commands

```bash
# Create migration from model changes
core makemigrations --name description

# Apply all pending migrations
core migrate

# Show migration status
core showmigrations

# Rollback last migration
core rollback

# Rollback to specific migration
core rollback 0002

# Preview without applying
core migrate --dry-run
```

## Migration File

Generated in `migrations/`:

```python
# migrations/0001_add_posts.py
from core.migrations import Migration, CreateTable, ColumnDef

class Migration(Migration):
    dependencies = []
    
    operations = [
        CreateTable(
            table_name="posts",
            columns=[
                ColumnDef(name="id", type="INTEGER", primary_key=True),
                ColumnDef(name="title", type="VARCHAR(200)", nullable=False),
                ColumnDef(name="content", type="TEXT", nullable=False),
                ColumnDef(name="published", type="BOOLEAN", default=False),
            ],
        ),
    ]
```

## Operations

| Operation | Description |
|-----------|-------------|
| `CreateTable` | Create new table |
| `DropTable` | Drop table |
| `AddColumn` | Add column |
| `DropColumn` | Remove column |
| `AlterColumn` | Modify column |
| `RenameColumn` | Rename column |
| `CreateIndex` | Create index |
| `DropIndex` | Drop index |

## Manual Migration

```python
# migrations/0002_custom.py
from core.migrations import Migration, AddColumn, ColumnDef

class Migration(Migration):
    dependencies = ["0001_add_posts"]
    
    operations = [
        AddColumn(
            table_name="posts",
            column=ColumnDef(
                name="views",
                type="INTEGER",
                default=0,
            ),
        ),
    ]
```

## Empty Migration

For custom SQL:

```bash
core makemigrations --name custom_sql --empty
```

```python
# migrations/0003_custom_sql.py
from core.migrations import Migration, RunSQL

class Migration(Migration):
    dependencies = ["0002_custom"]
    
    operations = [
        RunSQL(
            forward="CREATE INDEX idx_posts_title ON posts(title)",
            backward="DROP INDEX idx_posts_title",
        ),
    ]
```

## Best Practices

1. **One change per migration** — easier to rollback
2. **Descriptive names** — `add_posts`, `add_user_avatar`, `remove_legacy_field`
3. **Review before applying** — check generated SQL
4. **Test rollback** — ensure backward migration works
5. **Don't edit applied migrations** — create new ones instead

## Troubleshooting

### Migration not detecting changes

```bash
# Ensure models are imported in barrel file
# src/apps/models.py
from src.apps.posts.models import Post  # noqa
```

### Column already exists

```bash
# Skip problematic migration
core migrate --fake 0001
```

### Reset migrations (dev only)

```bash
# Delete migration files
rm -rf migrations/*.py

# Reset database
core reset_db --yes

# Start fresh
core makemigrations --name initial
core migrate
```

## Next

- [Models](03-models.md) — Model definitions
- [CLI](07-cli.md) — All commands
