"""
Views e ViewSets da aplicação de exemplo.

Demonstra:
- ModelViewSet para CRUD automático
- Permissões por action
- Actions customizadas
- APIView para endpoints específicos
"""

from typing import Any

from fastapi import Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.views import ModelViewSet, ReadOnlyModelViewSet, APIView, action
from core.permissions import (
    Permission,
    IsAuthenticated,
    IsAuthenticatedOrReadOnly,
    IsAdmin,
    IsOwner,
    AllowAny,
)
from core.dependencies import get_db

from example.models import User, Post, Comment, Tag
from example.schemas import (
    UserCreateInput,
    UserUpdateInput,
    UserOutput,
    UserDetailOutput,
    PostCreateInput,
    PostUpdateInput,
    PostOutput,
    PostDetailOutput,
    CommentCreateInput,
    CommentOutput,
    CommentDetailOutput,
    TagCreateInput,
    TagOutput,
)


# ============================================================
# Permissões Customizadas
# ============================================================

class IsPostAuthor(Permission):
    """Permite acesso apenas ao autor do post."""
    
    message = "You can only modify your own posts"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        return True
    
    async def has_object_permission(
        self,
        request: Request,
        view: Any = None,
        obj: Any = None,
    ) -> bool:
        if obj is None:
            return True
        
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        return obj.author_id == user.id


class IsCommentAuthor(Permission):
    """Permite acesso apenas ao autor do comentário."""
    
    message = "You can only modify your own comments"
    
    async def has_permission(
        self,
        request: Request,
        view: Any = None,
    ) -> bool:
        return True
    
    async def has_object_permission(
        self,
        request: Request,
        view: Any = None,
        obj: Any = None,
    ) -> bool:
        if obj is None:
            return True
        
        user = getattr(request.state, "user", None)
        if user is None:
            return False
        
        return obj.author_id == user.id


# ============================================================
# User ViewSet
# ============================================================

class UserViewSet(ModelViewSet[User, UserCreateInput, UserOutput]):
    """
    ViewSet para usuários.
    
    - list: Apenas admins
    - retrieve: Usuário autenticado (próprio perfil) ou admin
    - create: Público (registro)
    - update/delete: Próprio usuário ou admin
    """
    
    model = User
    input_schema = UserCreateInput
    output_schema = UserOutput
    tags = ["users"]
    
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "list": [IsAdmin],
        "create": [AllowAny],
        "retrieve": [IsAuthenticated],
        "update": [IsAuthenticated],
        "partial_update": [IsAuthenticated],
        "destroy": [IsAdmin],
    }
    
    async def create(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Cria usuário com hash de senha."""
        await self.check_permissions(request, "create")
        
        validated = UserCreateInput.model_validate(data)
        
        # Verifica se email já existe
        existing = await User.objects.using(db).get_or_none(email=validated.email)
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Email already registered",
            )
        
        # Cria usuário com senha hasheada
        user = User(
            email=validated.email,
            name=validated.name,
            password_hash=User.hash_password(validated.password),
        )
        await user.save(db)
        
        return UserOutput.model_validate(user).model_dump()
    
    @action(methods=["GET"], detail=False)
    async def me(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retorna o perfil do usuário autenticado."""
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated",
            )
        
        return UserDetailOutput.model_validate(user).model_dump()
    
    @action(methods=["POST"], detail=True)
    async def activate(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Ativa um usuário (apenas admin)."""
        # Verifica permissão de admin
        user = getattr(request.state, "user", None)
        if not user or not user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin access required",
            )
        
        target_user = await self.get_object(db, **kwargs)
        target_user.is_active = True
        await target_user.save(db)
        
        return {"message": f"User {target_user.email} activated"}
    
    @action(methods=["POST"], detail=True)
    async def deactivate(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Desativa um usuário (apenas admin)."""
        user = getattr(request.state, "user", None)
        if not user or not user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Admin access required",
            )
        
        target_user = await self.get_object(db, **kwargs)
        target_user.is_active = False
        await target_user.save(db)
        
        return {"message": f"User {target_user.email} deactivated"}


# ============================================================
# Post ViewSet
# ============================================================

