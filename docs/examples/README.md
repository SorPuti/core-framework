# Examples

Exemplos reais baseados no código e nos testes existentes.

## Exemplo rápido (sem app completa)

Veja `docs/01-quickstart.md` para um fluxo end-to-end com model, viewset, urls e app.

## Exemplo de Permissões

```python
from strider.permissions import IsAuthenticated, IsOwner

class UserProfileViewSet(ModelViewSet):
    model = UserProfile
    permission_classes = [IsAuthenticated]
    permission_classes_by_action = {
        "destroy": [IsAdmin],
        "update": [IsOwner],
    }
```

## Exemplo de Custom Action

```python
from strider.views import action

class OrderViewSet(ModelViewSet):
    ...
    @action(methods=["POST"], detail=True, permission_classes=[IsAuthenticated])
    async def cancel(self, request, db, **kwargs):
        order = await self.get_object(db, **kwargs)
        order.status = "cancelled"
        await order.save(db)
        return {"status": "cancelled"}
```
