# Core Framework - Complete Guide

Python framework inspired by Django, built on FastAPI. High performance, low coupling, extreme productivity.

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Models and ORM](#models-and-orm)
4. [Serializers](#serializers)
5. [Views and ViewSets (DRF Pattern)](#views-and-viewsets-drf-pattern)
6. [Routing](#routing)
7. [Authentication](#authentication)
8. [Custom Authentication Backends](#custom-authentication-backends)
9. [Custom Token Types](#custom-token-types)
10. [Custom User Model](#custom-user-model)
11. [Permissions](#permissions)
12. [Database](#database)
13. [Migrations](#migrations)
14. [Enterprise Features](#enterprise-features-v030)
15. [Messaging System](#messaging-system)
16. [Background Tasks](#background-tasks)
17. [Deployment](#deployment)
18. [Custom Message Brokers](#custom-message-brokers)
19. [Architecture Example](#architecture-example)
20. [Best Practices](#best-practices)

---

## Installation

```bash
# Global CLI installation
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"

# Create new project
core init my-project --python 3.13

# Enter project
cd my-project
source .venv/bin/activate

# Setup database
core makemigrations --name initial
core migrate

# Run server
core run
```

---

## Configuration

### .env File

```env
# Application
APP_NAME=My API
ENVIRONMENT=development
DEBUG=true
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=sqlite+aiosqlite:///./app.db
DATABASE_ECHO=false

# API
API_PREFIX=/api/v1

# Auth
AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=30
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
AUTH_PASSWORD_HASHER=pbkdf2_sha256
```

### Custom Settings

The `src/api/config.py` file comes with all available settings documented.
To add custom settings, define new fields:

```python
# src/api/config.py
from core import Settings

class AppSettings(Settings):
    # Custom settings (in addition to defaults)
    stripe_api_key: str = ""
    sendgrid_api_key: str = ""
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    redis_url: str = "redis://localhost:6379"

settings = AppSettings()
```

### Using Settings

```python
from src.api.config import settings

# Access settings
print(settings.database_url)
print(settings.is_production)
print(settings.stripe_api_key)
print(settings.secret_key)
```

### Available Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| APP_NAME | str | "My App" | Application name |
| APP_VERSION | str | "0.1.0" | Application version |
| ENVIRONMENT | str | "development" | development, staging, production, testing |
| DEBUG | bool | false | Debug mode (never use in production) |
| SECRET_KEY | str | - | Secret key for JWT tokens |
| DATABASE_URL | str | sqlite+aiosqlite:///./app.db | Database connection URL |
| API_PREFIX | str | /api/v1 | API routes prefix |
| AUTH_ACCESS_TOKEN_EXPIRE_MINUTES | int | 30 | Access token expiration |
| AUTH_REFRESH_TOKEN_EXPIRE_DAYS | int | 7 | Refresh token expiration |
| AUTH_PASSWORD_HASHER | str | pbkdf2_sha256 | Password hasher algorithm |

---

## Models and ORM

### Defining Models

```python
# src/apps/posts/models.py
from sqlalchemy.orm import Mapped
from core import Model, Field
from core.datetime import DateTime

class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    slug: Mapped[str] = Field.string(max_length=200, unique=True, index=True)
    content: Mapped[str] = Field.text()
    is_published: Mapped[bool] = Field.boolean(default=False)
    views_count: Mapped[int] = Field.integer(default=0)
    author_id: Mapped[int] = Field.foreign_key("users.id")
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[DateTime | None] = Field.datetime(auto_now=True, nullable=True)
```

### Available Field Types

```python
Field.pk()                          # Primary key (auto-increment)
Field.string(max_length=255)        # VARCHAR
Field.text()                        # TEXT
Field.integer()                     # INTEGER
Field.big_integer()                 # BIGINT
Field.float_()                      # FLOAT
Field.decimal(precision=10, scale=2)# DECIMAL
Field.boolean(default=False)        # BOOLEAN
Field.datetime(auto_now_add=True)   # DATETIME
Field.date()                        # DATE
Field.time()                        # TIME
Field.json()                        # JSON
Field.uuid()                        # UUID
Field.foreign_key("table.column")   # Foreign key
```

### QuerySet Operations

```python
from src.apps.posts.models import Post

# Get all
posts = await Post.objects.using(db).all()

# Filter
published = await Post.objects.using(db).filter(is_published=True).all()

# Complex filters
posts = await Post.objects.using(db).filter(
    is_published=True,
    views_count__gt=100,
    title__contains="Python",
).order_by("-created_at").limit(10).all()

# Get single
post = await Post.objects.using(db).get(id=1)
post = await Post.objects.using(db).get_or_none(slug="my-post")

# First/Last
first = await Post.objects.using(db).first()
last = await Post.objects.using(db).order_by("-id").first()

# Count
count = await Post.objects.using(db).filter(is_published=True).count()

# Exists
exists = await Post.objects.using(db).filter(slug="my-post").exists()

# Pagination
posts = await Post.objects.using(db).offset(20).limit(10).all()
```

### Instance Operations

```python
# Save
post = Post(title="Title", slug="title", content="...")
await post.save(db)

# Update
post.title = "New Title"
await post.save(db)

# Delete
await post.delete(db)

# Reload from database
await post.refresh(db)

# Convert to dict
data = post.to_dict()
```

---

## Serializers

### Input and Output Schemas

```python
# src/apps/posts/schemas.py
from pydantic import field_validator, EmailStr
from core import InputSchema, OutputSchema
from core.datetime import DateTime

class PostInput(InputSchema):
    """Schema for creating/updating posts."""
    title: str
    slug: str
    content: str
    is_published: bool = False
    
    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if " " in v:
            raise ValueError("Slug cannot contain spaces")
        return v.lower()

class PostOutput(OutputSchema):
    """Schema for post responses."""
    id: int
    title: str
    slug: str
    content: str
    is_published: bool
    views_count: int
    created_at: DateTime
    updated_at: DateTime | None
```

### Custom Validation

```python
from pydantic import field_validator, model_validator

class UserInput(InputSchema):
    email: EmailStr
    password: str
    password_confirm: str
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        return v
    
    @model_validator(mode="after")
    def passwords_match(self) -> "UserInput":
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self
```

---

## Views and ViewSets (DRF Pattern)

Core Framework uses a 100% DRF-style pattern. All endpoints are defined using ViewSets and @action decorators - no direct FastAPI decorators needed.

### ModelViewSet - Complete CRUD

```python
# src/apps/posts/views.py
from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core import ModelViewSet, action
from core.permissions import IsAuthenticated, AllowAny

from src.apps.posts.models import Post
from src.apps.posts.schemas import PostInput, PostOutput

class PostViewSet(ModelViewSet):
    """
    ViewSet for post management.
    
    Auto-generated endpoints:
        GET    /posts/              - List all posts
        POST   /posts/              - Create post
        GET    /posts/{id}/         - Get post details
        PUT    /posts/{id}/         - Update post
        PATCH  /posts/{id}/         - Partial update
        DELETE /posts/{id}/         - Delete post
    """
    
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    tags = ["Posts"]
    
    # Permissions per action
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "partial_update": [IsAuthenticated],
        "destroy": [IsAuthenticated],
    }
    
    # Unique field validation
    unique_fields = ["slug"]
    
    # Pagination
    page_size = 20
    max_page_size = 100
    
    def get_queryset(self, db):
        """Customize base queryset."""
        return Post.objects.using(db).filter(is_published=True)
    
    async def perform_create_validation(self, data: dict, db: AsyncSession) -> dict:
        """Hook before creating - transform data."""
        data["slug"] = data["title"].lower().replace(" ", "-")
        return data
    
    async def after_create(self, obj, db: AsyncSession) -> None:
        """Hook after creating - side effects."""
        # Send notification, invalidate cache, etc.
        pass
```

### Custom Actions with @action

```python
from core import ModelViewSet, action
from core.permissions import IsAuthenticated, AllowAny

class PostViewSet(ModelViewSet):
    model = Post
    input_schema = PostInput
    output_schema = PostOutput
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def publish(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /posts/{id}/publish/
        
        Publish a post.
        """
        post = await self.get_object(db, **kwargs)
        post.is_published = True
        await post.save(db)
        return {"message": f"Post '{post.title}' published", "is_published": True}
    
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def unpublish(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /posts/{id}/unpublish/
        
        Unpublish a post.
        """
        post = await self.get_object(db, **kwargs)
        post.is_published = False
        await post.save(db)
        return {"message": f"Post '{post.title}' unpublished", "is_published": False}
    
    @action(methods=["GET"], detail=False, permission_classes=[AllowAny])
    async def featured(self, request: Request, db: AsyncSession, **kwargs):
        """
        GET /posts/featured/
        
        Get featured posts (high view count).
        """
        posts = await Post.objects.using(db).filter(
            is_published=True,
            views_count__gt=100,
        ).order_by("-views_count").limit(5).all()
        
        return [PostOutput.model_validate(p).model_dump() for p in posts]
    
    @action(methods=["GET"], detail=True, permission_classes=[AllowAny])
    async def stats(self, request: Request, db: AsyncSession, **kwargs):
        """
        GET /posts/{id}/stats/
        
        Get post statistics.
        """
        post = await self.get_object(db, **kwargs)
        return {
            "id": post.id,
            "title": post.title,
            "views_count": post.views_count,
            "is_published": post.is_published,
            "created_at": post.created_at.isoformat(),
        }
```

### APIView for Custom Endpoints

```python
from core import APIView
from core.permissions import AllowAny, IsAuthenticated

class HealthView(APIView):
    """Health check endpoint."""
    
    permission_classes = [AllowAny]
    tags = ["System"]
    
    async def get(self, request, **kwargs):
        """GET /health - Health check."""
        return {
            "status": "healthy",
            "version": "1.0.0",
        }

class DashboardView(APIView):
    """Admin dashboard endpoint."""
    
    permission_classes = [IsAuthenticated]
    tags = ["Admin"]
    
    async def get(self, request, db, **kwargs):
        """GET /dashboard - Get dashboard stats."""
        user = request.state.user
        return {
            "user": user.email,
            "posts_count": await Post.objects.using(db).count(),
            "users_count": await User.objects.using(db).count(),
        }
```

### Authentication ViewSet (Complete Example)

```python
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from core import ModelViewSet, action
from core.permissions import AllowAny, IsAuthenticated
from core.auth import (
    create_access_token,
    create_refresh_token,
    verify_token,
    login_required,
)

from src.apps.users.models import User
from src.apps.users.schemas import (
    UserRegisterInput,
    UserOutput,
    LoginInput,
    TokenResponse,
    RefreshTokenInput,
    ChangePasswordInput,
)
from src.api.config import settings


class AuthViewSet(ModelViewSet):
    """
    Authentication ViewSet - 100% DRF pattern.
    
    All authentication endpoints via @action.
    No FastAPI decorators needed.
    
    Endpoints:
        POST /auth/register/  - Register new user
        POST /auth/login/     - Login and get tokens
        POST /auth/refresh/   - Refresh access token
        GET  /auth/me/        - Get current user profile
        POST /auth/password/  - Change password
        POST /auth/logout/    - Logout (invalidate token)
    """
    
    model = User
    input_schema = UserRegisterInput
    output_schema = UserOutput
    tags = ["Authentication"]
    permission_classes = [AllowAny]
    
    # Disable default CRUD (we only use custom actions)
    async def list(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def retrieve(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def create(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def update(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    async def destroy(self, *args, **kwargs):
        raise HTTPException(status_code=404, detail="Not found")
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def register(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /auth/register/
        
        Register a new user account.
        
        Request body:
            - email: User email (unique)
            - password: Strong password (min 8 chars, upper, lower, digit)
            - first_name: Optional first name
            - last_name: Optional last name
        
        Returns:
            Created user data (without password)
        """
        body = await request.json()
        data = UserRegisterInput.model_validate(body)
        
        # Check if email exists
        existing = await User.get_by_email(data.email, db)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Create user
        user = await User.create_user(
            email=data.email,
            password=data.password,
            db=db,
            first_name=data.first_name,
            last_name=data.last_name,
        )
        
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def login(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /auth/login/
        
        Authenticate and get access tokens.
        
        Request body:
            - email: User email
            - password: User password
        
        Returns:
            - access_token: JWT access token
            - refresh_token: JWT refresh token
            - token_type: "bearer"
            - expires_in: Token expiration in seconds
        """
        body = await request.json()
        data = LoginInput.model_validate(body)
        
        # Authenticate
        user = await User.authenticate(data.email, data.password, db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Generate tokens
        access_token = create_access_token({"sub": str(user.id), "email": user.email})
        refresh_token = create_refresh_token({"sub": str(user.id)})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.auth_access_token_expire_minutes * 60,
        ).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[AllowAny])
    async def refresh(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /auth/refresh/
        
        Refresh access token using refresh token.
        
        Request body:
            - refresh_token: Valid refresh token
        
        Returns:
            New access and refresh tokens
        """
        body = await request.json()
        data = RefreshTokenInput.model_validate(body)
        
        # Verify refresh token
        payload = verify_token(data.refresh_token, token_type="refresh")
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
        # Generate new tokens
        access_token = create_access_token({"sub": payload["sub"]})
        refresh_token = create_refresh_token({"sub": payload["sub"]})
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.auth_access_token_expire_minutes * 60,
        ).model_dump()
    
    @action(methods=["GET"], detail=False, permission_classes=[IsAuthenticated])
    async def me(self, request: Request, db: AsyncSession, **kwargs):
        """
        GET /auth/me/
        
        Get current authenticated user profile.
        
        Requires: Authorization header with Bearer token
        
        Returns:
            Current user data
        """
        user = await login_required(request, db)
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=False, permission_classes=[IsAuthenticated])
    async def password(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /auth/password/
        
        Change current user password.
        
        Requires: Authorization header with Bearer token
        
        Request body:
            - current_password: Current password
            - new_password: New strong password
        
        Returns:
            Success message
        """
        body = await request.json()
        data = ChangePasswordInput.model_validate(body)
        
        # Get current user
        user = await login_required(request, db)
        
        # Verify current password
        if not user.check_password(data.current_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        
        # Update password
        user.set_password(data.new_password)
        await user.save(db)
        
        return {"message": "Password changed successfully"}
```

### ReadOnlyModelViewSet

```python
from core.views import ReadOnlyModelViewSet

class PublicPostViewSet(ReadOnlyModelViewSet):
    """ViewSet for read-only access (list and retrieve only)."""
    
    model = Post
    output_schema = PostOutput
    permission_classes = [AllowAny]
    
    def get_queryset(self, db):
        return Post.objects.using(db).filter(is_published=True)
```

---

## Routing

### AutoRouter with ViewSets

```python
# src/apps/posts/routes.py
from core import AutoRouter
from src.apps.posts.views import PostViewSet

# Create router and register ViewSet
posts_router = AutoRouter(prefix="/posts", tags=["Posts"])
posts_router.register("", PostViewSet, basename="post")
```

### Main Application

```python
# src/main.py
from core import CoreApp, AutoRouter, APIView
from core.datetime import configure_datetime
from core.auth import configure_auth
from core.permissions import AllowAny

from src.api.config import settings
from src.apps.users.routes import users_router, auth_router
from src.apps.posts.routes import posts_router


# Configure DateTime to use UTC globally
configure_datetime(
    default_timezone=settings.timezone,
    use_aware_datetimes=settings.use_tz,
)

# Configure authentication system
configure_auth(
    secret_key=settings.secret_key,
    access_token_expire_minutes=settings.auth_access_token_expire_minutes,
    refresh_token_expire_days=settings.auth_refresh_token_expire_days,
    password_hasher=settings.auth_password_hasher,
)


# Health check using APIView (DRF-style)
class HealthView(APIView):
    permission_classes = [AllowAny]
    tags = ["System"]
    
    async def get(self, request, **kwargs):
        return {"status": "healthy", "version": settings.app_version}


# Main API router
api_router = AutoRouter(prefix=settings.api_prefix)

# Include app routers
api_router.include_router(users_router)   # /api/v1/users/
api_router.include_router(auth_router)    # /api/v1/auth/
api_router.include_router(posts_router)   # /api/v1/posts/

# Create application
app = CoreApp(
    title=settings.app_name,
    description="API built with Core Framework",
    version=settings.app_version,
    debug=settings.debug,
    routers=[api_router],
)

# Register system views
app.add_api_route("/health", HealthView.as_route("/health")[1], methods=["GET"], tags=["System"])
```

### Auto-Generated Routes

For a ViewSet registered at `/posts`:

| Method | Route | Action | Description |
|--------|-------|--------|-------------|
| GET | /posts/ | list | List all posts |
| POST | /posts/ | create | Create post |
| GET | /posts/{id}/ | retrieve | Get post details |
| PUT | /posts/{id}/ | update | Update post |
| PATCH | /posts/{id}/ | partial_update | Partial update |
| DELETE | /posts/{id}/ | destroy | Delete post |

For custom @action decorators:

| Decorator | Route |
|-----------|-------|
| @action(detail=False) | /posts/{action_name}/ |
| @action(detail=True) | /posts/{id}/{action_name}/ |

---

## Authentication

### Basic Configuration

```python
from core.auth import configure_auth

configure_auth(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
    password_hasher="pbkdf2_sha256",  # or argon2, bcrypt, scrypt
)
```

### Create and Verify Tokens

```python
from core.auth import create_access_token, create_refresh_token, verify_token

# Create tokens
access_token = create_access_token({"sub": str(user.id), "email": user.email})
refresh_token = create_refresh_token({"sub": str(user.id)})

# Verify token
payload = verify_token(access_token, token_type="access")
if payload:
    user_id = payload["sub"]
```

### Protect Routes with Permissions

```python
from core.permissions import IsAuthenticated, AllowAny

class ProtectedViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated],
        "destroy": [IsAuthenticated],
    }
```

---

## Custom Authentication Backends

Core Framework provides a pluggable authentication system. You can create custom backends for authentication, password hashing, tokens, and permissions.

### Custom Authentication Backend

```python
# src/auth/backends.py
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth import AuthBackend, register_auth_backend

class LDAPAuthBackend(AuthBackend):
    """
    Custom LDAP authentication backend.
    
    Authenticates users against an LDAP server.
    """
    
    name = "ldap"
    
    def __init__(self, ldap_server: str, base_dn: str):
        self.ldap_server = ldap_server
        self.base_dn = base_dn
    
    async def authenticate(
        self,
        request: Any,
        db: AsyncSession,
        **credentials,
    ) -> Any | None:
        """
        Authenticate user against LDAP.
        
        Args:
            request: HTTP request
            db: Database session
            **credentials: username, password
        
        Returns:
            User object if authenticated, None otherwise
        """
        username = credentials.get("username")
        password = credentials.get("password")
        
        if not username or not password:
            return None
        
        # Connect to LDAP and verify credentials
        # (implement your LDAP logic here)
        import ldap3
        
        server = ldap3.Server(self.ldap_server)
        user_dn = f"uid={username},{self.base_dn}"
        
        try:
            conn = ldap3.Connection(server, user_dn, password, auto_bind=True)
            conn.unbind()
        except ldap3.core.exceptions.LDAPException:
            return None
        
        # Get or create local user
        from src.apps.users.models import User
        
        user = await User.objects.using(db).get_or_none(username=username)
        if not user:
            # Create user from LDAP data
            user = User(
                username=username,
                email=f"{username}@company.com",
                is_active=True,
            )
            await user.save(db)
        
        return user
    
    async def get_user(self, user_id: int, db: AsyncSession) -> Any | None:
        """Get user by ID."""
        from src.apps.users.models import User
        return await User.objects.using(db).get_or_none(id=user_id)


# Register the backend
register_auth_backend(LDAPAuthBackend(
    ldap_server="ldap://ldap.company.com",
    base_dn="ou=users,dc=company,dc=com",
))
```

### Custom Password Hasher

```python
# src/auth/hashers.py
from core.auth import PasswordHasher, register_password_hasher

class CustomHasher(PasswordHasher):
    """
    Custom password hasher using a specific algorithm.
    """
    
    name = "custom_sha512"
    
    def hash(self, password: str) -> str:
        """Hash a password."""
        import hashlib
        import secrets
        
        salt = secrets.token_hex(16)
        hashed = hashlib.sha512((salt + password).encode()).hexdigest()
        return f"{salt}${hashed}"
    
    def verify(self, password: str, hashed: str) -> bool:
        """Verify a password against a hash."""
        import hashlib
        
        try:
            salt, stored_hash = hashed.split("$")
            computed_hash = hashlib.sha512((salt + password).encode()).hexdigest()
            return computed_hash == stored_hash
        except ValueError:
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """Check if password needs rehashing."""
        return False


# Register the hasher
register_password_hasher(CustomHasher())

# Use in config
# AUTH_PASSWORD_HASHER=custom_sha512
```

### Available Password Hashers

```python
from core.auth import (
    PBKDF2Hasher,    # Default, secure, no extra dependencies
    Argon2Hasher,    # Most secure, requires argon2-cffi
    BCryptHasher,    # Popular, requires bcrypt
    ScryptHasher,    # Memory-hard, built-in Python
)

# Configure in .env
AUTH_PASSWORD_HASHER=pbkdf2_sha256  # or argon2, bcrypt, scrypt
```

---

## Custom Token Types

### Custom Token Backend

```python
# src/auth/tokens.py
from typing import Any
from datetime import timedelta
from core.auth import TokenBackend, register_token_backend
from core.datetime import timezone

class CustomJWTBackend(TokenBackend):
    """
    Custom JWT backend with additional claims.
    """
    
    name = "custom_jwt"
    
    def __init__(self, secret_key: str, algorithm: str = "HS512"):
        self.secret_key = secret_key
        self.algorithm = algorithm
    
    def create_token(
        self,
        payload: dict[str, Any],
        token_type: str = "access",
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a JWT token with custom claims."""
        import jwt
        
        now = timezone.now()
        
        # Set expiration
        if expires_delta:
            expire = now + expires_delta
        elif token_type == "access":
            expire = now + timedelta(minutes=30)
        else:
            expire = now + timedelta(days=7)
        
        # Build token payload
        token_payload = {
            **payload,
            "type": token_type,
            "iat": now,
            "exp": expire,
            "iss": "my-app",  # Custom issuer
            "aud": "my-app-users",  # Custom audience
        }
        
        return jwt.encode(token_payload, self.secret_key, algorithm=self.algorithm)
    
    def decode_token(self, token: str) -> dict[str, Any] | None:
        """Decode and validate a JWT token."""
        import jwt
        
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                audience="my-app-users",
                issuer="my-app",
            )
            return payload
        except jwt.PyJWTError:
            return None
    
    def verify_token(
        self,
        token: str,
        token_type: str = "access",
    ) -> dict[str, Any] | None:
        """Verify token type and validity."""
        payload = self.decode_token(token)
        
        if not payload:
            return None
        
        if payload.get("type") != token_type:
            return None
        
        return payload


# Register the backend
from src.api.config import settings

register_token_backend(CustomJWTBackend(
    secret_key=settings.secret_key,
    algorithm="HS512",
))
```

### API Key Authentication

```python
# src/auth/api_key.py
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth import AuthBackend, register_auth_backend

class APIKeyAuthBackend(AuthBackend):
    """
    API Key authentication backend.
    
    Authenticates requests using X-API-Key header.
    """
    
    name = "api_key"
    
    async def authenticate(
        self,
        request: Any,
        db: AsyncSession,
        **credentials,
    ) -> Any | None:
        """Authenticate using API key."""
        # Get API key from header
        api_key = request.headers.get("X-API-Key")
        
        if not api_key:
            return None
        
        # Look up API key in database
        from src.apps.api_keys.models import APIKey
        
        key_obj = await APIKey.objects.using(db).get_or_none(
            key=api_key,
            is_active=True,
        )
        
        if not key_obj:
            return None
        
        # Update last used
        key_obj.last_used_at = timezone.now()
        await key_obj.save(db)
        
        # Return associated user
        return key_obj.user
    
    async def get_user(self, user_id: int, db: AsyncSession) -> Any | None:
        from src.apps.users.models import User
        return await User.objects.using(db).get_or_none(id=user_id)


# Register
register_auth_backend(APIKeyAuthBackend())
```

### OAuth2 / Social Authentication

```python
# src/auth/oauth.py
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth import AuthBackend, register_auth_backend
import httpx

class GoogleOAuthBackend(AuthBackend):
    """
    Google OAuth2 authentication backend.
    """
    
    name = "google_oauth"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
    
    async def authenticate(
        self,
        request: Any,
        db: AsyncSession,
        **credentials,
    ) -> Any | None:
        """Authenticate using Google OAuth token."""
        google_token = credentials.get("google_token")
        
        if not google_token:
            return None
        
        # Verify token with Google
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {google_token}"},
            )
            
            if response.status_code != 200:
                return None
            
            google_user = response.json()
        
        # Get or create user
        from src.apps.users.models import User
        
        user = await User.objects.using(db).get_or_none(email=google_user["email"])
        
        if not user:
            user = User(
                email=google_user["email"],
                first_name=google_user.get("given_name", ""),
                last_name=google_user.get("family_name", ""),
                avatar_url=google_user.get("picture"),
                is_active=True,
            )
            user.set_unusable_password()
            await user.save(db)
        
        return user
    
    async def get_user(self, user_id: int, db: AsyncSession) -> Any | None:
        from src.apps.users.models import User
        return await User.objects.using(db).get_or_none(id=user_id)


# Register
from src.api.config import settings

register_auth_backend(GoogleOAuthBackend(
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
))
```

### Using Multiple Auth Backends in ViewSet

```python
from core import ModelViewSet, action
from core.auth import get_auth_backend

class MultiAuthViewSet(ModelViewSet):
    """ViewSet supporting multiple authentication methods."""
    
    @action(methods=["POST"], detail=False)
    async def login_password(self, request: Request, db: AsyncSession, **kwargs):
        """Login with email/password."""
        body = await request.json()
        
        backend = get_auth_backend("default")
        user = await backend.authenticate(
            request, db,
            email=body["email"],
            password=body["password"],
        )
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return self._generate_tokens(user)
    
    @action(methods=["POST"], detail=False)
    async def login_google(self, request: Request, db: AsyncSession, **kwargs):
        """Login with Google OAuth."""
        body = await request.json()
        
        backend = get_auth_backend("google_oauth")
        user = await backend.authenticate(
            request, db,
            google_token=body["google_token"],
        )
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid Google token")
        
        return self._generate_tokens(user)
    
    @action(methods=["POST"], detail=False)
    async def login_api_key(self, request: Request, db: AsyncSession, **kwargs):
        """Login with API key."""
        backend = get_auth_backend("api_key")
        user = await backend.authenticate(request, db)
        
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API key")
        
        return self._generate_tokens(user)
    
    def _generate_tokens(self, user):
        from core.auth import create_access_token, create_refresh_token
        from src.api.config import settings
        
        return {
            "access_token": create_access_token({"sub": str(user.id)}),
            "refresh_token": create_refresh_token({"sub": str(user.id)}),
            "token_type": "bearer",
            "expires_in": settings.auth_access_token_expire_minutes * 60,
        }
```

---

## Custom User Model

### Extending AbstractUser

```python
# src/apps/users/models.py
from sqlalchemy.orm import Mapped, relationship
from core import Model, Field
from core.auth import AbstractUser, PermissionsMixin
from core.datetime import DateTime

class User(AbstractUser, PermissionsMixin):
    """Custom user with additional fields."""
    
    __tablename__ = "users"
    
    # Additional fields
    username: Mapped[str] = Field.string(max_length=50, unique=True)
    phone: Mapped[str | None] = Field.string(max_length=20, nullable=True)
    avatar_url: Mapped[str | None] = Field.string(max_length=500, nullable=True)
    bio: Mapped[str | None] = Field.text(nullable=True)
    birth_date: Mapped[DateTime | None] = Field.datetime(nullable=True)
    
    # Relationships
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="author")
    
    # Configuration
    USERNAME_FIELD = "email"  # Field used for login
    REQUIRED_FIELDS = ["username"]  # Required fields besides email
```

### Inherited Fields from AbstractUser

AbstractUser includes:

- `id`: Primary key
- `email`: Unique email (used for login)
- `password_hash`: Password hash
- `is_active`: Whether user is active
- `is_staff`: Whether user can access admin
- `is_superuser`: Whether user has all permissions
- `date_joined`: Creation timestamp
- `last_login`: Last login timestamp

### PermissionsMixin Fields

PermissionsMixin adds:

- `groups`: Relationship with groups
- `user_permissions`: Direct permissions

### Available Methods

```python
# Create user
user = await User.create_user(
    email="user@example.com",
    password="password123",
    db=db,
    username="user",
    phone="+1234567890",
)

# Create superuser
admin = await User.create_superuser(
    email="admin@example.com",
    password="password123",
    db=db,
    username="admin",
)

# Authenticate
user = await User.authenticate("user@example.com", "password123", db)

# Get by email
user = await User.get_by_email("user@example.com", db)

# Verify/set password
user.set_password("new_password")
is_valid = user.check_password("test_password")

# Check permissions
if user.has_perm("posts.delete"):
    # ...

if user.has_perms(["posts.create", "posts.edit"]):
    # ...

# Get all permissions
perms = user.get_all_permissions()  # {"posts.create", "posts.edit", ...}

# Groups
if user.is_in_group("editors"):
    # ...

groups = user.get_group_names()  # ["editors", "moderators"]

# Manage groups
await user.add_to_group("editors", db)
await user.remove_from_group("editors", db)
await user.set_groups(["editors", "moderators"], db)

# Manage direct permissions
await user.add_permission("posts.delete", db)
await user.remove_permission("posts.delete", db)
await user.set_permissions(["posts.create", "posts.edit"], db)
```

---

## Permissions

### Available Permission Classes

```python
from core.permissions import (
    AllowAny,           # Allow any access
    IsAuthenticated,    # Require authentication
    IsAdmin,            # Require is_superuser=True
    IsOwner,            # Check if user owns the object
    HasPermission,      # Check specific permission
    IsInGroup,          # Check if in group
    IsSuperUser,        # Alias for IsAdmin
    IsStaff,            # Require is_staff=True
)
```

### Using in ViewSets

```python
class PostViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated]
    
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated, IsOwner],
        "destroy": [IsAuthenticated, HasPermission("posts.delete")],
    }
```

### Custom Permission

```python
from core.permissions import Permission

class IsVerifiedUser(Permission):
    """Allow only verified users."""
    
    async def has_permission(self, request, view) -> bool:
        user = getattr(request.state, "user", None)
        if not user:
            return False
        return getattr(user, "is_verified", False)
    
    async def has_object_permission(self, request, view, obj) -> bool:
        return await self.has_permission(request, view)

# Usage
class VerifiedOnlyViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, IsVerifiedUser]
```

### Groups and Permissions in Database

```python
from core.auth import Group, Permission

# Create group
editors = await Group.get_or_create("editors", db=db)

# Add permissions to group
await editors.add_permission("posts.create", db)
await editors.add_permission("posts.edit", db)
await editors.add_permission("posts.delete", db)

# Or set all at once
await editors.set_permissions([
    "posts.create",
    "posts.edit",
    "posts.delete",
    "comments.moderate",
], db)

# Check group permission
if editors.has_permission("posts.delete"):
    # ...

# Create permission
perm = await Permission.get_or_create(
    codename="posts.feature",
    name="Can feature posts",
    description="Allows featuring posts on homepage",
    db=db,
)
```

---

## Database

### Configuration

```python
# Via .env
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname

# SQLite (development)
DATABASE_URL=sqlite+aiosqlite:///./app.db

# PostgreSQL (production)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/dbname

# MySQL
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/dbname
```

### Using CoreApp (Recommended)

```python
from core import CoreApp

app = CoreApp(
    title="My API",
    database_url="sqlite+aiosqlite:///./app.db",
)

# CoreApp automatically manages:
# - Database initialization on startup
# - Closing on shutdown
# - Session dependency injection
```

---

## Migrations

### CLI Commands

```bash
# Create migration
core makemigrations --name add_phone_to_users

# Apply migrations
core migrate

# Check pending migrations
core check

# Rollback last migration
core migrate --rollback

# List migrations
core showmigrations

# Reset database (WARNING: destroys all data)
core reset_db
```

### Migration Structure

```python
# migrations/0002_add_phone_to_users.py
from core.migrations import Migration, AddColumn

class Migration0002(Migration):
    dependencies = ["0001_initial"]
    
    operations = [
        AddColumn(
            table_name="users",
            column_name="phone",
            column_type="VARCHAR(20)",
            nullable=True,
        ),
    ]
```

### Available Operations

```python
from core.migrations import (
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    CreateIndex,
    DropIndex,
    AddForeignKey,
    DropForeignKey,
    RunSQL,
    RunPython,
)
```

---

## Project Structure

```
my-project/
  src/
    __init__.py
    main.py                 # Main application
    apps/
      __init__.py
      users/
        __init__.py
        models.py           # App models
        schemas.py          # Input/Output schemas
        views.py            # ViewSets and APIViews
        services.py         # Business logic
        routes.py           # App routes
        tests/
          __init__.py
          test_users.py
      posts/
        __init__.py
        models.py
        schemas.py
        views.py
        services.py
        routes.py
        tests/
    api/
      __init__.py
      config.py             # Application settings
  migrations/
    __init__.py
    0001_initial.py
  tests/
    __init__.py
    conftest.py
  .env
  .env.example
  pyproject.toml
  README.md
```

---

## Running

```bash
# Development
core run

# Production
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Access

- API: http://localhost:8000
- Documentation: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Enterprise Features (v0.3.0+)

Core Framework includes enterprise-grade features for scaling applications:

- **Messaging**: Kafka, Redis Streams, RabbitMQ
- **Background Tasks**: @task, @periodic_task decorators
- **Deployment**: Docker, PM2, Kubernetes generators

### Installation

```bash
# Install with messaging support
pip install "core-framework[messaging]"

# Or specific brokers
pip install "core-framework[kafka]"
pip install "core-framework[redis]"
pip install "core-framework[rabbitmq]"

# Full enterprise package
pip install "core-framework[enterprise]"
```

---

## Messaging System

The messaging system provides event-driven architecture with plug-and-play brokers.

### Configuration

```env
# .env
MESSAGE_BROKER=kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Or Redis
MESSAGE_BROKER=redis
REDIS_URL=redis://localhost:6379/0

# Or RabbitMQ
MESSAGE_BROKER=rabbitmq
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
```

### Event Decorator

Automatically emit events after ViewSet actions:

```python
from core import ModelViewSet, action
from core.messaging import event

class UserViewSet(ModelViewSet):
    model = User
    
    @action(methods=["POST"], detail=False)
    @event("user.created", topic="user-events")
    async def register(self, request, db, **kwargs):
        body = await request.json()
        user = await User.create_user(
            email=body["email"],
            password=body["password"],
            db=db,
        )
        return UserOutput.model_validate(user).model_dump()
        # Event automatically emitted with return value as data
```

### Consumer Decorator

Define event consumers with DRF-style decorators:

```python
from core.messaging import consumer, on_event

@consumer("order-service", topics=["user-events", "payment-events"])
class OrderEventsConsumer:
    
    @on_event("user.created")
    async def handle_user_created(self, event, db):
        """Create welcome order when user is created."""
        await Order.objects.create(
            user_id=event.data["id"],
            type="welcome",
            status="pending",
            db=db,
        )
    
    @on_event("payment.completed")
    async def handle_payment_completed(self, event, db):
        """Mark order as paid."""
        await Order.objects.filter(
            id=event.data["order_id"]
        ).update(status="paid", db=db)
```

### Manual Event Publishing

```python
from core.messaging import publish_event

# Publish event directly
await publish_event(
    "user.updated",
    data={"id": 1, "email": "new@example.com"},
    topic="user-events",
)
```

### CLI Commands

```bash
# Start event consumer
core consumer --group order-service --topic user-events

# Manage Kafka topics
core topics list
core topics create user-events --partitions 3
core topics delete old-events
```

---

## Background Tasks

The task system provides background job processing integrated with the messaging system.

### Task Decorator

Define background tasks:

```python
from core.tasks import task

@task(queue="emails", retry=3, timeout=300)
async def send_email(to: str, subject: str, body: str):
    """Send email in background."""
    await EmailService.send(to, subject, body)

# Execute immediately (blocking)
await send_email("user@example.com", "Hello", "World")

# Schedule for background execution
task_id = await send_email.delay("user@example.com", "Hello", "World")

# Schedule with delay
task_id = await send_email.apply_async(
    args=("user@example.com", "Hello", "World"),
    countdown=60,  # Execute after 60 seconds
)
```

### Periodic Task Decorator

Define scheduled/periodic tasks:

```python
from core.tasks import periodic_task

# Cron expression
@periodic_task(cron="0 0 * * *")  # Every day at midnight
async def daily_cleanup():
    """Clean up expired sessions."""
    await Session.objects.filter(expired=True).delete()

# Interval
@periodic_task(interval=300)  # Every 5 minutes
async def sync_external_data():
    """Sync data from external API."""
    await ExternalAPI.sync()

# Weekly report
@periodic_task(cron="0 9 * * 1")  # Every Monday at 9 AM
async def weekly_report():
    """Generate weekly report."""
    await ReportService.generate_weekly()
```

### Cron Expression Format

```
# ┌───────────── minute (0 - 59)
# │ ┌───────────── hour (0 - 23)
# │ │ ┌───────────── day of month (1 - 31)
# │ │ │ ┌───────────── month (1 - 12)
# │ │ │ │ ┌───────────── day of week (0 - 6) (Sunday = 0)
# │ │ │ │ │
# * * * * *

Examples:
  "0 0 * * *"     # Every day at midnight
  "*/5 * * * *"   # Every 5 minutes
  "0 9 * * 1"     # Every Monday at 9 AM
  "0 0 1 * *"     # First day of every month
  "0 */2 * * *"   # Every 2 hours
```

### CLI Commands

```bash
# Start task worker
core worker --queue default --concurrency 4

# Start multiple queues
core worker --queue default --queue emails --queue reports

# Start task scheduler (for periodic tasks)
core scheduler

# List registered tasks
core tasks
```

### Task Configuration

```env
# .env
TASK_DEFAULT_QUEUE=default
TASK_WORKER_CONCURRENCY=4
TASK_DEFAULT_RETRY=3
TASK_DEFAULT_TIMEOUT=300
```

---

## Deployment

Generate deployment files for different environments.

### Docker

```bash
# Generate Docker files
core deploy docker

# Generated files:
#   - docker-compose.yml
#   - Dockerfile
#   - .dockerignore
```

Start with Docker:

```bash
docker-compose up -d

# Scale workers
docker-compose up -d --scale worker=4
```

### PM2

```bash
# Generate PM2 ecosystem file
core deploy pm2

# Generated: ecosystem.config.js
```

Start with PM2:

```bash
pm2 start ecosystem.config.js
pm2 status
pm2 logs
```

### Kubernetes

```bash
# Generate Kubernetes manifests
core deploy k8s

# Generated files in k8s/:
#   - namespace.yaml
#   - configmap.yaml
#   - secrets.yaml
#   - api-deployment.yaml
#   - api-service.yaml
#   - worker-deployment.yaml
#   - scheduler-deployment.yaml
#   - ingress.yaml
#   - hpa.yaml
#   - kustomization.yaml
```

Deploy to Kubernetes:

```bash
kubectl apply -f k8s/

# Or with kustomize
kubectl apply -k k8s/
```

### All Deployment Files

```bash
# Generate all deployment files at once
core deploy all
```

---

## Custom Message Brokers

### Using Redis Streams

```python
from core.messaging.redis import RedisBroker, RedisProducer

# Configure
broker = RedisBroker(redis_url="redis://localhost:6379/0")
await broker.connect()

# Publish
await broker.publish("events", {"type": "test"})

# Subscribe
async def handler(message):
    print(f"Received: {message}")

await broker.subscribe(["events"], "my-group", handler)
```

### Using RabbitMQ

```python
from core.messaging.rabbitmq import RabbitMQBroker

broker = RabbitMQBroker(url="amqp://guest:guest@localhost:5672/")
await broker.connect()

# Publish with routing key
await broker.publish("user.created", {"id": 1})

# Subscribe with pattern
await broker.subscribe(["user.*"], "order-service", handler)
```

### Custom Broker Implementation

```python
from core.messaging.base import MessageBroker

class CustomBroker(MessageBroker):
    name = "custom"
    
    async def connect(self) -> None:
        # Connect to your broker
        pass
    
    async def disconnect(self) -> None:
        # Disconnect
        pass
    
    async def publish(self, topic, message, key=None, headers=None) -> None:
        # Publish message
        pass
    
    async def subscribe(self, topics, group_id, handler) -> None:
        # Subscribe to topics
        pass
    
    async def create_topic(self, topic, partitions=1, replication_factor=1) -> None:
        # Create topic
        pass
    
    async def delete_topic(self, topic) -> None:
        # Delete topic
        pass
    
    async def list_topics(self) -> list[str]:
        # List topics
        return []
```

---

## Architecture Example

Complete microservices architecture with Core Framework:

```
                    +------------------+
                    |   Load Balancer  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v----+  +------v------+  +----v--------+
     |  API Pod 1  |  |  API Pod 2  |  |  API Pod 3  |
     +------+------+  +------+------+  +------+------+
            |                |                |
            +----------------+----------------+
                             |
                    +--------v--------+
                    |     Kafka       |
                    +--------+--------+
                             |
         +-------------------+-------------------+
         |                   |                   |
+--------v--------+ +--------v--------+ +--------v--------+
|  Worker Pod 1   | |  Worker Pod 2   | |  Scheduler Pod  |
+-----------------+ +-----------------+ +-----------------+
         |                   |                   |
         +-------------------+-------------------+
                             |
                    +--------v--------+
                    |   PostgreSQL    |
                    +-----------------+
```

### Service Communication

```python
# User Service (API 1)
@consumer("user-service", topics=["order-events"])
class OrderEventsConsumer:
    @on_event("order.created")
    async def handle_order_created(self, event, db):
        # Update user's order count
        await User.objects.filter(
            id=event.data["user_id"]
        ).update(order_count=User.order_count + 1, db=db)

# Order Service (API 2)
class OrderViewSet(ModelViewSet):
    model = Order
    
    @action(methods=["POST"], detail=False)
    @event("order.created", topic="order-events")
    async def create_order(self, request, db, **kwargs):
        # Create order and emit event
        order = await Order.objects.create(...)
        return OrderOutput.model_validate(order).model_dump()
```

---

## Best Practices

### 1. Event Naming

Use dot notation for event names:

```python
# Good
@event("user.created")
@event("order.payment.completed")
@event("notification.email.sent")

# Bad
@event("userCreated")
@event("ORDER_CREATED")
```

### 2. Idempotent Handlers

Make event handlers idempotent:

```python
@on_event("payment.completed")
async def handle_payment(self, event, db):
    # Check if already processed
    existing = await Order.objects.filter(
        id=event.data["order_id"],
        payment_processed=True,
    ).first(db=db)
    
    if existing:
        return  # Already processed
    
    # Process payment
    await Order.objects.filter(
        id=event.data["order_id"]
    ).update(payment_processed=True, db=db)
```

### 3. Error Handling

Use retry and dead letter queues:

```python
@task(queue="emails", retry=3, retry_delay=60)
async def send_email(to: str, subject: str, body: str):
    try:
        await EmailService.send(to, subject, body)
    except TemporaryError:
        raise  # Will retry
    except PermanentError:
        # Log and don't retry
        logger.error(f"Failed to send email to {to}")
```

### 4. Monitoring

Use structured logging:

```python
import logging

logger = logging.getLogger(__name__)

@on_event("user.created")
async def handle_user_created(self, event, db):
    logger.info(
        "Processing user.created event",
        extra={
            "event_id": event.id,
            "user_id": event.data["id"],
        }
    )
```
