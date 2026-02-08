# Admin Panel

O Admin Panel e um componente nativo do core-framework que gera automaticamente uma interface de gestao para todos os models registrados. Inspirado no Django Admin, mas construido com FastAPI, SQLAlchemy 2.0 async, Jinja2 + HTMX.

## Ativacao

O admin vem habilitado por padrao. Ao iniciar a app, o painel fica disponivel em `/admin` (customizavel).

```python
from core import CoreApp, Settings

class AppSettings(Settings):
    admin_enabled: bool = True          # default
    admin_url_prefix: str = "/admin"    # customizavel

app = CoreApp(title="My API", settings=AppSettings())
# Admin disponivel em http://localhost:8000/admin
```

Nenhuma configuracao adicional necessaria. O admin descobre models automaticamente.

## Configuracao via Settings

Todos os campos do admin ficam no `Settings` centralizado:

```python
class AppSettings(Settings):
    # Habilitar/desabilitar
    admin_enabled: bool = True
    
    # Rota customizavel (seguranca por obscuridade, convencao interna, etc)
    admin_url_prefix: str = "/admin"
    
    # Visual
    admin_site_title: str = "Admin"          # titulo na aba do browser
    admin_site_header: str = "Core Admin"    # header no sidebar
    admin_theme: str = "default"             # "default" ou "dark"
    admin_logo_url: str | None = None        # URL do logo custom
    admin_primary_color: str = "#3B82F6"     # cor primaria (hex)
    admin_custom_css: str | None = None      # path para CSS extra
```

Ou via `.env`:

```bash
ADMIN_ENABLED=true
ADMIN_URL_PREFIX=/backoffice
ADMIN_SITE_TITLE=Backoffice Acme
ADMIN_SITE_HEADER=Acme Admin
ADMIN_THEME=dark
ADMIN_PRIMARY_COLOR=#10B981
```

### Rota customizavel

O prefixo da URL nao e hardcoded. Util para:

- Seguranca por obscuridade: `ADMIN_URL_PREFIX=/ops-c7a3e1b2`
- Convencao interna: `ADMIN_URL_PREFIX=/internal`
- Multi-admin: prefixos diferentes para sites diferentes

## Registro de Models via admin.py

Crie um arquivo `admin.py` no seu app. O core descobre automaticamente durante o boot.

### Estrutura do projeto

```
myproject/
├── apps/
│   ├── users/
│   │   ├── models.py
│   │   └── admin.py      # ← auto-descoberto
│   └── payments/
│       ├── models.py
│       └── admin.py      # ← auto-descoberto
├── settings.py
└── main.py
```

### Registro basico

```python
# apps/users/admin.py
from core.admin import admin, ModelAdmin

@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ("id", "email", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name")
    list_filter = ("is_active", "is_staff")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "last_login")
    display_name = "Usuario"
    display_name_plural = "Usuarios"
    icon = "users"
```

### Registro com defaults (sem classe custom)

```python
# Registra com configuracao automatica
admin.register(PaymentLog)
```

### Registro funcional (com admin class)

```python
admin.register(Order, OrderAdmin)
```

## API do ModelAdmin

### Metadados

```python
class ProductAdmin(ModelAdmin):
    display_name = "Produto"             # Nome singular
    display_name_plural = "Produtos"     # Nome plural
    icon = "package"                     # Lucide icon name
```

### List View

```python
class ProductAdmin(ModelAdmin):
    list_display = ("id", "name", "price", "is_available")   # Colunas visiveis
    list_display_links = ("id", "name")                       # Colunas clicaveis
    list_filter = ("is_available", "category")                # Filtros laterais
    search_fields = ("name", "description")                   # Campos de busca
    ordering = ("-created_at",)                               # Ordenacao default
    list_per_page = 50                                        # Itens por pagina
    list_max_show_all = 200                                   # Maximo "mostrar todos"
```

### Detail/Edit View

```python
class ProductAdmin(ModelAdmin):
    fields = ("name", "price", "description", "category")    # Campos no form (None = todos)
    exclude = ("internal_code",)                              # Campos excluidos
    readonly_fields = ("id", "created_at", "updated_at")     # Somente leitura
    
    # Agrupamento visual
    fieldsets = [
        ("Informacoes", {"fields": ("name", "description")}),
        ("Preco", {"fields": ("price", "discount")}),
        ("Status", {"fields": ("is_available", "category")}),
    ]
    
    # Help texts
    help_texts = {
        "price": "Preco em centavos (ex: 1990 = R$ 19,90)",
        "description": "Descricao exibida no catalogo",
    }
```

