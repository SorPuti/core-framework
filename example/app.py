"""
Aplicação de exemplo completa.

Demonstra como usar o Core Framework para criar uma API REST completa.
"""

from core.app import CoreApp, create_app
from core.config import Settings
from core.routing import Router, AutoRouter

from example.models import User, Post, Comment, Tag
from example.views import (
    UserViewSet,
    PostViewSet,
    CommentViewSet,
    TagViewSet,
    HealthCheckView,
)
from example.auth import auth_router, setup_auth


class AppSettings(Settings):
    """Configurações específicas da aplicação."""
    
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_expiration_hours: int = 24


def create_example_app() -> CoreApp:
    """
    Cria a aplicação de exemplo.
    
    Retorna:
        Instância configurada do CoreApp
    """
    # Configurações
    settings = AppSettings()
    
    # Cria auto-router para ViewSets
    api_router = AutoRouter(prefix="/api/v1")
    
    # Registra ViewSets
    api_router.register("/users", UserViewSet, basename="user")
    api_router.register("/posts", PostViewSet, basename="post")
    api_router.register("/comments", CommentViewSet, basename="comment")
    api_router.register("/tags", TagViewSet, basename="tag")
    
    # Registra view de health check
    api_router.register_view("/health", HealthCheckView)
    
    # Cria aplicação
    app = CoreApp(
        title="Core Framework Example API",
        description="""
        API de exemplo demonstrando o Core Framework.
        
        ## Funcionalidades
        
        - **Usuários**: CRUD completo com autenticação
        - **Posts**: Blog com publicação e visualizações
        - **Comentários**: Sistema de comentários em posts
        - **Tags**: Categorização de conteúdo
        
        ## Autenticação
        
        Use o endpoint `/auth/login` para obter um token JWT.
        Inclua o token no header `Authorization: Bearer <token>`.
        """,
        version="1.0.0",
        settings=settings,
        routers=[api_router],
    )
    
    # Inclui router de autenticação
    app.app.include_router(auth_router)
    
    # Configura autenticação
    @app.on_startup
    async def configure_authentication():
        setup_auth()
    
    # Rota raiz
    @app.get("/")
    async def root():
        return {
            "message": "Welcome to Core Framework Example API",
            "docs": "/docs",
            "redoc": "/redoc",
        }
    
    return app


# Cria instância da aplicação
example_app = create_example_app()

# Exporta a aplicação FastAPI para uso com uvicorn
app = example_app.app


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "example.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
