# Admin Panel

Painel administrativo estilo Django com tipagem genérica para autocomplete no PyCharm.

## Habilitação

Admin é habilitado por padrão. Acesse em `/admin/`.

```python
# src/settings.py
class AppSettings(Settings):
    admin_enabled: bool = True  # Default
    admin_url_prefix: str = "/admin"
    admin_site_title: str = "Minha Empresa"
    admin_site_header: str = "Painel Administrativo"
    admin_primary_color: str = "#3B82F6"  # blue-500
```

## Registrar Models

```python
# src/apps/posts/admin.py
from core.admin import admin, ModelAdmin
from .models import Post

@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):  # Tipagem genérica para autocomplete
    display_name = "Post"
    display_name_plural = "Posts"
    icon = "file-text"  # Lucide icon
    
    list_display = ("id", "title", "published", "created_at")
    list_filter = ("published",)
    search_fields = ("title", "content")
    ordering = ("-created_at",)
```

## Tipagem Genérica

Use `ModelAdmin[Model]` para autocomplete no PyCharm:

```python
from core.admin import ModelAdmin, WidgetConfig, IconType

@admin.register(Domain)
class DomainAdmin(ModelAdmin[Domain]):
    # PyCharm sugere ícones válidos
    icon: IconType = "globe"
    
    # Campos do model Domain
    list_display = ("id", "domain", "is_verified")
    
    # TypedDict para widgets
    widgets: dict[str, WidgetConfig] = {
        "hostname_status": {
            "widget": "choices",
            "label": "Status do Hostname",
        },
    }
```

## Opções Completas

```python
@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    # ══════════════════════════════════════════════════════════════════
    # Metadados
    # ══════════════════════════════════════════════════════════════════
    display_name = "Post"
    display_name_plural = "Posts"
    icon = "file-text"  # Lucide icon
    
    # ══════════════════════════════════════════════════════════════════
    # List View
    # ══════════════════════════════════════════════════════════════════
    list_display = ("id", "title", "author_id", "published", "created_at")
    list_display_links = ("id", "title")  # Campos clicáveis
    list_filter = ("published", "author_id")
    search_fields = ("title", "content")
    ordering = ("-created_at",)
    list_per_page = 25
    list_max_show_all = 200
    
    # ══════════════════════════════════════════════════════════════════
    # Detail/Edit View
    # ══════════════════════════════════════════════════════════════════
    fields = ("title", "content", "published")  # Campos no form
    exclude = ("deleted_at",)  # Campos a excluir
    readonly_fields = ("id", "created_at", "updated_at")
    
    # ══════════════════════════════════════════════════════════════════
    # Fieldsets (agrupamento)
    # ══════════════════════════════════════════════════════════════════
    fieldsets = [
        ("Conteúdo", {"fields": ("title", "content")}),
        ("Status", {"fields": ("published",)}),
        ("Metadados", {"fields": ("created_at", "updated_at")}),
    ]
    
    # ══════════════════════════════════════════════════════════════════
    # Widgets e Help Texts
    # ══════════════════════════════════════════════════════════════════
    widgets = {
        "content": {"widget": "text", "label": "Conteúdo do Post"},
    }
    
    help_texts = {
        "title": "Título que aparece na listagem",
        "content": "Conteúdo em markdown",
    }
    
    # ══════════════════════════════════════════════════════════════════
    # Permissões
    # ══════════════════════════════════════════════════════════════════
    permissions = ("view", "add", "change", "delete")
    exclude_actions = ()  # Actions a desabilitar
```

## Widgets Disponíveis

| Widget | Descrição |
|--------|-----------|
| `default` | Input padrão baseado no tipo |
| `string` | Input de texto |
| `text` | Textarea |
| `integer` | Input numérico |
| `float` | Input decimal |
| `boolean` | Checkbox |
| `datetime` | Date/time picker |
| `date` | Date picker |
| `time` | Time picker |
| `json` | Editor JSON |
| `uuid` | Input UUID |
| `password` | Input de senha |
| `password_hash` | Campo de hash (oculto) |
| `virtual_password` | Senha virtual (usa set_password) |
| `secret` | Campo secreto (nunca exibe) |
| `email` | Input de email |
| `url` | Input de URL |
| `slug` | Input de slug (auto-gera) |
| `color` | Color picker |
| `ip` | Input de IP |
| `choices` | Select dropdown (enum) |
| `fk` | Foreign key (autocomplete) |
| `m2m_select` | Many-to-many select |
| `file_upload` | Upload de arquivo (storage local ou GCS); drag-and-drop, preview |

