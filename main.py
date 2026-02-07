"""
Core Framework - Ponto de entrada principal.

Execute com:
    python main.py

Ou com uvicorn:
    uvicorn main:app --reload

Configuração:
    Todas as settings ficam em example/settings.py
    Variáveis de ambiente em .env e .env.{ENVIRONMENT}
"""

if __name__ == "__main__":
    import uvicorn
    from example.settings import settings
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
