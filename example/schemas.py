"""
Schemas (Serializers) da aplicação de exemplo.

Demonstra:
- InputSchema para validação de entrada
- OutputSchema para serialização de saída
- Validação customizada
- Campos computados
"""

from datetime import datetime
from typing import Any

from pydantic import EmailStr, field_validator, computed_field

from core.serializers import InputSchema, OutputSchema


# ============================================================
# User Schemas
# ============================================================

class UserCreateInput(InputSchema):
    """Schema para criação de usuário."""
    
    email: EmailStr
    name: str
    password: str
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip()
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdateInput(InputSchema):
    """Schema para atualização de usuário."""
    
    name: str | None = None
    is_active: bool | None = None
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        return v.strip() if v else v


class UserOutput(OutputSchema):
    """Schema de saída para usuário."""
    
    id: int
    email: str
    name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    
    @computed_field
    @property
    def display_name(self) -> str:
        """Nome formatado para exibição."""
        return f"{self.name} ({self.email})"


class UserDetailOutput(UserOutput):
    """Schema de saída detalhado para usuário."""
    
    updated_at: datetime
    posts_count: int = 0


# ============================================================
# Post Schemas
# ============================================================

class PostCreateInput(InputSchema):
    """Schema para criação de post."""
    
    title: str
    content: str
    is_published: bool = False
    
    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        if len(v) < 5:
            raise ValueError("Title must be at least 5 characters")
        if len(v) > 200:
            raise ValueError("Title must be at most 200 characters")
        return v.strip()
    
    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Content must be at least 10 characters")
        return v


class PostUpdateInput(InputSchema):
    """Schema para atualização de post."""
    
    title: str | None = None
    content: str | None = None
    is_published: bool | None = None


class PostOutput(OutputSchema):
    """Schema de saída para post."""
    
    id: int
    title: str
    content: str
    is_published: bool
    views_count: int
    author_id: int
    created_at: datetime
    
    @computed_field
    @property
    def excerpt(self) -> str:
        """Resumo do conteúdo."""
        if len(self.content) <= 100:
            return self.content
        return self.content[:100] + "..."


class PostDetailOutput(PostOutput):
    """Schema de saída detalhado para post."""
    
    updated_at: datetime
    author: UserOutput | None = None


class PostListOutput(OutputSchema):
    """Schema de saída para listagem de posts."""
    
    id: int
    title: str
    excerpt: str
    is_published: bool
    views_count: int
    author_id: int
    created_at: datetime


# ============================================================
# Comment Schemas
# ============================================================

class CommentCreateInput(InputSchema):
    """Schema para criação de comentário."""
    
    content: str
    post_id: int
    
    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Comment must be at least 2 characters")
        if len(v) > 1000:
            raise ValueError("Comment must be at most 1000 characters")
        return v.strip()


class CommentOutput(OutputSchema):
    """Schema de saída para comentário."""
    
    id: int
    content: str
    post_id: int
    author_id: int
    created_at: datetime


class CommentDetailOutput(CommentOutput):
    """Schema de saída detalhado para comentário."""
    
    author: UserOutput | None = None


# ============================================================
# Tag Schemas
# ============================================================

class TagCreateInput(InputSchema):
    """Schema para criação de tag."""
    
    name: str
    slug: str | None = None
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if len(v) < 2:
            raise ValueError("Tag name must be at least 2 characters")
        if len(v) > 50:
            raise ValueError("Tag name must be at most 50 characters")
        return v.strip()


class TagOutput(OutputSchema):
    """Schema de saída para tag."""
    
    id: int
    name: str
    slug: str


# ============================================================
# Auth Schemas
# ============================================================

class LoginInput(InputSchema):
    """Schema para login."""
    
    email: EmailStr
    password: str


class TokenOutput(OutputSchema):
    """Schema de saída para token."""
    
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RegisterInput(UserCreateInput):
    """Schema para registro (mesmo que criação de usuário)."""
    pass
