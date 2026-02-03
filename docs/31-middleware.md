# Sistema de Middleware

O Core Framework fornece um sistema de middleware inspirado no Django, permitindo configuração declarativa e fácil criação de middlewares customizados.

---

## Configuração Rápida

### Via CoreApp

```python
from core import CoreApp

app = CoreApp(
    title="My API",
    middleware=[
        "timing",           # Mede tempo de resposta
        "request_id",       # Adiciona ID único
        "auth",             # Autenticação
        "logging",          # Logs de request/response
    ],
)
```

### Via Settings

```python
from core import Settings

class AppSettings(Settings):
    middleware: list[str] = [
        "timing",
        "auth",
        "logging",
    ]
```

Ou via variável de ambiente:
```bash
MIDDLEWARE='["timing", "auth", "logging"]'
```

### Via configure_middleware()

```python
from core.middleware import configure_middleware

configure_middleware([
    "timing",
    ("logging", {"log_body": True}),  # Com configuração
    "auth",
])
```

---

## Shortcuts Disponíveis

| Shortcut | Classe Completa | Descrição |
|----------|-----------------|-----------|
| `auth` | `core.auth.AuthenticationMiddleware` | Popula `request.state.user` |
| `optional_auth` | `core.auth.OptionalAuthenticationMiddleware` | Auth opcional (nunca falha) |
| `timing` | `core.middleware.TimingMiddleware` | Header `X-Response-Time` |
| `request_id` | `core.middleware.RequestIDMiddleware` | Header `X-Request-ID` |
| `logging` | `core.middleware.LoggingMiddleware` | Logs de requests |
| `security_headers` | `core.middleware.SecurityHeadersMiddleware` | Headers de segurança |
| `maintenance` | `core.middleware.MaintenanceModeMiddleware` | Modo manutenção (503) |
| `cors` | `starlette.middleware.cors.CORSMiddleware` | CORS (já incluso por padrão) |
| `gzip` | `starlette.middleware.gzip.GZipMiddleware` | Compressão gzip |

---

## Middlewares Built-in

### TimingMiddleware

Adiciona o header `X-Response-Time` com duração da request.

```python
middleware=["timing"]

# Response headers:
# X-Response-Time: 0.0234s
```

### RequestIDMiddleware

Adiciona ID único a cada request para tracing.

```python
middleware=["request_id"]

# Request pode enviar seu próprio ID:
# X-Request-ID: my-custom-id

# Ou será gerado automaticamente:
# X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

Acesso no código:
```python
@router.get("/test")
async def test(request: Request):
    request_id = request.state.request_id
    return {"request_id": request_id}
```

### LoggingMiddleware

Loga todas as requests e responses.

```python
middleware=[
    ("logging", {
        "log_body": False,      # Log do body
        "log_headers": False,   # Log dos headers
        "logger_name": "core.requests",
    }),
]
```

Saída de exemplo:
```
INFO:core.requests:→ GET /api/users?page=1
INFO:core.requests:← 200 [0.045s]
```

### AuthenticationMiddleware

Autentica requests e popula `request.state.user`.

```python
middleware=["auth"]

# No seu código:
@router.get("/me")
async def me(request: Request):
    user = request.state.user
    if not user:
        raise HTTPException(401)
    return {"email": user.email}
```

Configuração avançada:
```python
middleware=[
    ("auth", {
        "skip_paths": ["/health", "/docs"],  # Paths sem auth
        "header_name": "Authorization",
        "scheme": "Bearer",
    }),
]
```

### SecurityHeadersMiddleware

Adiciona headers de segurança.

```python
middleware=["security_headers"]

