# Troubleshooting

## Erro ao descobrir apps

- Verifique `installed_apps` em settings.
- Certifique-se de que cada app tenha `urls.py` com `urlpatterns`.
- Caso use `root_urlconf`, este é o único caminho de urls.

## HTTP 401/403

- Confirme middleware de auth: `StrideApp(middleware=["auth"])` ou `settings.middleware`.
- Verifique `permission_classes` e `permission_classes_by_action`.

## Validação de schema falhando no startup

- Se `strict_validation=True` e `debug=True`, qualquer mismatch entre InputSchema/OutputSchema e Model lança erro.
- Use `strict_validation=False` para ser permissivo ou corrija schema/model.

## Rota duplicada

- `Router.add_api_route` detecta duplicatas por (path,method).
- Ajuste prefixos ou garanta `route_conflict_policy` em ViewSet (`warn`, `raise`, `ignore`).

## WebSocket não conectando

- `WebSocketView` deve estar registrado antes de outras rotas e `StrideApp` monta `_ws_router` separadamente.
- Verifique CORS/WebSocket e permissões para WS em `strider.realtime`.

## DB não inicializado

- Use `init_db(settings)` antes de DB queries.
- Se `auto_create_tables=True`, `create_tables()` é executado no startup.
- Verifique `DATABASE_URL` e validadores pydantic.
