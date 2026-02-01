"""
Models da aplicação de exemplo.

Demonstra:
- Definição de campos tipados
- Relacionamentos
- Hooks de ciclo de vida
- Métodos customizados
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Mapped, relationship

from core.models import Model, Field

if TYPE_CHECKING:
    from collections.abc import Sequence


class User(Model):
    """
    Model de usuário.
    
    Exemplo de uso:
        # Criar usuário
        user = await User.objects.using(db).create(
            email="user@example.com",
            name="John Doe",
            password_hash="hashed_password",
        )
        
        # Buscar usuário
        user = await User.objects.using(db).get(id=1)
        
        # Filtrar usuários
        active_users = await User.objects.using(db)\\
            .filter(is_active=True)\\
            .order_by("-created_at")\\
            .all()
    """
    
    __tablename__ = "users"
    
    id: Mapped[int] = Field.pk()
    email: Mapped[str] = Field.string(max_length=255, unique=True, index=True)
    name: Mapped[str] = Field.string(max_length=100)
    password_hash: Mapped[str] = Field.string(max_length=255)
    is_active: Mapped[bool] = Field.boolean(default=True, index=True)
    is_admin: Mapped[bool] = Field.boolean(default=False)
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[datetime] = Field.datetime(auto_now=True)
    
    # Relacionamento com posts
    posts: Mapped[list["Post"]] = relationship(
        "Post",
        back_populates="author",
        lazy="selectin",
    )
    
    async def before_create(self) -> None:
        """Hook executado antes de criar o usuário."""
        # Normaliza o email
        self.email = self.email.lower().strip()
    
    def verify_password(self, password: str) -> bool:
        """Verifica se a senha está correta."""
        # Em produção, use bcrypt ou similar
        import hashlib
        return self.password_hash == hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Gera hash da senha."""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()


class Post(Model):
    """
    Model de post/artigo.
    
    Demonstra relacionamento com User.
    """
    
    __tablename__ = "posts"
    
    id: Mapped[int] = Field.pk()
    title: Mapped[str] = Field.string(max_length=200)
    content: Mapped[str] = Field.text()
    is_published: Mapped[bool] = Field.boolean(default=False, index=True)
    views_count: Mapped[int] = Field.integer(default=0)
    author_id: Mapped[int] = Field.foreign_key("users.id")
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[datetime] = Field.datetime(auto_now=True)
    
    # Relacionamento com autor
    author: Mapped["User"] = relationship(
        "User",
        back_populates="posts",
        lazy="selectin",
    )
    
    # Relacionamento com comentários
    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="post",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    
    async def increment_views(self, session) -> None:
        """Incrementa o contador de visualizações."""
        self.views_count += 1
        await self.save(session)


class Comment(Model):
    """
    Model de comentário.
    
    Demonstra relacionamento many-to-one.
    """
    
    __tablename__ = "comments"
    
    id: Mapped[int] = Field.pk()
    content: Mapped[str] = Field.text()
    post_id: Mapped[int] = Field.foreign_key("posts.id")
    author_id: Mapped[int] = Field.foreign_key("users.id")
    created_at: Mapped[datetime] = Field.datetime(auto_now_add=True)
    
    # Relacionamentos
    post: Mapped["Post"] = relationship(
        "Post",
        back_populates="comments",
        lazy="selectin",
    )
    author: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )


class Tag(Model):
    """
    Model de tag para posts.
    
    Exemplo simples sem relacionamentos complexos.
    """
    
    __tablename__ = "tags"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(max_length=50, unique=True)
    slug: Mapped[str] = Field.string(max_length=50, unique=True, index=True)
    
    async def before_create(self) -> None:
        """Gera slug automaticamente."""
        if not self.slug:
            self.slug = self.name.lower().replace(" ", "-")
