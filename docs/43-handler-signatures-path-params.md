# Assinaturas de handlers, path params e upload

Este guia é específico para alinhar **assinaturas Python** dos métodos em `APIView`, `ViewSet` / `ModelViewSet` com o que o **router Stride** injeta automaticamente (dependências FastAPI, segmentos de URL, corpo JSON e `UploadFile`). Para visão geral de URLs e `path()`, veja [Routing](23-routing.md).

## O que o router repassa ao handler

O Stride monta os argumentos com base na **assinatura** do método (nome e anotação de cada parâmetro). Em geral:

| Origem | Parâmetros típicos |
|--------|---------------------|
| Dependências | `request`, `db`, `_user` (só entram se existirem na assinatura) |
| Segmentos `{nome}` na rota | Mesmo nome na assinatura (após merge/alias, ver abaixo) |
| JSON | Parâmetro escolhido por convenção (`data`, `payload`, `body`, etc.) |
| Multipart | `UploadFile` no parâmetro anotado (ex.: `file`) |

Chamadas geradas pelo router usam **apenas palavras-chave** para dependências e path: `handler(vs, **kwargs)` ou `handler(**kwargs)` em `APIView`, onde `kwargs` inclui o que o método declara.

### ViewSet: lookup, `pk` e `id`

Em rotas de **detalhe** (`detail=True` ou CRUD em `/{lookup}/`), o segmento da URL vem de `ViewSet.lookup_url_kwarg` (ou `lookup_field` quando `lookup_url_kwarg` não está definido). O Stride mapeia esse valor para parâmetros aceitos pelo método:

- o nome do segmento (ex.: `id`);
- `lookup_field` (ex.: `id`);
- `pk` (estilo DRF).

Assim, um único valor na URL pode satisfazer `async def retrieve(self, request, db, pk: int)` mesmo quando a rota expõe `{id}`.

Em `APIView` **sem** ViewSet, o alias automático é só **`id` → `pk`** quando a assinatura declara `pk` e não declara `id`.

## Coerção de tipos nos segmentos de path

Valores de path chegam como **string**. Se você anotar o parâmetro, o Stride tenta converter:

- `int`, `float`, `bool` (aceita `true`/`false`, `1`/`0`, `yes`/`no`, etc.);
- `uuid.UUID`;
- `str` deixa como está.

Falhas de conversão levantam `StridePathParamBindingError` com mensagem objetiva (em vez de falhas genéricas mais adiante).

## Erros claros: `StridePathParamBindingError`

Quando a assinatura **não combina** com os argumentos injetados (por exemplo, keyword inesperada ou falta de parâmetro), o Python levanta `TypeError`. O Stride intercepta isso nas rotas geradas e substitui por **`StridePathParamBindingError`** (subclasse de `TypeError`), com:

- a mensagem original do `TypeError`;
- um bloco **“Stride (assinatura e path)”** listando handler, parâmetros declarados, contexto de URL e dicas de lookup (`lookup_field` / segmento da rota).

Importação:

```python
from strider import StridePathParamBindingError
# ou
from strider.exceptions import StridePathParamBindingError
```

## `@action` e rotas customizadas

### `detail=False`

- Sem `{lookup}` na URL: path params vêm só dos placeholders do `url_path` (ex.: `url_path="{slug}/preview"` → parâmetro `slug`).
- Com **JSON**: declare um parâmetro para o corpo (ex.: `data`) ou confie na detecção automática do nome.
- Com **upload**: anote `file: UploadFile` (ou use o atributo `accepts_upload` na action) para o router registrar multipart.

### `detail=True`

- A URL inclui o segmento de lookup (`{id}` ou o valor de `lookup_url_kwarg`).
- Inclua na assinatura **`pk`**, o **nome do segmento**, ou **`lookup_field`**, ou omita e use `get_object()` se não precisar do valor cru na URL.
- **Upload em detalhe**: o router expõe o lookup no OpenAPI e injeta `file` junto com os path params.

### Rotas só com actions (`include_crud=False`)

Apenas as actions declaradas com `@action` são registradas; as mesmas regras de assinatura e merge de path aplicam-se.

## `APIView` (`register_view`)

O método HTTP (`get`, `post`, …) recebe dependências via kwargs quando declaradas (`request`, `db`, `_user`). Os `{chaves}` da rota devem bater com nomes na assinatura (ou use `**kwargs` no handler). O alias `id` → `pk` aplica-se como acima.

## Checklist rápido

1. Nomes dos `{segmentos}` na rota = parâmetros na assinatura (ou `pk` / lookup mapeado).
2. Use anotações (`pk: int`, `id: UUID`) para coerção automática de path.
3. Em erro de assinatura, leia o bloco Stride na exceção e ajuste a assinatura ou a rota.
4. Upload: parâmetro `UploadFile` com o nome esperado na assinatura (`file` é o padrão do FastAPI no template gerado).
