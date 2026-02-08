# ViewSets

ViewSets centralizam a logica de manipulacao de recursos em uma unica classe. Diferente de frameworks que exigem decorators em cada funcao, aqui a configuracao e declarativa atraves de atributos de classe.

## ModelViewSet

Fornece implementacao completa de CRUD. O roteamento e gerado automaticamente quando registrado em um `AutoRouter`.

```python
from core import ModelViewSet
from .models import Product
from .schemas import ProductInput, ProductOutput

class ProductViewSet(ModelViewSet):
    # Obrigatorio: model SQLAlchemy que sera manipulado
    model = Product
    
    # Schemas para validacao de entrada e formatacao de saida
    input_schema = ProductInput
    output_schema = ProductOutput
    
    # Tags para agrupamento na documentacao OpenAPI
    tags = ["Products"]
    
    # Paginacao: page_size define itens por pagina no list()
    # Cliente pode solicitar ate max_page_size via query param ?page_size=
    page_size = 20
    max_page_size = 100
    
    # Campo usado para lookup em retrieve/update/destroy
    # Padrao e "id". Altere para usar slug, uuid, etc.
    # O tipo do campo e detectado automaticamente do model
    lookup_field = "id"
```

**Comportamento de paginacao**: A resposta de `list()` inclui metadados de paginacao (`count`, `next`, `previous`). Se `page_size` nao for definido, retorna todos os registros (cuidado com performance).

## Custom Actions

O decorator `@action` permite criar endpoints alem do CRUD padrao. Acoes sao metodos que se tornam endpoints HTTP.

```python
from core import ModelViewSet, action
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

class ProductViewSet(ModelViewSet):
    model = Product
    
    @action(methods=["POST"], detail=True)
    async def publish(self, request: Request, db: AsyncSession, **kwargs):
        """
        POST /products/{id}/publish
        
        detail=True significa que a acao opera sobre um registro especifico.
        O {id} vem de kwargs e e passado para get_object().
        """
        # get_object() busca o registro e levanta 404 se nao encontrar
        # Tambem executa verificacao de permissao a nivel de objeto
        product = await self.get_object(db, **kwargs)
        product.published = True
        await product.save(db)
        return {"status": "published"}
    
    @action(methods=["GET"], detail=False)
    async def featured(self, request: Request, db: AsyncSession, **kwargs):
        """
        GET /products/featured
        
        detail=False significa que a acao opera sobre a colecao.
        Nao recebe {id} na URL.
        """
        # get_queryset() retorna QuerySet filtrado conforme regras do ViewSet
        products = await self.get_queryset(db).filter(featured=True).all()
        
        # Serializacao manual - necessaria em actions customizadas
        schema = self.get_output_schema()
        return [schema.model_validate(p).model_dump() for p in products]
```

## Parametros do @action

| Parametro | Tipo | Descricao |
|-----------|------|-----------|
| `methods` | list[str] | Metodos HTTP aceitos. Multiplos metodos geram o mesmo endpoint. |
| `detail` | bool | `True`: URL inclui `{id}`. `False`: URL sem identificador. |
| `url_path` | str | Path customizado. Padrao: nome do metodo. Ex: `url_path="change-status"` |
| `permission_classes` | list | Sobrescreve permissoes apenas para esta acao. |

**Nota sobre url_path**: Use para URLs com hifen ou caracteres especiais. O nome do metodo Python deve ser valido (`change_status`), mas a URL pode ser `change-status`.

## Hooks de Ciclo de Vida

Hooks permitem interceptar operacoes CRUD sem sobrescrever os metodos principais. Sao chamados em pontos especificos do fluxo.

```python
class ProductViewSet(ModelViewSet):
    model = Product
    
    async def perform_create(self, data: dict, db: AsyncSession) -> Product:
        """
        Chamado apos validacao do schema, antes de salvar no banco.
        
        Use para:
        - Adicionar campos automaticos (created_by, tenant_id)
        - Transformar dados antes de salvar
        - Executar logica de negocio pre-criacao
        
        Retorno: instancia do model criada e salva
        """
        # self.request esta disponivel em todos os metodos do ViewSet
        data["created_by"] = self.request.state.user.id
        
        # super() executa a criacao padrao
        return await super().perform_create(data, db)
    
    async def perform_update(self, obj: Product, data: dict, db: AsyncSession) -> Product:
        """
        Chamado apos validacao, antes de salvar atualizacao.
        
        obj: instancia existente do model
        data: dados validados do request (apenas campos enviados em PATCH)
        """
        data["updated_by"] = self.request.state.user.id
        return await super().perform_update(obj, data, db)
    
    async def perform_destroy(self, obj: Product, db: AsyncSession) -> None:
        """
        Chamado antes de deletar o registro.
        
        Use para implementar soft delete ou validacoes pre-delecao.
        NAO chame super() se quiser impedir a delecao real.
        """
        # Soft delete: marca como deletado ao inves de remover
        obj.deleted = True
        obj.deleted_at = datetime.utcnow()
        await obj.save(db)
        # Nao chama super() - registro permanece no banco
```

