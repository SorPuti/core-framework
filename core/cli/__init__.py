"""
CLI do Core Framework.

Comandos disponíveis:
- core init: Inicializa um novo projeto
- core makemigrations: Gera migrações
- core migrate: Aplica migrações
- core showmigrations: Mostra status das migrações
- core rollback: Reverte migrações
- core run: Executa o servidor de desenvolvimento
- core shell: Abre shell interativo
- core routes: Lista rotas registradas
"""

from core.cli.main import cli, main

__all__ = ["cli", "main"]