class PostViewSet(ModelViewSet[Post, PostCreateInput, PostOutput]):
    """
    ViewSet para posts.
    
    - list: Público (apenas publicados) ou autenticado (todos)
    - retrieve: Público
    - create: Autenticado
    - update/delete: Autor ou admin
    """
    
    model = Post
    input_schema = PostCreateInput
    output_schema = PostOutput
    tags = ["posts"]
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated, IsPostAuthor],
        "partial_update": [IsAuthenticated, IsPostAuthor],
        "destroy": [IsAuthenticated, IsPostAuthor],
    }
    
    def get_queryset(self, db: AsyncSession):
        """Filtra posts baseado no usuário."""
        return Post.objects.using(db)
    
    async def list(
        self,
        request: Request,
        db: AsyncSession,
        page: int = 1,
        page_size: int | None = None,
        published_only: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Lista posts com filtro de publicação."""
        await self.check_permissions(request, "list")
        
        page_size = min(page_size or self.page_size, self.max_page_size)
        offset = (page - 1) * page_size
        
        queryset = self.get_queryset(db)
        
        # Filtra por publicados se não autenticado
        user = getattr(request.state, "user", None)
        if published_only and (user is None or not user.is_admin):
            queryset = queryset.filter(is_published=True)
        
        total = await queryset.count()
        posts = await queryset.order_by("-created_at").offset(offset).limit(page_size).all()
        
        items = [PostOutput.model_validate(post).model_dump() for post in posts]
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
        }
    
    async def create(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Cria post associado ao usuário autenticado."""
        await self.check_permissions(request, "create")
        
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        validated = PostCreateInput.model_validate(data)
        
        post = Post(
            title=validated.title,
            content=validated.content,
            is_published=validated.is_published,
            author_id=user.id,
        )
        await post.save(db)
        
        return PostOutput.model_validate(post).model_dump()
    
    async def retrieve(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retorna post e incrementa visualizações."""
        await self.check_permissions(request, "retrieve")
        
        post = await self.get_object(db, **kwargs)
        
        # Incrementa visualizações
        await post.increment_views(db)
        
        return PostDetailOutput.model_validate(post).model_dump()
    
    @action(methods=["POST"], detail=True)
    async def publish(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Publica um post."""
        post = await self.get_object(db, **kwargs)
        await self.check_object_permissions(request, post, "update")
        
        post.is_published = True
        await post.save(db)
        
        return {"message": "Post published", "post": PostOutput.model_validate(post).model_dump()}
    
    @action(methods=["POST"], detail=True)
    async def unpublish(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Despublica um post."""
        post = await self.get_object(db, **kwargs)
        await self.check_object_permissions(request, post, "update")
        
        post.is_published = False
        await post.save(db)
        
        return {"message": "Post unpublished", "post": PostOutput.model_validate(post).model_dump()}
    
    @action(methods=["GET"], detail=False)
    async def my_posts(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Lista posts do usuário autenticado."""
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        posts = await Post.objects.using(db)\
            .filter(author_id=user.id)\
            .order_by("-created_at")\
            .all()
        
        return {
            "items": [PostOutput.model_validate(post).model_dump() for post in posts],
            "total": len(posts),
        }


# ============================================================
# Comment ViewSet
# ============================================================

class CommentViewSet(ModelViewSet[Comment, CommentCreateInput, CommentOutput]):
    """
    ViewSet para comentários.
    """
    
    model = Comment
    input_schema = CommentCreateInput
    output_schema = CommentOutput
    tags = ["comments"]
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAuthenticated],
        "update": [IsAuthenticated, IsCommentAuthor],
        "partial_update": [IsAuthenticated, IsCommentAuthor],
        "destroy": [IsAuthenticated, IsCommentAuthor],
    }
    
    async def create(
        self,
        request: Request,
        db: AsyncSession,
        data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Cria comentário associado ao usuário autenticado."""
        await self.check_permissions(request, "create")
        
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        validated = CommentCreateInput.model_validate(data)
        
        # Verifica se o post existe
        post = await Post.objects.using(db).get_or_none(id=validated.post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        
        comment = Comment(
            content=validated.content,
            post_id=validated.post_id,
            author_id=user.id,
        )
        await comment.save(db)
        
        return CommentOutput.model_validate(comment).model_dump()


# ============================================================
# Tag ViewSet (Read-Only para público)
# ============================================================

class TagViewSet(ModelViewSet[Tag, TagCreateInput, TagOutput]):
    """
    ViewSet para tags.
    
    - list/retrieve: Público
    - create/update/delete: Admin
    """
    
    model = Tag
    input_schema = TagCreateInput
    output_schema = TagOutput
    tags = ["tags"]
    
    permission_classes = [IsAuthenticatedOrReadOnly]
    permission_classes_by_action = {
        "list": [AllowAny],
        "retrieve": [AllowAny],
        "create": [IsAdmin],
        "update": [IsAdmin],
        "partial_update": [IsAdmin],
        "destroy": [IsAdmin],
    }


# ============================================================
# Health Check View
# ============================================================

class HealthCheckView(APIView):
    """View para health check da API."""
    
    permission_classes = [AllowAny]
    tags = ["health"]
    
    async def get(
        self,
        request: Request,
        db: AsyncSession,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retorna status da API."""
        return {
            "status": "healthy",
            "database": "connected",
        }