# Headers adicionados:
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# X-XSS-Protection: 1; mode=block
# Referrer-Policy: strict-origin-when-cross-origin
```

Configuração:
```python
middleware=[
    ("security_headers", {
        "enable_hsts": True,        # HTTPS only
        "hsts_max_age": 31536000,   # 1 ano
        "headers": {
            "X-Custom-Header": "value",
        },
    }),
]
```

### MaintenanceModeMiddleware

Retorna 503 para todas as requests quando ativado.

```python
middleware=[
    ("maintenance", {
        "maintenance_enabled": False,  # Ative quando precisar
        "message": "Sistema em manutenção",
        "allowed_ips": ["127.0.0.1", "10.0.0.1"],
        "allowed_paths": ["/health", "/admin"],
    }),
]
```

---

## Criando Middleware Customizado

### Estrutura Básica

```python
from core.middleware import BaseMiddleware
from starlette.requests import Request
from starlette.responses import Response

class MyMiddleware(BaseMiddleware):
    """Descrição do middleware."""
    
    # Configurações opcionais
    name = "MyMiddleware"        # Nome para logs
    order = 100                  # Ordem de execução
    exclude_paths = ["/health"]  # Paths a ignorar
    include_paths = []           # Paths específicos (vazio = todos)
    
    async def before_request(self, request: Request) -> Response | None:
        """
        Executado ANTES da view.
        
        Retorne None para continuar, ou Response para curto-circuitar.
        """
        pass
    
    async def after_request(self, request: Request, response: Response) -> Response:
        """
        Executado DEPOIS da view.
        
        Deve retornar Response (pode modificar).
        """
        return response
    
    async def on_error(self, request: Request, exc: Exception) -> Response | None:
        """
        Executado quando ocorre exceção.
        
        Retorne None para re-raise, ou Response para handling.
        """
        return None
```

### Exemplo: Rate Limiting

```python
from core.middleware import BaseMiddleware
from starlette.responses import JSONResponse
from collections import defaultdict
import time

