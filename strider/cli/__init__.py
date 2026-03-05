"""
CLI do Strider.

Comandos disponíveis:
- strider init: Inicializa um novo projeto
- strider makemigrations: Gera migrações
- strider migrate: Aplica migrações
- strider showmigrations: Mostra status das migrações
- strider rollback: Reverte migrações
- strider run: Executa o servidor de desenvolvimento
- strider shell: Abre shell interativo
- strider routes: Lista rotas registradas
- strider test: Executa testes com ambiente isolado
- strider version: Mostra versão do framework
"""

from strider.cli.main import cli, main

__all__ = ["cli", "main"]