**Importante**: Em `perform_destroy`, se voce chamar `super()`, o registro sera deletado do banco. Omitir `super()` mantem o registro.

## Hooks de Validacao

Validacao ocorre antes dos hooks de ciclo de vida. Use para regras de negocio que dependem de multiplos campos ou do banco de dados.

```python
class ProductViewSet(ModelViewSet):
    model = Product
    
    # unique_fields: validacao automatica de unicidade
    # O framework verifica no banco antes de criar/atualizar
    unique_fields = ["sku"]
    
    async def validate(self, data: dict, db: AsyncSession, instance=None) -> dict:
        """
        Validacao cross-field. Chamado apos validacao do schema.
        
        instance: None em create, objeto existente em update
        Retorno: data (possivelmente modificado)
        Levante ValidationError para rejeitar
        """
        if data.get("price", 0) < data.get("cost", 0):
            from core.validators import ValidationError
            # field= indica qual campo exibir o erro no frontend
            raise ValidationError("Price must be greater than cost", field="price")
        return data
    
    async def validate_field(self, field: str, value, db: AsyncSession, instance=None):
        """
        Validacao por campo individual. Chamado para cada campo do payload.
        
        Use para validacoes que dependem do banco ou sao especificas do campo.
        """
        if field == "sku" and not value.startswith("SKU-"):
            from core.validators import ValidationError
            raise ValidationError("SKU must start with 'SKU-'", field="sku")
        return value
```

**Ordem de execucao**: Schema validation -> `validate_field()` para cada campo -> `validate()` -> `perform_create/update()`

## Customizacao de QuerySet

O metodo `get_queryset()` define a query base para todas as operacoes. Use para filtros globais como multi-tenancy ou soft delete.

```python
class ProductViewSet(ModelViewSet):
    model = Product
    
    def get_queryset(self, db: AsyncSession):
        """
        Retorna QuerySet base para todas as operacoes do ViewSet.
        
        Chamado em: list(), retrieve(), update(), destroy()
        Use para: filtros de tenant, soft delete, permissoes baseadas em dados
        """
        qs = super().get_queryset(db)
        user = self.request.state.user
        
        # Usuarios nao-staff veem apenas produtos publicados
        # Staff ve todos os produtos
        if not user or not user.is_staff:
            return qs.filter(published=True)
        return qs
```

**Cuidado**: `get_queryset()` afeta todas as operacoes. Um filtro aqui impede que usuarios acessem registros mesmo conhecendo o ID.

## ReadOnlyModelViewSet

Versao restrita que expoe apenas `list()` e `retrieve()`. Util para recursos que nao devem ser modificados via API.

```python
from core import ReadOnlyModelViewSet

class PublicProductViewSet(ReadOnlyModelViewSet):
    model = Product
    output_schema = ProductOutput
    
    # input_schema nao e necessario - nao ha operacoes de escrita
    permission_classes = [AllowAny]
```

**Endpoints gerados**: Apenas `GET /products/` e `GET /products/{id}`. Tentativas de POST/PUT/PATCH/DELETE retornam 405 Method Not Allowed.

## APIView

Para endpoints que nao operam sobre models. Util para health checks, webhooks, ou integracao com servicos externos.

```python
from core import APIView
from core.permissions import AllowAny

class HealthView(APIView):
    permission_classes = [AllowAny]
    tags = ["System"]
    
    async def get(self, request, **kwargs):
        """
        GET /health
        
        Metodos HTTP sao mapeados para metodos da classe.
        Defina apenas os metodos que deseja expor.
        """
        return {"status": "healthy"}
    
    async def post(self, request, **kwargs):
        """
        POST /health
        
        request e o objeto Request do FastAPI.
        Use request.json() para obter o body.
        """
        body = await request.json()
        return {"received": body}
```

**Registro**: `APIView` e registrado diferente de `ModelViewSet`:

```python
router = AutoRouter(prefix="/system")
router.add_api_route("/health", HealthView.as_view(), methods=["GET", "POST"])
```

---

Proximo: [Authentication](03-authentication.md) - Configuracao de JWT, tokens e controle de acesso.