class RateLimitMiddleware(BaseMiddleware):
    """Limita requests por IP."""
    
    name = "RateLimitMiddleware"
    order = 30  # Executa cedo
    
    # Configurações
    requests_per_minute: int = 60
    
    # Cache interno
    _request_counts: dict = defaultdict(list)
    
    async def before_request(self, request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        minute_ago = now - 60
        
        # Limpa requests antigas
        self._request_counts[client_ip] = [
            t for t in self._request_counts[client_ip] if t > minute_ago
        ]
        
        # Verifica limite
        if len(self._request_counts[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )
        
        # Registra request
        self._request_counts[client_ip].append(now)
    
    async def after_request(self, request, response):
        client_ip = request.client.host if request.client else "unknown"
        remaining = self.requests_per_minute - len(self._request_counts[client_ip])
        
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        
        return response
```

### Exemplo: Request Correlation

```python
from core.middleware import BaseMiddleware
import contextvars

# Context var para ID da request
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")

class CorrelationMiddleware(BaseMiddleware):
    """Propaga correlation ID para logs e chamadas externas."""
    
    name = "CorrelationMiddleware"
    order = 5
    
    header_name: str = "X-Correlation-ID"
    
    async def before_request(self, request):
        import uuid
        
        # Usa ID do header ou gera novo
        correlation_id = request.headers.get(self.header_name)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Armazena no request e no context var
        request.state.correlation_id = correlation_id
        request_id_var.set(correlation_id)
    
    async def after_request(self, request, response):
        correlation_id = getattr(request.state, "correlation_id", None)
        if correlation_id:
            response.headers[self.header_name] = correlation_id
        return response


# Uso em qualquer lugar:
def get_correlation_id() -> str:
    return request_id_var.get("unknown")
```

### Exemplo: Cache de Responses

```python
from core.middleware import BaseMiddleware
from starlette.responses import Response
import hashlib
import json

class CacheMiddleware(BaseMiddleware):
    """Cache simples de responses GET."""
    
    name = "CacheMiddleware"
    order = 50
    include_paths = ["/api/"]  # Só cacheia /api/*
    
    ttl_seconds: int = 60
    _cache: dict = {}
    
    def _cache_key(self, request) -> str:
        """Gera chave de cache."""
        return hashlib.md5(
            f"{request.method}:{request.url}".encode()
        ).hexdigest()
    
    async def before_request(self, request):
        # Só cacheia GET
        if request.method != "GET":
            return None
        
        import time
        key = self._cache_key(request)
        
        if key in self._cache:
            data, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl_seconds:
                return Response(
                    content=data,
                    media_type="application/json",
                    headers={"X-Cache": "HIT"},
                )
        
        return None
    
    async def after_request(self, request, response):
        # Cacheia apenas GET 200
        if request.method == "GET" and response.status_code == 200:
            import time
            key = self._cache_key(request)
            
            # Lê body da response
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            self._cache[key] = (body, time.time())
            
            response.headers["X-Cache"] = "MISS"
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )
        
        return response
```

---

## Ordem de Execução

Middlewares são executados na ordem em que são registrados:

```python
middleware=[
    "timing",    # 1º before, último after
    "auth",      # 2º before, penúltimo after
    "logging",   # 3º before, primeiro after
]
```

Fluxo de execução:
```
Request
    ↓
timing.before_request()
    ↓
auth.before_request()
    ↓
logging.before_request()
    ↓
    [VIEW]
    ↓
logging.after_request()
    ↓
auth.after_request()
    ↓
timing.after_request()
    ↓
Response
```

Use o atributo `order` para controlar prioridade:
```python
class EarlyMiddleware(BaseMiddleware):
    order = 10  # Executa primeiro

class LateMiddleware(BaseMiddleware):
    order = 200  # Executa depois
```

---

## Debug da Stack

### Visualizar Stack

```python
from core.middleware import print_middleware_stack

print_middleware_stack(app)
```

Saída:
```
📦 Middleware Stack:
==================================================
   1. TimingMiddleware
   2. RequestIDMiddleware
   3. AuthenticationMiddleware
   4. LoggingMiddleware
   └─ [APP] FastAPI
==================================================
```

### Obter Info Programaticamente

```python
from core.middleware import get_middleware_stack_info

info = get_middleware_stack_info(app)
for mw in info:
    print(f"{mw['class']}: {mw.get('module')}")
```

---

## Boas Práticas

### 1. Ordem Recomendada

```python
middleware=[
    "request_id",       # Primeiro: ID para tracing
    "timing",           # Cedo: medir tempo total
    "security_headers", # Cedo: headers de segurança
    "auth",             # Depois: autenticação
    "logging",          # Por último: log completo
]
```

### 2. Falhe Graciosamente

```python
class SafeMiddleware(BaseMiddleware):
    async def before_request(self, request):
        try:
            # Sua lógica
            pass
        except Exception as e:
            # Log mas não falhe
            import logging
            logging.error(f"Middleware error: {e}")
            # Continua sem falhar
```

### 3. Use exclude_paths para Paths Críticos

```python
class HeavyMiddleware(BaseMiddleware):
    exclude_paths = [
        "/health",      # Health checks
        "/metrics",     # Prometheus
        "/docs",        # Swagger
        "/openapi.json",
    ]
```

### 4. Evite Estado Global

```python
# ❌ Ruim: estado global
_counter = 0

class BadMiddleware(BaseMiddleware):
    async def before_request(self, request):
        global _counter
        _counter += 1  # Race condition!

# ✅ Bom: estado no request
class GoodMiddleware(BaseMiddleware):
    async def before_request(self, request):
        request.state.counter = getattr(request.state, "counter", 0) + 1
```

---

## Migração do Formato Antigo

### Antes (v0.12.1)

```python
from starlette.middleware.base import BaseHTTPMiddleware

class MyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # antes
        response = await call_next(request)
        # depois
        return response

app = CoreApp(
    middlewares=[(MyMiddleware, {})],  # Formato antigo
)
```

### Depois (v0.12.2)

```python
from core.middleware import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_request(self, request):
        pass
    
    async def after_request(self, request, response):
        return response

app = CoreApp(
    middleware=["myapp.middleware.MyMiddleware"],  # Formato novo
)
```

O formato antigo ainda funciona para retrocompatibilidade.
