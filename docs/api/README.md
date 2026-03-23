# API Reference (basics)

Esta seção agrupa exemplos de uso de routing e endpoints baseados em código.

## Auto-route com ViewSet

```python
from strider import StrideApp, AutoRouter
from src.apps.posts.views import PostViewSet

router = AutoRouter(prefix="/api/v1")
router.register("/posts", PostViewSet)

app = StrideApp(routers=[router])
```

### Endpoints gerados (ModelViewSet)

- `GET /api/v1/posts/`
- `POST /api/v1/posts/`
- `GET /api/v1/posts/{id}`
- `PUT /api/v1/posts/{id}`
- `PATCH /api/v1/posts/{id}`
- `DELETE /api/v1/posts/{id}`

## APIView

```python
from strider import APIView

class PingView(APIView):
    async def get(self, request):
        return {"status": "pong"}

router.register_view("/ping", PingView, methods=["GET"])
```
