# Authentication

O sistema de autenticacao e baseado em JWT (JSON Web Tokens). A configuracao e centralizada e afeta toda a aplicacao.

## Configuracao Inicial

A funcao `configure_auth()` deve ser chamada no inicio da aplicacao, antes de qualquer rota ser registrada.

```python
# src/main.py
from core.auth import configure_auth
from src.apps.users.models import User

# Chamado uma vez na inicializacao da aplicacao
# Todos os parametros tem valores padrao, mas secret_key DEVE ser alterado em producao
configure_auth(
    # Chave usada para assinar tokens JWT
    # NUNCA use o valor padrao em producao
    # Recomendado: string aleatoria de 32+ caracteres
    secret_key="your-secret-key",
    
    # Tempo de vida do access token em minutos
    # Tokens expirados retornam 401 Unauthorized
    access_token_expire_minutes=30,
    
    # Tempo de vida do refresh token em dias
    # Usado para obter novos access tokens sem re-autenticar
    refresh_token_expire_days=7,
    
    # Model que representa usuarios no sistema
    # Deve herdar de AbstractUser ou implementar interface compativel
    user_model=User,
)
```

**Importante**: `configure_auth()` registra automaticamente os backends de autenticacao (`ModelBackend`, `TokenAuthBackend`). Chamadas subsequentes sobrescrevem a configuracao anterior.

## User Model

O `AbstractUser` fornece campos e metodos padrao para autenticacao. Extenda para adicionar campos especificos do seu dominio.

```python
# src/apps/users/models.py
from core.auth import AbstractUser
from sqlalchemy.orm import Mapped, mapped_column

class User(AbstractUser):
    # __tablename__ e obrigatorio mesmo herdando de AbstractUser
    __tablename__ = "users"
    
    # Campos adicionais especificos da sua aplicacao
    # AbstractUser ja fornece: id, email, password_hash, is_active, etc.
    phone: Mapped[str | None] = mapped_column(default=None)
    avatar_url: Mapped[str | None] = mapped_column(default=None)
```

**Campos herdados de AbstractUser**:
- `id`: Primary key (int)
- `email`: Unico, usado como identificador de login
- `password_hash`: Hash da senha (nunca armazena texto plano)
- `is_active`: Se False, usuario nao consegue autenticar
- `is_staff`: Flag para usuarios administrativos
- `is_superuser`: Flag para super usuarios
- `date_joined`: Data de criacao da conta
- `last_login`: Atualizado automaticamente em cada login

**Metodos disponiveis**:
- `set_password(password)`: Gera hash e armazena
- `check_password(password)`: Verifica senha contra hash
- `authenticate(email, password, db)`: Classmethod que retorna User ou None
- `create_user(email, password, db)`: Classmethod para criar usuario comum
- `create_superuser(email, password, db)`: Classmethod para criar superuser

## Funcoes de Token

Tokens sao criados e verificados atraves de funcoes dedicadas. O framework gerencia a assinatura e validacao automaticamente.

```python
from core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
)

# Criar access token
# user_id e armazenado no claim "sub" (subject) do JWT
# extra_claims permite adicionar dados customizados ao payload
access = create_access_token(
    user_id=user.id,
    extra_claims={"email": user.email}  # Opcional
)

# Criar refresh token
# Refresh tokens tem vida mais longa e sao usados apenas para renovar access tokens
refresh = create_refresh_token(user_id=user.id)

# Verificar token
# Retorna payload (dict) se valido, None se invalido ou expirado
# token_type deve corresponder ao tipo do token sendo verificado
payload = verify_token(token, token_type="access")  # ou "refresh"
if payload:
    user_id = payload["sub"]  # "sub" contem o user_id
```

**Estrutura do payload JWT**:
```json
{
  "sub": "123",           // user_id como string
  "type": "access",       // "access" ou "refresh"
  "exp": 1706792400,      // Unix timestamp de expiracao
  "iat": 1706790600,      // Unix timestamp de criacao
  "email": "user@..."     // extra_claims (se fornecido)
}
```

## ViewSet de Autenticacao

Implementacao tipica de endpoints de login, registro e perfil.

```python
from core import ModelViewSet, action
from core.auth import create_access_token, create_refresh_token, verify_token
from core.permissions import AllowAny, IsAuthenticated
from fastapi import HTTPException

class AuthViewSet(ModelViewSet):
    model = User
    permission_classes = [AllowAny]  # Padrao: endpoints publicos
    tags = ["Auth"]
    
    @action(methods=["POST"], detail=False)
    async def login(self, request, db, **kwargs):
        """
        POST /auth/login
        Body: {"email": "...", "password": "..."}
        
        Autentica usuario e retorna par de tokens.
        """
        body = await request.json()
        
        # authenticate() retorna User se credenciais validas, None caso contrario
        # Tambem verifica is_active - usuarios inativos retornam None
        user = await User.authenticate(body["email"], body["password"], db)
        if not user:
            # 401 para credenciais invalidas
            # Mensagem generica por seguranca - nao revela se email existe
            raise HTTPException(401, "Invalid credentials")
        
        return {
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
        }
    
    @action(methods=["POST"], detail=False)
    async def register(self, request, db, **kwargs):
        """
        POST /auth/register
        Body: {"email": "...", "password": "..."}
        
        Cria novo usuario. Nao retorna tokens - cliente deve fazer login.
        """
        body = await request.json()
        
        # create_user() levanta excecao se email ja existe
        # Considere tratar IntegrityError para mensagem amigavel
        user = await User.create_user(
            email=body["email"],
            password=body["password"],
            db=db,
        )
        return {"id": user.id, "email": user.email}
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(self, request, db, **kwargs):
        """
        GET /auth/me
        Header: Authorization: Bearer <access_token>
        
        Retorna dados do usuario autenticado.
        permission_classes=[IsAuthenticated] exige token valido.
        """
        # request.state.user e populado automaticamente pelo middleware de auth
        # quando um token valido e fornecido no header Authorization
        user = request.state.user
        return {"id": user.id, "email": user.email}
```

