# Sistema de Testes

O Core Framework inclui um sistema completo de testes que facilita a criação de testes unitários, de integração e end-to-end para suas aplicações.

## Índice

- [Instalação](#instalação)
- [Quick Start](#quick-start)
- [CLI de Testes](#cli-de-testes)
- [Ambiente Isolado](#ambiente-isolado)
- [Fixtures Disponíveis](#fixtures-disponíveis)
- [TestClient](#testclient)
- [AuthenticatedClient](#authenticatedclient)
- [TestDatabase](#testdatabase)
- [Mocks](#mocks)
- [Factories](#factories)
- [Assertions](#assertions)
- [Testando Múltiplos Apps](#testando-múltiplos-apps)
- [Exemplos Completos](#exemplos-completos)
- [Boas Práticas](#boas-práticas)

---

## Instalação

Instale o Core Framework com as dependências de teste:

```bash
pip install core-framework[testing]
```

Ou adicione ao seu `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "core-framework[testing]",
]
```

### Dependências Incluídas

- `pytest>=7.4.0` - Framework de testes
- `pytest-asyncio>=0.23.0` - Suporte a testes assíncronos
- `httpx>=0.26.0` - Cliente HTTP para testes
- `faker>=20.0.0` - Geração de dados fake

---

## Quick Start

### 1. Crie sua estrutura de testes

```
myproject/
├── src/
│   └── myapp/
│       ├── __init__.py
│       ├── main.py
│       ├── models.py
│       └── views.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Configuração dos testes
│   ├── test_auth.py
│   └── test_users.py
└── pyproject.toml
```

### 2. Configure o `conftest.py`

```python
# tests/conftest.py
import pytest
from src.myapp.main import app as _app

@pytest.fixture(scope="session")
def app():
    """Retorna a instância do app para testes."""
    return _app
```

### 3. Escreva seu primeiro teste

```python
# tests/test_health.py
import pytest

@pytest.mark.asyncio
async def test_health_check(client):
    """Testa o endpoint de health check."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

### 4. Execute os testes

```bash
# Via CLI do Core Framework
core test

# Ou diretamente com pytest
pytest tests/
```

---

## CLI de Testes

O Core Framework inclui um comando CLI dedicado para execução de testes.

### Uso Básico

```bash
core test [OPTIONS] [PATH]
```

### Opções

| Opção | Descrição |
|-------|-----------|
| `path` | Caminho dos testes (default: `tests`) |
| `-v, --verbose` | Saída detalhada |
| `-k, --keyword` | Filtrar por keyword expression |
| `-x, --exitfirst` | Parar no primeiro erro |
| `--cov [SOURCE]` | Ativar cobertura de código |
| `--cov-report TYPE` | Formato do relatório (`term`, `html`, `xml`, `json`) |
| `-m, --marker` | Filtrar por marker (`unit`, `integration`, `slow`) |
| `--no-header` | Desabilitar cabeçalho do pytest |

### Exemplos

```bash
# Executar todos os testes
core test

# Executar arquivo específico
core test tests/test_auth.py

# Executar com saída verbose
core test -v

# Parar no primeiro erro
core test -x

# Filtrar por keyword
core test -k "test_login"
core test -k "test_login or test_register"
core test -k "not test_slow"

# Filtrar por marker
core test -m unit           # Apenas testes unitários
core test -m integration    # Apenas integração
core test -m "not slow"     # Excluir testes lentos

# Com cobertura de código
core test --cov
core test --cov=src/myapp
core test --cov=src --cov-report=html

# Combinando opções
core test tests/test_auth.py -v -x --cov=src
```

### Markers Pré-configurados

O plugin registra automaticamente os seguintes markers:

```python
@pytest.mark.unit          # Teste unitário (sem dependências externas)
@pytest.mark.integration   # Teste de integração
@pytest.mark.slow          # Teste lento
@pytest.mark.auth          # Requer autenticação
@pytest.mark.database      # Requer banco de dados
```

**Uso:**

```python
import pytest

@pytest.mark.unit
def test_password_validation():
    """Teste unitário de validação de senha."""
    from core.auth.hashers import validate_password_strength
    assert validate_password_strength("Weak") is False
    assert validate_password_strength("StrongPass123!") is True

@pytest.mark.integration
async def test_full_auth_flow(client):
    """Teste de integração do fluxo de auth."""
    # Register
    response = await client.post("/auth/register", json={...})
    assert response.status_code == 201
    
    # Login
    response = await client.post("/auth/login", json={...})
    assert response.status_code == 200

@pytest.mark.slow
async def test_heavy_computation():
    """Teste que demora muito."""
    ...
```

---

## Ambiente Isolado

O plugin cria automaticamente um ambiente isolado para cada execução de testes:

### O que é configurado automaticamente

1. **Banco de Dados**
   - SQLite em memória (`sqlite+aiosqlite:///:memory:`)
   - Tabelas criadas automaticamente
   - Limpeza após cada teste

2. **Configurações**
   - `TESTING=true`
   - `DEBUG=true`
   - `SECRET_KEY` de teste (apenas para testes!)

3. **Auth**
   - Configuração de tokens JWT
   - Sem warnings de middleware

4. **Middleware**
   - Registry limpo

### Variáveis de Ambiente

O ambiente de teste define:

```bash
TESTING=true
DEBUG=true
DATABASE_URL=sqlite+aiosqlite:///:memory:
SECRET_KEY=test-secret-key-for-testing-only
```

---

## Fixtures Disponíveis

O plugin fornece várias fixtures prontas para uso:

### Fixtures de Cliente HTTP

| Fixture | Descrição |
|---------|-----------|
| `client` | Cliente HTTP com banco inicializado |
| `auth_client` | Cliente já autenticado |
| `client_factory` | Factory para criar múltiplos clientes |

### Fixtures de Banco de Dados

| Fixture | Descrição |
|---------|-----------|
| `db` | Sessão do banco de dados |
| `clean_db` | Sessão com tabelas truncadas |
| `test_engine` | Engine do SQLAlchemy |

### Fixtures de Mock

| Fixture | Descrição |
|---------|-----------|
| `mock_kafka` | Mock do Kafka |
| `mock_redis` | Mock do Redis |
| `mock_http` | Mock para chamadas HTTP externas |

### Fixtures de Utilidade

| Fixture | Descrição |
|---------|-----------|
| `fake` | Instância do Faker |
| `user_factory` | Factory para criar usuários |
| `settings` | Configurações de teste |
| `assert_status` | Helper para assertions |
| `assert_json` | Helper para assertions JSON |

---

## TestClient

O `TestClient` é um cliente HTTP assíncrono com configuração automática de banco de dados.

### Uso Básico

```python
from core.testing import TestClient

async def test_with_client():
    async with TestClient(app) as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
```

### Usando a Fixture

```python
async def test_list_users(client):
    """client já vem configurado automaticamente."""
    response = await client.get("/api/v1/users/")
    assert response.status_code == 200
```

### Parâmetros

```python
TestClient(
    app,                                      # Aplicação FastAPI/Starlette
    database_url="sqlite+aiosqlite:///:memory:",  # URL do banco
    base_url="http://test",                   # URL base
    auto_create_tables=True,                  # Criar tabelas automaticamente
)
```

### Métodos HTTP

```python
async def test_crud_operations(client):
    # GET
    response = await client.get("/users/")
    
    # POST
    response = await client.post("/users/", json={"name": "John"})
    
    # PUT
    response = await client.put("/users/1", json={"name": "Jane"})
    
    # PATCH
    response = await client.patch("/users/1", json={"active": True})
    
    # DELETE
    response = await client.delete("/users/1")
    
    # Com headers
    response = await client.get(
        "/protected",
        headers={"Authorization": "Bearer token123"}
    )
    
    # Com query params
    response = await client.get("/users/", params={"page": 1, "size": 10})
```

---

## AuthenticatedClient

O `AuthenticatedClient` automaticamente registra um usuário e inclui o token de autenticação em todas as requisições.

### Uso Básico

```python
from core.testing import AuthenticatedClient

async def test_protected_endpoint():
    async with AuthenticatedClient(app) as client:
        # Todas as requisições já incluem o token!
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 200
```

### Usando a Fixture

```python
async def test_user_profile(auth_client):
    """auth_client já vem autenticado."""
    response = await auth_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
```

### Parâmetros

```python
AuthenticatedClient(
    app,
    email="test@example.com",         # Email do usuário de teste
    password="TestPass123!",          # Senha
    register_url="/api/v1/auth/register",  # URL de registro
    login_url="/api/v1/auth/login",        # URL de login
    extra_register_data=None,         # Dados extras no registro
)
```

### Testando com Múltiplos Usuários

```python
async def test_permission_denied(client_factory):
    """Testa que um usuário não pode acessar dados de outro."""
    # Cria dois usuários
    user1 = await client_factory(email="user1@example.com")
    user2 = await client_factory(email="user2@example.com")
    
    # User1 cria um recurso
    response = await user1.post("/api/v1/documents/", json={"title": "Private"})
    doc_id = response.json()["id"]
    
    # User2 não consegue acessar
    response = await user2.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 403
```

---

## TestDatabase

O `TestDatabase` gerencia o ciclo de vida do banco de dados nos testes.

### Uso Direto

```python
from core.testing import TestDatabase

async def test_database_operations():
    async with TestDatabase() as db:
        # Usar a sessão
        async with db.session() as session:
            user = User(email="test@example.com")
            session.add(user)
            await session.commit()
```

### Usando a Fixture `db`

```python
async def test_create_user(db):
    """Sessão de banco para queries diretas."""
    from myapp.models import User
    
    user = User(email="test@example.com", name="Test User")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    assert user.id is not None
    assert user.email == "test@example.com"
```

### Limpeza de Dados

```python
async def test_with_clean_data(clean_db):
    """Tabelas truncadas antes do teste."""
    # Garantia de começar com banco vazio
    users = await User.objects.using(clean_db).all()
    assert len(users) == 0
```

### Operações Disponíveis

```python
# Criar tabelas
await db.setup()

# Dropar tabelas
await db.teardown()

# Truncar todas as tabelas
await db.truncate_all()

# Sessão para queries
async with db.session() as session:
    ...
```

---

## Mocks

### MockKafka

Mock para testes com Kafka/messaging.

```python
async def test_send_event(mock_kafka):
    # Seu código que envia para Kafka
    await mock_kafka.send("events", {"type": "user.created", "id": 1})
    
    # Assertions
    mock_kafka.assert_sent("events")
    mock_kafka.assert_sent("events", count=1)
    mock_kafka.assert_message_contains("events", {"type": "user.created"})
    
    # Acessar mensagens
    messages = mock_kafka.get_messages("events")
    assert len(messages) == 1
    assert messages[0].value["type"] == "user.created"
```

**Métodos disponíveis:**

```python
# Enviar mensagem
await mock_kafka.send(topic, value, key=None)

# Assertions
mock_kafka.assert_sent(topic, count=None)
mock_kafka.assert_not_sent(topic)
mock_kafka.assert_message_contains(topic, expected_data)

# Acessar dados
mock_kafka.get_messages(topic)  # Lista de MockMessage
mock_kafka.get_all_messages()   # Dict[topic, List[MockMessage]]

# Limpar
mock_kafka.clear()
mock_kafka.clear_topic(topic)
```

### MockRedis

Mock completo do Redis.

```python
async def test_caching(mock_redis):
    # String operations
    await mock_redis.set("key", "value")
    value = await mock_redis.get("key")
    assert value == "value"
    
    # Com TTL
    await mock_redis.set("temp", "data", ex=60)
    
    # Hash operations
    await mock_redis.hset("user:1", "name", "John")
    await mock_redis.hset("user:1", "email", "john@example.com")
    user = await mock_redis.hgetall("user:1")
    assert user == {"name": "John", "email": "john@example.com"}
    
    # List operations
    await mock_redis.lpush("queue", "task1", "task2")
    task = await mock_redis.rpop("queue")
    assert task == "task1"
    
    # Set operations
    await mock_redis.sadd("tags", "python", "testing")
    assert await mock_redis.sismember("tags", "python")
```

**Operações suportadas:**

| Tipo | Operações |
|------|-----------|
| Strings | `get`, `set`, `delete`, `exists`, `expire`, `ttl` |
| Hashes | `hget`, `hset`, `hdel`, `hgetall`, `hexists` |
| Lists | `lpush`, `rpush`, `lpop`, `rpop`, `llen`, `lrange` |
| Sets | `sadd`, `srem`, `smembers`, `sismember`, `scard` |
| Keys | `keys`, `delete`, `exists` |

### MockHTTP

Mock para chamadas HTTP externas.

```python
async def test_external_api(mock_http):
    # Configurar resposta esperada
    mock_http.when("GET", "https://api.github.com/users/octocat").respond(
        status=200,
        json={"login": "octocat", "id": 1}
    )
    
    # Seu código que chama a API
    response = await mock_http.request("GET", "https://api.github.com/users/octocat")
    assert response["login"] == "octocat"
    
    # Verificar que foi chamado
    mock_http.assert_called("GET", "https://api.github.com/users/octocat")
    mock_http.assert_called("GET", "https://api.github.com/users/octocat", times=1)
```

**Configurando respostas:**

```python
# JSON response
mock_http.when("POST", "https://api.stripe.com/charges").respond(
    status=201,
    json={"id": "ch_123", "status": "succeeded"}
)

# Text response
mock_http.when("GET", "https://example.com/robots.txt").respond(
    status=200,
    text="User-agent: *\nDisallow: /"
)

# Error response
mock_http.when("GET", "https://api.example.com/fail").respond(
    status=500,
    json={"error": "Internal Server Error"}
)

# With headers
mock_http.when("GET", "https://api.example.com/data").respond(
    status=200,
    json={"data": "value"},
    headers={"X-Custom-Header": "value"}
)
```

---

## Factories

### Factory Base

Crie factories personalizadas para seus models:

```python
from core.testing import Factory, fake

class ProductFactory(Factory):
    model = Product
    
    @classmethod
    def build(cls, **overrides):
        data = {
            "name": fake.word().capitalize(),
            "description": fake.sentence(),
            "price": fake.pyfloat(min_value=1, max_value=1000, right_digits=2),
            "sku": fake.uuid4()[:8].upper(),
            "active": True,
        }
        data.update(overrides)
        return data
    
    @classmethod
    async def create(cls, db, **overrides):
        data = cls.build(**overrides)
        product = cls.model(**data)
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product
```

**Uso:**

```python
async def test_product_listing(db, client):
    # Criar produtos
    products = await ProductFactory.create_batch(db, count=5)
    
    # Testar endpoint
    response = await client.get("/api/v1/products/")
    assert len(response.json()) >= 5

async def test_specific_product(db):
    # Com valores específicos
    product = await ProductFactory.create(db, name="Special Product", price=99.99)
    assert product.name == "Special Product"
    assert product.price == 99.99
```

### UserFactory

Factory pré-configurada para usuários:

```python
async def test_multiple_users(db, user_factory):
    # Criar usuário simples
    user = await user_factory.create(db)
    
    # Com email específico
    admin = await user_factory.create(db, email="admin@example.com", is_admin=True)
    
    # Criar batch
    users = await user_factory.create_batch(db, count=10)
```

### Faker

Gerador de dados fake para testes:

```python
def test_data_generation(fake):
    # Dados pessoais
    name = fake.name()
    email = fake.email()
    phone = fake.phone_number()
    
    # Endereço
    address = fake.address()
    city = fake.city()
    country = fake.country()
    
    # Internet
    username = fake.user_name()
    url = fake.url()
    
    # Texto
    sentence = fake.sentence()
    paragraph = fake.paragraph()
    
    # Números
    number = fake.random_int(min=1, max=100)
    price = fake.pyfloat(min_value=0, max_value=1000, right_digits=2)
    
    # Datas
    date = fake.date_object()
    datetime = fake.date_time()
```

---

## Assertions

Helpers para assertions comuns em testes de API:

### Status Codes

```python
from core.testing import assert_status, assert_status_ok, assert_created

async def test_endpoints(client):
    # Status específico
    response = await client.get("/users/")
    assert_status(response, 200)
    
    # Atalhos
    assert_status_ok(response)           # 200-299
    
    response = await client.post("/users/", json={...})
    assert_created(response)              # 201
    
    response = await client.get("/not-found")
    assert_not_found(response)            # 404
    
    response = await client.get("/protected")
    assert_unauthorized(response)         # 401
    
    response = await client.get("/admin-only")
    assert_forbidden(response)            # 403
```

### JSON Content

```python
from core.testing import assert_json_contains, assert_json_equals, assert_json_list

async def test_json_response(client):
    response = await client.get("/users/1")
    
    # Contém campos específicos
    assert_json_contains(response, {
        "id": 1,
        "email": "test@example.com"
    })
    
    # Igualdade exata
    assert_json_equals(response, {
        "id": 1,
        "email": "test@example.com",
        "name": "Test User"
    })
    
    # Lista com tamanho
    response = await client.get("/users/")
    users = assert_json_list(response, min_length=1, max_length=100)
```

### Errors

```python
from core.testing import assert_validation_error, assert_error_code

async def test_validation(client):
    response = await client.post("/users/", json={"email": "invalid"})
    
    # Erro de validação
    assert_validation_error(response)
    
    # Erro em campo específico
    assert_validation_error(response, field="email")
    
    # Código de erro específico
    assert_error_code(response, "INVALID_EMAIL")
```

### Headers

```python
from core.testing import assert_header

async def test_headers(client):
    response = await client.get("/download")
    
    # Header existe
    assert_header(response, "Content-Type")
    
    # Header com valor
    assert_header(response, "Content-Type", "application/json")
```

---

## Testando Múltiplos Apps

### Estrutura de Projeto Multi-App

```
myproject/
├── apps/
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── views.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_login.py
│   │       └── test_register.py
│   ├── users/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── views.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       └── test_users.py
│   └── products/
│       ├── __init__.py
│       ├── models.py
│       ├── views.py
│       └── tests/
│           ├── __init__.py
│           └── test_products.py
├── src/
│   └── main.py
├── tests/
│   ├── conftest.py          # Configuração global
│   ├── integration/         # Testes de integração
│   │   └── test_checkout.py
│   └── e2e/                 # Testes end-to-end
│       └── test_purchase_flow.py
└── pyproject.toml
```

### Configuração do `conftest.py` Global

```python
# tests/conftest.py
import pytest
import sys
from pathlib import Path

# Adicionar apps ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "apps"))

from src.main import create_app

@pytest.fixture(scope="session")
def app():
    """App configurado para testes."""
    return create_app(testing=True)

@pytest.fixture(scope="session")
def anyio_backend():
    """Backend para pytest-asyncio."""
    return "asyncio"
```

### Rodando Testes por App

```bash
# Todos os testes
core test

# Apenas auth
core test apps/auth/tests/

# Apenas users
core test apps/users/tests/

# Testes de integração
core test tests/integration/

# Combinado
core test apps/auth/tests/ apps/users/tests/ -v
```

### Fixtures Específicas por App

```python
# apps/products/tests/conftest.py
import pytest
from core.testing import Factory, fake

class ProductFactory(Factory):
    @classmethod
    def build(cls, **overrides):
        return {
            "name": fake.word(),
            "price": fake.pyfloat(min_value=1, max_value=100),
            **overrides
        }

@pytest.fixture
def product_factory():
    return ProductFactory

@pytest.fixture
async def sample_products(db, product_factory):
    """Cria produtos de exemplo para testes."""
    return await product_factory.create_batch(db, count=5)
```

**Uso nos testes:**

```python
# apps/products/tests/test_products.py
async def test_list_products(client, sample_products):
    """sample_products criados automaticamente."""
    response = await client.get("/api/v1/products/")
    assert response.status_code == 200
    assert len(response.json()) >= 5
```

---

## Exemplos Completos

### Exemplo 1: CRUD Completo

```python
# tests/test_crud.py
import pytest
from core.testing import (
    assert_status,
    assert_created,
    assert_json_contains,
    assert_not_found,
)

class TestUserCRUD:
    """Testes de CRUD para usuários."""
    
    @pytest.fixture
    async def user_data(self, fake):
        return {
            "email": fake.email(),
            "name": fake.name(),
            "password": "SecurePass123!",
        }
    
    async def test_create_user(self, client, user_data):
        """POST /users/ cria usuário."""
        response = await client.post("/api/v1/users/", json=user_data)
        
        assert_created(response)
        assert_json_contains(response, {
            "email": user_data["email"],
            "name": user_data["name"],
        })
        assert "password" not in response.json()  # Senha não exposta
    
    async def test_read_user(self, auth_client, db, user_factory):
        """GET /users/{id} retorna usuário."""
        user = await user_factory.create(db)
        
        response = await auth_client.get(f"/api/v1/users/{user.id}")
        
        assert_status(response, 200)
        assert_json_contains(response, {"id": user.id})
    
    async def test_update_user(self, auth_client, db, user_factory):
        """PUT /users/{id} atualiza usuário."""
        user = await user_factory.create(db)
        
        response = await auth_client.put(
            f"/api/v1/users/{user.id}",
            json={"name": "Updated Name"}
        )
        
        assert_status(response, 200)
        assert response.json()["name"] == "Updated Name"
    
    async def test_delete_user(self, auth_client, db, user_factory):
        """DELETE /users/{id} remove usuário."""
        user = await user_factory.create(db)
        
        response = await auth_client.delete(f"/api/v1/users/{user.id}")
        assert_status(response, 204)
        
        # Verificar que foi removido
        response = await auth_client.get(f"/api/v1/users/{user.id}")
        assert_not_found(response)
    
    async def test_list_users(self, auth_client, db, user_factory):
        """GET /users/ lista usuários."""
        await user_factory.create_batch(db, count=5)
        
        response = await auth_client.get("/api/v1/users/")
        
        assert_status(response, 200)
        assert len(response.json()) >= 5


### Exemplo 2: Autenticação

```python
# tests/test_auth.py
import pytest
from core.testing import (
    assert_status,
    assert_created,
    assert_unauthorized,
    assert_json_contains,
)

class TestAuthentication:
    """Testes de autenticação."""
    
    @pytest.fixture
    def user_credentials(self):
        return {
            "email": "auth_test@example.com",
            "password": "StrongPass123!",
        }
    
    async def test_register_success(self, client, user_credentials):
        """Registro com credenciais válidas."""
        response = await client.post(
            "/api/v1/auth/register",
            json={**user_credentials, "name": "Test User"}
        )
        
        assert_created(response)
        assert_json_contains(response, {"email": user_credentials["email"]})
    
    async def test_register_duplicate_email(self, client, user_credentials):
        """Registro duplicado falha."""
        # Primeiro registro
        await client.post(
            "/api/v1/auth/register",
            json={**user_credentials, "name": "User 1"}
        )
        
        # Segundo registro com mesmo email
        response = await client.post(
            "/api/v1/auth/register",
            json={**user_credentials, "name": "User 2"}
        )
        
        assert_status(response, 400)
    
    async def test_login_success(self, client, user_credentials):
        """Login com credenciais corretas."""
        # Registrar primeiro
        await client.post(
            "/api/v1/auth/register",
            json={**user_credentials, "name": "Test User"}
        )
        
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json=user_credentials
        )
        
        assert_status(response, 200)
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
    
    async def test_login_invalid_password(self, client, user_credentials):
        """Login com senha errada falha."""
        # Registrar
        await client.post(
            "/api/v1/auth/register",
            json={**user_credentials, "name": "Test User"}
        )
        
        # Login com senha errada
        response = await client.post(
            "/api/v1/auth/login",
            json={**user_credentials, "password": "WrongPassword123!"}
        )
        
        assert_unauthorized(response)
    
    async def test_protected_endpoint_without_token(self, client):
        """Endpoint protegido sem token falha."""
        response = await client.get("/api/v1/auth/me")
        assert_unauthorized(response)
    
    async def test_protected_endpoint_with_token(self, auth_client):
        """Endpoint protegido com token funciona."""
        response = await auth_client.get("/api/v1/auth/me")
        assert_status(response, 200)


### Exemplo 3: Com Mocks

```python
# tests/test_with_mocks.py
import pytest

class TestNotifications:
    """Testes com mocks de serviços externos."""
    
    async def test_send_notification(self, auth_client, mock_kafka):
        """Criar recurso envia notificação para Kafka."""
        response = await auth_client.post(
            "/api/v1/documents/",
            json={"title": "Important Doc", "content": "..."}
        )
        
        assert response.status_code == 201
        
        # Verificar evento enviado
        mock_kafka.assert_sent("document.events", count=1)
        mock_kafka.assert_message_contains("document.events", {
            "type": "document.created",
            "title": "Important Doc"
        })
    
    async def test_cache_user_profile(self, auth_client, mock_redis):
        """Perfil é cacheado no Redis."""
        # Primeira chamada - cache miss
        response = await auth_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        
        # Verificar que foi cacheado
        cached = await mock_redis.get("user:profile:test@example.com")
        assert cached is not None
    
    async def test_external_api_call(self, auth_client, mock_http):
        """Integração com API externa."""
        # Configurar mock
        mock_http.when("GET", "https://api.geocode.com/search").respond(
            status=200,
            json={"lat": -23.5505, "lng": -46.6333}
        )
        
        # Fazer requisição que chama API externa
        response = await auth_client.post(
            "/api/v1/locations/",
            json={"address": "São Paulo, Brazil"}
        )
        
        assert response.status_code == 201
        mock_http.assert_called("GET", "https://api.geocode.com/search")
```

---

## Boas Práticas

### 1. Organize os Testes

```
tests/
├── unit/              # Testes sem I/O
│   ├── test_validators.py
│   └── test_utils.py
├── integration/       # Com banco de dados
│   ├── test_models.py
│   └── test_queries.py
├── e2e/              # Fluxos completos
│   └── test_user_journey.py
└── conftest.py
```

### 2. Use Markers

```python
@pytest.mark.unit
def test_pure_function():
    """Teste rápido, sem dependências."""
    pass

@pytest.mark.integration
async def test_with_database(db):
    """Requer banco de dados."""
    pass

@pytest.mark.slow
async def test_heavy_operation(client):
    """Teste demorado."""
    pass
```

### 3. Fixtures Reutilizáveis

```python
# conftest.py
@pytest.fixture
def valid_user_data(fake):
    """Dados válidos de usuário."""
    return {
        "email": fake.email(),
        "password": "ValidPass123!",
        "name": fake.name(),
    }

@pytest.fixture
async def existing_user(db, user_factory, valid_user_data):
    """Usuário já existente no banco."""
    return await user_factory.create(db, **valid_user_data)
```

### 4. Teste Casos de Erro

```python
class TestErrorCases:
    async def test_not_found(self, client):
        response = await client.get("/users/99999")
        assert response.status_code == 404
    
    async def test_validation_error(self, client):
        response = await client.post("/users/", json={"email": "invalid"})
        assert response.status_code == 422
    
    async def test_unauthorized(self, client):
        response = await client.get("/protected")
        assert response.status_code == 401
```

### 5. Limpe Estado Entre Testes

```python
@pytest.fixture(autouse=True)
async def cleanup(mock_kafka, mock_redis):
    """Limpa mocks após cada teste."""
    yield
    mock_kafka.clear()
    mock_redis.clear()
```

### 6. Use Context Managers para Setup/Teardown

```python
@pytest.fixture
async def temp_file():
    """Arquivo temporário para teste."""
    import tempfile
    import os
    
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    os.unlink(path)
```

---

## Configuração do pyproject.toml

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
    "unit: Testes unitários",
    "integration: Testes de integração",
    "slow: Testes lentos",
    "auth: Requer autenticação",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.coverage.run]
source = ["src", "apps"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
]
```

---

## Troubleshooting

### Erro: "No module named 'pytest'"

```bash
pip install pytest pytest-asyncio
# ou
pip install core-framework[testing]
```

### Erro: "Database not initialized"

O plugin inicializa automaticamente. Se ainda ocorrer:

```python
# conftest.py
import pytest
from core.testing.database import setup_test_db

@pytest.fixture(scope="session", autouse=True)
async def init_database():
    await setup_test_db()
```

### Erro: "App fixture not defined"

```python
# conftest.py
import pytest

@pytest.fixture(scope="session")
def app():
    from myapp.main import app
    return app
```

### Testes Assíncronos Não Funcionam

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

Ou decore cada teste:

```python
import pytest

@pytest.mark.asyncio
async def test_async_function():
    ...
```

---

## Referências

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [httpx](https://www.python-httpx.org/)
- [Faker](https://faker.readthedocs.io/)