### Permissoes

```python
class ProductAdmin(ModelAdmin):
    permissions = ("view", "add", "change", "delete")    # Default
    exclude_actions = ("delete",)                         # Remove botao delete
```

Permissoes sao verificadas por model. Superusers tem acesso total. Staff users precisam de permissoes especificas no formato `{app_label}.{action}_{model_name}` (ex: `products.add_product`).

### Hooks

```python
class ProductAdmin(ModelAdmin):
    async def before_save(self, db, obj, is_new):
        """Executado antes de salvar."""
        if is_new:
            obj.slug = slugify(obj.name)
    
    async def after_save(self, db, obj, is_new):
        """Executado apos salvar."""
        if is_new:
            await notify_team(f"Novo produto: {obj.name}")
    
    async def before_delete(self, db, obj):
        """Executado antes de deletar."""
        if obj.has_orders:
            raise ValueError("Nao e possivel deletar produto com pedidos")
    
    async def after_delete(self, db, obj):
        """Executado apos deletar."""
        await clear_product_cache(obj.id)
```

### Campos computados

```python
class OrderAdmin(ModelAdmin):
    list_display = ("id", "customer_email", "total", "status_display")
    
    def status_display(self, obj) -> str:
        """Campo computado exibido na lista."""
        labels = {"pending": "Pendente", "paid": "Pago", "cancelled": "Cancelado"}
        return labels.get(obj.status, obj.status)
    
    status_display.short_description = "Status"
    status_display.admin_order_field = "status"
```

### Custom actions

```python
from core.admin import admin, ModelAdmin, action

@admin.register(Order)
class OrderAdmin(ModelAdmin):
    actions = ["mark_as_paid", "delete_selected"]
    
    @action(description="Marcar como pago")
    async def mark_as_paid(self, db, queryset):
        await queryset.update(status="paid")
```

### Queryset customizado

```python
class MyModelAdmin(ModelAdmin):
    def get_queryset(self, db):
        """Override para filtrar queryset base."""
        return self.model.objects.using(db).filter(is_archived=False)
```

## Models Core (auto-registrados)

Os seguintes models sobem automaticamente no admin:

| Model | Origem | Descricao |
|-------|--------|-----------|
| User | `get_user_model()` | Modelo de usuario (resolvido dinamicamente) |
| Group | `core.auth.models` | Grupos com permissoes |
| Permission | `core.auth.models` | Permissoes por codename |
| AuditLog | `core.admin.models` | Log de acoes administrativas |
| AdminSession | `core.admin.models` | Sessoes do admin panel |

### Ocultar model core

```python
from core.admin import admin
from core.auth.models import Permission

admin.unregister(Permission)
```

### Sobrescrever config de model core

```python
from core.admin import admin, ModelAdmin
from core.auth.models import get_user_model

User = get_user_model()

@admin.register(User)
class CustomUserAdmin(ModelAdmin):
    list_display = ("id", "email", "role", "is_active")
    exclude_actions = ("delete",)
```

O ultimo registro vence — o usuario sempre sobrescreve o core.

## get_user_model()

O admin NUNCA importa o modelo User diretamente. Sempre usa `get_user_model()` para respeitar modelos customizados:

```python
# CORRETO
from core.auth.models import get_user_model
User = get_user_model()

# ERRADO — nao faca isso
from core.auth.models import AbstractUser  # quebra se usuario customizou
```

## Autenticacao do Admin

O admin usa autenticacao session-based (cookies), separada do JWT da API. Apenas usuarios com `is_staff=True` ou `is_superuser=True` tem acesso.

- Login: `{prefix}/login`
- Logout: `{prefix}/logout`
- Cookie: `admin_session` (HttpOnly, SameSite=Lax, Secure em producao)

## Audit Log

Toda acao no admin (create, update, delete) e registrada automaticamente no `AuditLog`:

- Quem fez (user_id, email)
- O que fez (action, model, object_id)
- O que mudou (changes JSON com before/after)
- De onde (ip_address, user_agent)
- Quando (timestamp)

Visivel no admin para superusers. Somente leitura.

## API JSON (API-first)

O admin expoe uma API JSON completa sob `{prefix}/api/`:

