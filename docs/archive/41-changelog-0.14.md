# Changelog — v0.14.0

## Admin Panel Nativo (Major Feature)

Release que introduz o Admin Panel como componente core do framework. Interface de gestao completa, auto-gerada, com auto-discovery, seguranca integrada e API JSON-first.

### Novos Modulos

- **NEW**: `core/admin/` — Package completo do Admin Panel
- **NEW**: `core/admin/site.py` — `AdminSite` singleton, registro e auto-discovery
- **NEW**: `core/admin/options.py` — `ModelAdmin` base class para configuracao
- **NEW**: `core/admin/discovery.py` — Auto-discovery de `admin.py` em apps
- **NEW**: `core/admin/permissions.py` — `IsAdminUser`, verificacao de permissoes por model
- **NEW**: `core/admin/models.py` — `AuditLog` e `AdminSession` models
- **NEW**: `core/admin/defaults.py` — Configs default para models core (User, Group, etc)
- **NEW**: `core/admin/serializers.py` — Auto-geracao de Pydantic schemas a partir de SQLAlchemy models
- **NEW**: `core/admin/views.py` — API JSON completa (list, detail, create, update, delete, bulk-delete)
- **NEW**: `core/admin/router.py` — Router principal com endpoints HTML e API
- **NEW**: `core/admin/exceptions.py` — `AdminConfigurationError`, `AdminRegistrationError`, `AdminRuntimeError`
- **NEW**: `core/admin/collectstatic.py` — Comando `core collectstatic` para assets de producao
- **NEW**: `core/admin/__init__.py` — API publica: `admin`, `register`, `ModelAdmin`, etc

### Templates e Assets

- **NEW**: `core/admin/templates/admin/base.html` — Layout base com Tailwind + HTMX + Alpine.js
- **NEW**: `core/admin/templates/admin/login.html` — Pagina de login session-based
- **NEW**: `core/admin/templates/admin/dashboard.html` — Dashboard com status, erros e app list
- **NEW**: `core/admin/templates/admin/list.html` — List view com paginacao, busca, filtros, bulk actions
- **NEW**: `core/admin/templates/admin/detail.html` — Detail/edit view com forms dinamicos
- **NEW**: `core/admin/static/core-admin/css/admin.css` — Estilos custom
- **NEW**: `core/admin/static/core-admin/js/admin.js` — JS para icones e mensagens

### Settings (core/config.py)

- **NEW**: `admin_enabled` — Habilita/desabilita o admin (default: `True`)
- **NEW**: `admin_url_prefix` — Rota customizavel (default: `"/admin"`)
- **NEW**: `admin_site_title` — Titulo da pagina (default: `"Admin"`)
- **NEW**: `admin_site_header` — Header no sidebar (default: `"Core Admin"`)
- **NEW**: `admin_theme` — Tema visual (default: `"default"`)
- **NEW**: `admin_logo_url` — URL de logo customizado
- **NEW**: `admin_primary_color` — Cor primaria hex (default: `"#3B82F6"`)
- **NEW**: `admin_custom_css` — Path para CSS adicional

### Boot Sequence (core/app.py)

- **NEW**: Step 8.5 no boot sequence — `_setup_admin()` automatico
- **NEW**: Auto-discovery de `admin.py` em apps configurados
- **NEW**: Mount do admin router no FastAPI app
- **NEW**: Logging estruturado de erros de admin

### CLI (core/cli/main.py)

- **NEW**: `core collectstatic` — Coleta assets para producao
  - `--output` — Diretorio alvo (default: `./static`)
  - `--no-hash` — Desabilita cache busting
  - `--verbose` — Output detalhado
- **NEW**: Cache busting com hash no filename
- **NEW**: `manifest.json` gerado automaticamente

### API do Admin

```
GET    /admin/api/metadata               # Metadados de apps, models, erros
GET    /admin/api/{app}/{model}/          # List paginado + search
POST   /admin/api/{app}/{model}/          # Create
GET    /admin/api/{app}/{model}/{pk}/     # Detail
PUT    /admin/api/{app}/{model}/{pk}/     # Update
DELETE /admin/api/{app}/{model}/{pk}/     # Delete
POST   /admin/api/{app}/{model}/bulk-delete/  # Bulk delete
```

### Features

- Auto-discovery de `admin.py` (como Django)
- CRUD completo auto-gerado para qualquer model
- `ModelAdmin` com `list_display`, `search_fields`, `list_filter`, `ordering`
- `readonly_fields`, `fieldsets`, `help_texts`
- Hooks: `before_save`, `after_save`, `before_delete`, `after_delete`
- Custom actions em bulk
- Campos computados
- Permissoes por model (view/add/change/delete)
- Audit log automatico com diff JSON
- Session-based auth (separada do JWT da API)
- `get_user_model()` para flexibilidade do modelo User
- Tratamento de erros profissional em 3 niveis
- Stack frontend leve: Jinja2 + HTMX + Alpine.js + Tailwind

### Seguranca

- Autenticacao session-based com cookies HttpOnly
- CSRF protection
- Permissoes RBAC por model integradas com core.auth
- Audit trail completo
- Rota customizavel para seguranca por obscuridade
- SameSite=Lax, Secure em producao

### Testes

- **NEW**: `tests/test_admin.py` — 42 testes cobrindo:
  - Registry (register, unregister, decorator, duplicatas)
  - ModelAdmin (defaults, validacao, configuracao)
  - Exceptions e ErrorCollector
  - Permissions
  - Serializers (list, detail, write schemas)
  - Collectstatic
  - Exports publicos

### Decisoes Arquiteturais

1. **Server-rendered, nao SPA** — Simplicidade, zero build step, progressivamente interativo via HTMX
2. **API-first** — Frontend HTML consome API JSON interna; tudo testavel/extensivel via API
3. **`get_user_model()` obrigatorio** — Nunca import direto do User; respeita customizacao
4. **Errors transparentes** — Nunca try/catch silencioso; erros exibidos profissionalmente
5. **Rota customizavel** — `admin_url_prefix` via Settings; nao hardcoded
6. **Singleton AdminSite** — Um site global com estado limpo por registro/reset

### Dependencias

- Nenhuma dependencia nova no core. Jinja2 ja e dependencia transitiva do FastAPI.
- Frontend: Tailwind, HTMX, Alpine.js e Lucide servidos via CDN (sem Node.js)

### Breaking Changes

Nenhum. O admin e 100% aditivo. Projetos existentes nao sao afetados.

### Upgrade

```bash
pip install --upgrade core-framework
```

O admin esta habilitado por padrao. Para desabilitar:

```bash
ADMIN_ENABLED=false
```