## Campos de arquivo (Storage) e exclusão

Quando o model tem campos que armazenam **path ou URL de arquivo** (ex.: `image`, `avatar`, `file_path`, `attachment_url`), o admin detecta automaticamente e exibe o widget **file_upload**:

- **Detecção automática**: nomes como `image`, `avatar`, `photo`, `file_path`, `attachment`, `*_url` (para imagem/arquivo) viram `file_upload`.
- **Widget no formulário**: área de drag-and-drop, preview (imagem ou ícone), link para o arquivo atual e botão para remover.
- **Upload**: o arquivo é enviado para o backend configurado em Settings (`storage_backend`: local ou GCS). O valor retornado (path ou URL) é salvo no campo.

Configure o storage em `src/settings.py` (veja [Settings — Storage](02-settings.md#storage--file-uploads)). Documentação completa da API e fluxo: [Storage (37-storage.md)](37-storage.md).

### Exclusão e arquivos físicos

Ao **deletar** um registro (botão "Delete" na tela de edição):

1. Abre um **modal de confirmação**.
2. Se o model tiver campos file_upload com valor, aparece a opção: **"Also delete X file(s) from storage"**.
3. Se marcar, o backend remove o(s) arquivo(s) do disco ou do bucket GCS ao deletar o registro.

Assim você evita arquivo órfão no storage. Em **bulk delete** (listagem), o body da requisição pode incluir `"delete_physical_files": true` para o mesmo efeito.

### Forçar widget file_upload em um campo

Se o nome da coluna não for detectado automaticamente, use `widgets`:

```python
@admin.register(Profile)
class ProfileAdmin(ModelAdmin[Profile]):
    widgets = {
        "cover_image": {"widget": "file_upload", "label": "Cover image"},
    }
```

## Ícones (Lucide)

```python
# Ícones mais comuns
icon = "file"        # Arquivo
icon = "folder"      # Pasta
icon = "user"        # Usuário
icon = "users"       # Usuários
icon = "settings"    # Configurações
icon = "database"    # Banco de dados
icon = "globe"       # Domínio/Web
icon = "mail"        # Email
icon = "lock"        # Segurança
icon = "key"         # Chave
icon = "shield"      # Proteção
icon = "activity"    # Atividade
icon = "calendar"    # Calendário
icon = "clock"       # Tempo
icon = "tag"         # Tag
icon = "bookmark"    # Favorito
icon = "star"        # Estrela
icon = "heart"       # Coração
icon = "bell"        # Notificação
icon = "search"      # Busca
icon = "filter"      # Filtro
icon = "edit"        # Editar
icon = "trash"       # Lixeira
icon = "plus"        # Adicionar
icon = "refresh-cw"  # Atualizar
icon = "download"    # Download
icon = "upload"      # Upload
icon = "link"        # Link
icon = "eye"         # Visualizar
icon = "copy"        # Copiar
icon = "archive"     # Arquivar
icon = "box"         # Caixa
icon = "package"     # Pacote
icon = "layers"      # Camadas
icon = "grid"        # Grade
icon = "list"        # Lista
icon = "table"       # Tabela
icon = "pie-chart"   # Gráfico pizza
icon = "bar-chart"   # Gráfico barras
icon = "trending-up" # Tendência alta
icon = "dollar-sign" # Dinheiro
icon = "credit-card" # Cartão
icon = "shopping-cart" # Carrinho
icon = "truck"       # Entrega
icon = "map-pin"     # Localização
icon = "zap"         # Raio/Rápido
icon = "cpu"         # Processador
icon = "server"      # Servidor
icon = "hard-drive"  # Disco
icon = "wifi"        # WiFi
icon = "monitor"     # Monitor
icon = "smartphone"  # Celular
icon = "code"        # Código
icon = "terminal"    # Terminal
icon = "git-branch"  # Git
```

## Actions Customizadas

```python
@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    list_display = ("id", "title", "published")
    actions = ["delete_selected", "publish", "unpublish"]
    
    @admin.action(description="Publicar selecionados")
    async def publish(self, db, queryset):
        for post in queryset:
            post.published = True
            await post.save(db)
    
    @admin.action(description="Despublicar selecionados")
    async def unpublish(self, db, queryset):
        for post in queryset:
            post.published = False
            await post.save(db)
```

## Hooks de Ciclo de Vida

```python
@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    async def before_save(self, db, obj, is_new: bool) -> None:
        """Executado antes de salvar (create ou update)."""
        if is_new:
            obj.slug = slugify(obj.title)
    
    async def after_save(self, db, obj, is_new: bool) -> None:
        """Executado após salvar."""
        if is_new:
            await send_notification(f"Novo post: {obj.title}")
    
    async def before_delete(self, db, obj) -> None:
        """Executado antes de deletar."""
        await archive_post(obj)
    
    async def after_delete(self, db, obj) -> None:
        """Executado após deletar."""
        await clear_cache(f"post:{obj.id}")
```

## Queryset Customizado

```python
@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    def get_queryset(self, db):
        """Filtra queryset base."""
        # Exemplo: só mostrar posts do workspace do usuário
        return Post.objects.using(db).filter(workspace_id=self.request.user.workspace_id)
```

## Password Virtual

Para models com `set_password()`, o admin detecta automaticamente e cria um campo virtual de senha:

```python
@admin.register(User)
class UserAdmin(ModelAdmin[User]):
    # password_field é auto-detectado se model tem set_password()
    # e uma coluna password_hash/hashed_password
    
    # Para customizar:
    password_field = "password_hash"  # Coluna do hash
    
    widgets = {
        "password": {
            "help_text": "Deixe vazio para manter a senha atual",
            "required_on_create": True,
            "required_on_edit": False,
        },
    }
```

## Many-to-Many

Relacionamentos M2M são detectados automaticamente:

```python
@admin.register(User)
class UserAdmin(ModelAdmin[User]):
    # groups e user_permissions são detectados automaticamente
    # se o model tem esses relacionamentos M2M
    
    fieldsets = [
        ("Conta", {"fields": ("email", "password")}),
        ("Permissões", {"fields": ("is_active", "is_staff", "groups", "user_permissions")}),
    ]
```

## Permissões

Acesso ao admin requer `is_staff=True`.

```python
@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    # Permissões disponíveis
    permissions = ("view", "add", "change", "delete")
    
    # Desabilitar ações específicas
    exclude_actions = ("delete_selected",)
```

## Configurações do Admin

```python
# src/settings.py
class AppSettings(Settings):
    # Habilitar/desabilitar
    admin_enabled: bool = True
    
    # URL
    admin_url_prefix: str = "/admin"  # ou "/backoffice", "/ops-secret"
    
    # Branding
    admin_site_title: str = "Minha Empresa"  # Título na aba
    admin_site_header: str = "Painel Admin"  # Header no sidebar
    admin_logo_url: str = "/static/logo.png"  # Logo custom
    
    # Tema
    admin_theme: str = "default"  # ou "dark"
    admin_primary_color: str = "#3B82F6"  # Cor primária (hex)
    admin_custom_css: str = "./static/admin-custom.css"  # CSS extra
    
    # Segurança
    admin_cookie_secure: bool = None  # None = auto-detect HTTPS
```

## Operations Center

O admin inclui um centro de operações para monitorar:

```python
class AppSettings(Settings):
    # Habilitar Operations Center
    ops_enabled: bool = True
    
    # Tasks
    ops_task_persist: bool = True  # Persistir execuções
    ops_task_retention_days: int = 30  # Dias para reter
    
    # Workers
    ops_worker_heartbeat_interval: int = 30  # Heartbeat (segundos)
    ops_worker_offline_ttl: int = 24  # Horas para manter offline
    
    # Logs
    ops_log_buffer_size: int = 5000  # Tamanho do buffer
    ops_log_stream_enabled: bool = True  # Streaming SSE
    
    # Infraestrutura
    ops_infrastructure_poll_interval: int = 60  # Métricas (segundos)
```

## Login

Admin usa autenticação por sessão (separada do JWT da API).

```bash
# Criar superusuário
core createsuperuser
```

Login padrão: `/admin/login`

## Auto-Discovery

Módulos admin são descobertos automaticamente de arquivos `admin.py`:

```
src/apps/
├── posts/
│   ├── models.py
│   └── admin.py  # Auto-descoberto
└── users/
    ├── models.py
    └── admin.py  # Auto-descoberto
```

## Tipos para Autocomplete

```python
from core.admin import (
    ModelAdmin,
    WidgetConfig,      # TypedDict para widgets
    FieldsetConfig,    # Tipo para fieldsets
    IconType,          # Literal com ícones válidos
    PermissionType,    # Literal para permissões
    WidgetType,        # Literal com widgets válidos
)
```

## Próximos Passos

- [CLI](07-cli.md) — Comandos disponíveis
- [Permissions](08-permissions.md) — Controle de acesso
- [Settings](02-settings.md) — Todas as configurações