```
GET    {prefix}/api/metadata                          # App list, erros, status
GET    {prefix}/api/{app}/{model}?page=1&q=search     # List (paginado)
GET    {prefix}/api/{app}/{model}/{pk}                 # Detail
POST   {prefix}/api/{app}/{model}                      # Create
PUT    {prefix}/api/{app}/{model}/{pk}                 # Update
DELETE {prefix}/api/{app}/{model}/{pk}                 # Delete
POST   {prefix}/api/{app}/{model}/bulk-delete          # Bulk delete
```

Todos os endpoints requerem autenticacao admin e retornam JSON. O frontend HTML consome esta API.

## Static Assets e collectstatic

### Em desenvolvimento

Assets servidos diretamente pelo FastAPI quando `debug=True`. Nenhum comando necessario.

### Em producao

```bash
core collectstatic
core collectstatic --output ./static
core collectstatic --no-hash
core collectstatic --verbose
```

O comando:
1. Copia assets do core (`core/admin/static/core-admin/`)
2. Copia assets de apps do usuario (`*/static/`)
3. Aplica cache busting (hash no nome: `admin.a1b2c3d4.css`)
4. Gera `manifest.json`
5. Output CDN-ready

```
static/core-admin/
├── css/admin.a1b2c3d4.css
├── js/admin.7e8f9a0b.js
└── manifest.json
```

## Tratamento de Erros

O admin nunca engole erros. Tres niveis:

### 1. AdminConfigurationError (fatal)

Impede o boot do admin. Stacktrace completo no terminal.

```
Failed to setup admin panel: AdminConfigurationError: Admin requires
a configured User model. Call configure_auth(user_model=YourUser)
before app startup.
```

### 2. AdminRegistrationError (por model)

Model especifico nao sobe, demais continuam. Warning no log + banner na UI.

```
AdminRegistrationError: UserAdmin.list_display references 'campo_inexistente'
which does not exist on model User.
Available columns: id, email, password_hash, is_active, is_staff, ...
Registered at: apps/users/admin.py:5
```

### 3. Runtime errors (na UI)

Erros de banco/query exibidos profissionalmente na UI com hints de resolucao:

```
⚠ Users — Tabela nao encontrada
  A tabela 'users' nao existe no banco de dados.
  Execute: core migrate
```

Em `debug=True`, stacktraces completos sao exibidos. Em producao, mensagens limpas.

## Configuracao explicita via core.toml

Para projetos com estrutura nao convencional, configure os modulos admin explicitamente:

```toml
# core.toml
[admin]
modules = ["apps.users.admin", "apps.payments.admin"]
```

Ou em `pyproject.toml`:

```toml
[tool.core.admin]
modules = ["apps.users.admin", "apps.payments.admin"]
```

## Stack Frontend

O admin usa uma stack leve, sem Node.js:

- **Jinja2** — Templates server-rendered
- **HTMX** (~14KB) — Interatividade sem SPA
- **Alpine.js** (~15KB) — Micro-interacoes
- **Tailwind CSS** — Design system
- **Lucide Icons** — Icones modernos

Tudo empacotado no core. Nenhum build step necessario.

## Exemplo Completo

```python
# apps/products/models.py
from core import Model, Field
from core.datetime import DateTime
from sqlalchemy.orm import Mapped

class Product(Model):
    __tablename__ = "products"
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=200)
    price: Mapped[int] = Field.integer()
    description: Mapped[str] = Field.text(default="")
    is_available: Mapped[bool] = Field.boolean(default=True)
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)


# apps/products/admin.py
from core.admin import admin, ModelAdmin, action
from apps.products.models import Product

@admin.register(Product)
class ProductAdmin(ModelAdmin):
    display_name = "Produto"
    display_name_plural = "Produtos"
    icon = "package"
    
    list_display = ("id", "name", "price", "is_available", "created_at")
    search_fields = ("name", "description")
    list_filter = ("is_available",)
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    
    help_texts = {
        "price": "Preco em centavos",
    }
    
    @action(description="Marcar como indisponivel")
    async def mark_unavailable(self, db, queryset):
        await queryset.update(is_available=False)
    
    actions = ["mark_unavailable", "delete_selected"]
    
    async def before_save(self, db, obj, is_new):
        if obj.price < 0:
            raise ValueError("Preco nao pode ser negativo")
```
