# Introdução

Bem-vindo ao Stride Framework (core-framework).

Este documento foi gerado a partir do código existente no repositório e reflete precisamente as implementações atuais.
O objetivo é oferecer um ponto de verdade único (source of truth) para desenvolvedores e IAs.

## O que é o Stride

Stride é um framework Python para APIs REST, construído sobre `FastAPI` e `SQLAlchemy` com um estilo inspirado em Django (ViewSets, URL routing, configs centradas em settings).

## MCP Server (independente)

O projeto inclui uma implementação separada de MCP em `/mcp-server`.
- Não acoplado ao backend principal.
- Consome apenas a documentação de `/docs`.
- Usa indexação e busca semântica baseada em TF-IDF.
- Endpoints: `GET /status`, `POST /query`.


### Pilares do projeto

- Auto-discovery de apps via `Settings.installed_apps` e `strider.urls.autodiscover`.
- API CRUD via `ViewSet`, `ModelViewSet`, `AutoRouter` e `Router.register_viewset`.
- Schemas Pydantic (`InputSchema`, `OutputSchema`) para request e response.
- Sistema de permissões composível (`Permission`, `IsAuthenticated`, `IsAdmin`, `IsOwner`, `AndPermission`, `OrPermission`).
- Módulos adicionais: `auth`, `admin`, `messaging`, `tenancy`, `realtime`, `workers`.

## Como usar

1. Defina um `AppSettings` estendendo `strider.config.Settings`.
2. Configure `.env` com `DATABASE_URL`, `SECRET_KEY`, etc.
3. Crie `Model` em `src/apps/<app>/models.py`.
4. Crie `ViewSet` em `src/apps/<app>/views.py`.
5. Crie `urlpatterns` em `src/apps/<app>/urls.py` usando `strider.urls.path`.
6. Inicie a aplicação com `app = StrideApp()` e `uvicorn main:app`.

## Objetivo do repositório

- Documentação 100% congruente com código.
- Base para geração de GitHub Pages e MCP Server (IA).
- Facilitar entendimentos automáticos via introspecção e especificações OpenAPI.