**Fluxo de autenticacao**:
1. Cliente envia credenciais para `/auth/login`
2. Servidor retorna `access_token` e `refresh_token`
3. Cliente inclui `Authorization: Bearer <access_token>` em requests subsequentes
4. Quando access token expira, cliente usa refresh token para obter novo par

## Permissoes

Permissoes controlam acesso a endpoints. Sao classes que implementam logica de verificacao.

```python
from core.permissions import (
    AllowAny,           # Permite qualquer acesso, mesmo sem token
    IsAuthenticated,    # Exige token valido (request.state.user != None)
    IsAdmin,            # Exige is_admin=True ou is_superuser=True
    IsOwner,            # Exige que usuario seja dono do objeto (via user_id ou owner_id)
    HasRole,            # Exige role especifico (requer campo roles no User)
)

class PostViewSet(ModelViewSet):
    # Permissao padrao para todas as acoes
    permission_classes = [IsAuthenticated]
    
    # Override por acao especifica
    # Acoes nao listadas usam permission_classes
    permission_classes_by_action = {
        "list": [AllowAny],           # GET /posts/ - publico
        "retrieve": [AllowAny],       # GET /posts/{id} - publico
        "create": [IsAuthenticated],  # POST /posts/ - logado
        "update": [IsOwner],          # PUT /posts/{id} - apenas autor
        "destroy": [IsAdmin],         # DELETE /posts/{id} - apenas admin
    }
```

**Ordem de verificacao**: `permission_classes_by_action[action]` > `permission_classes` > `[IsAuthenticated]` (padrao)

## Permissao Customizada

Crie permissoes para regras de negocio especificas.

```python
from core.permissions import Permission

class IsPremiumUser(Permission):
    # Mensagem retornada quando permissao e negada
    message = "Premium subscription required"
    
    async def has_permission(self, request, view=None) -> bool:
        """
        Verificacao a nivel de endpoint.
        Chamado antes de qualquer operacao.
        
        request.state.user: usuario autenticado ou None
        view: instancia do ViewSet (pode ser None em alguns contextos)
        
        Retorno: True permite acesso, False nega com self.message
        """
        user = getattr(request.state, "user", None)
        # Verifica se usuario existe E tem atributo is_premium=True
        return user and user.is_premium
    
    async def has_object_permission(self, request, view, obj) -> bool:
        """
        Verificacao a nivel de objeto.
        Chamado apos has_permission(), apenas em operacoes que acessam objeto especifico.
        
        obj: instancia do model sendo acessada
        
        Use para regras como "apenas dono pode editar".
        """
        # Neste caso, mesma logica de has_permission
        return await self.has_permission(request, view)
```

**Quando usar cada metodo**:
- `has_permission()`: Regras que nao dependem do objeto (roles, planos, horarios)
- `has_object_permission()`: Regras que dependem do objeto (ownership, status do objeto)

## Backend de Autenticacao Customizado

Backends definem COMO a autenticacao acontece. O padrao usa JWT no header Authorization.

```python
from core.auth.backends import AuthBackend

class APIKeyBackend(AuthBackend):
    """
    Autentica via header X-API-Key ao inves de JWT.
    Util para integracao com servicos externos.
    """
    
    async def authenticate(self, request, db, **kwargs):
        """
        Chamado pelo middleware para tentar autenticar o request.
        
        Retorno: User se autenticado, None se nao (tenta proximo backend)
        """
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        
        # Busca API key no banco e retorna usuario associado
        return await APIKey.objects.using(db).filter(
            key=api_key,
            is_active=True,
        ).first()
```

Registro do backend:

```python
from core.auth.backends import register_auth_backend

# "api_key" e o identificador do backend
# Pode ser usado para selecionar backend especifico em contextos avancados
register_auth_backend("api_key", APIKeyBackend())
```

**Ordem de backends**: O framework tenta cada backend registrado em ordem ate um retornar User. Se todos retornarem None, request.state.user permanece None.

## Password Hashers

Algoritmos disponiveis para hash de senha. A escolha afeta seguranca e performance.

| Algoritmo | Seguranca | Performance | Recomendacao |
|-----------|-----------|-------------|--------------|
| `pbkdf2_sha256` | Boa | Rapida | Padrao, compativel |
| `bcrypt` | Muito boa | Media | Recomendado |
| `argon2` | Excelente | Lenta | Projetos novos |

```python
configure_auth(
    # argon2 e o mais seguro, mas requer mais CPU
    # Em servidores com recursos limitados, bcrypt e bom compromisso
    password_hasher="argon2",
)
```

**Migracao de hasher**: Usuarios existentes mantem o hash antigo. O framework detecta o algoritmo pelo prefixo do hash e verifica corretamente. Novos hashes usam o algoritmo configurado.

Hasher customizado (casos raros):

```python
from core.auth.hashers import PasswordHasher

class CustomHasher(PasswordHasher):
    # Identificador unico - usado no prefixo do hash
    algorithm = "custom"
    
    def hash(self, password: str) -> str:
        """Gera hash da senha. Retorno deve incluir prefixo do algoritmo."""
        # Implementacao do hash
        pass
    
    def verify(self, password: str, hashed: str) -> bool:
        """Verifica se senha corresponde ao hash."""
        # Implementacao da verificacao
        pass
```

---

Proximo: [Messaging](04-messaging.md) - Sistema de eventos assincrono com Kafka, RabbitMQ ou Redis.
