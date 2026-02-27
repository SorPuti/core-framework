# Storage (arquivos)

Sistema de armazenamento de arquivos plug-and-play: **local** (disco) ou **Google Cloud Storage (GCS)**. Inspirado em Django + django-storages. Usado pelo Admin Panel para upload em campos de arquivo e para remover arquivos físicos na exclusão.

## Visão geral

- **Configuração**: em [Settings](02-settings.md#storage--file-uploads) você define `storage_backend` (`local` ou `gcs`) e os parâmetros do backend (bucket, credenciais, etc.).
- **Admin**: modelos com campos que armazenam path/URL de arquivo ganham o widget [file_upload no Admin](40-admin.md#campos-de-arquivo-storage-e-exclusão) (drag-and-drop, preview) e, ao deletar, a opção de apagar o arquivo físico do storage.
- **API programática**: use `core.storage` para salvar/remover arquivos fora do admin (jobs, APIs customizadas, etc.).
- **Signed URLs**: suporte nativo para buckets privados via signed URLs — seguro e temporário.

## Configuração

Toda a configuração fica em **Settings** (e `.env`). Resumo:

| Backend | Settings principais |
|--------|----------------------|
| **local** | `storage_backend="local"`, `storage_local_media_root`, `storage_media_url` |
| **gcs** (público) | `storage_backend="gcs"`, `storage_gcs_bucket_name`, `storage_gcs_use_signed_urls=false` |
| **gcs** (privado) | `storage_backend="gcs"`, `storage_gcs_bucket_name`, `storage_gcs_use_signed_urls=true` |

### Configurações GCS

| Setting | Descrição | Default |
|---------|-----------|---------|
| `storage_gcs_bucket_name` | Nome do bucket | obrigatório |
| `storage_gcs_credentials_file` | Caminho do JSON da Service Account | None (usa ADC) |
| `storage_gcs_project` | ID do projeto GCP | None (usa do JSON) |
| `storage_gcs_use_signed_urls` | Usar signed URLs para bucket privado | `true` |
| `storage_gcs_expiration_seconds` | Tempo de expiração das signed URLs | `3600` (1 hora) |
| `storage_gcs_default_acl` | ACL padrão dos objetos | `private` |
| `storage_media_url` | URL base (fallback se signed URLs falharem) | None |

### Dependência opcional para GCS

```bash
pip install "core-framework[gcs]"
# ou
pip install google-cloud-storage
```

## Buckets Privados (Signed URLs)

Para buckets privados, o framework gera **signed URLs** automaticamente. Isso é similar ao comportamento do Django com `django-storages`:

1. O **model armazena apenas o path relativo** (ex: `uploads/foto.jpg`)
2. A **API retorna signed URLs** automaticamente ao serializar

### Configuração para bucket privado

```bash
# .env
STORAGE_BACKEND=gcs
STORAGE_GCS_PROJECT=meu-projeto-123456
STORAGE_GCS_BUCKET_NAME=meu-bucket-privado
STORAGE_GCS_CREDENTIALS_FILE=config/gcp-service-account.json
STORAGE_GCS_USE_SIGNED_URLS=true
STORAGE_GCS_EXPIRATION_SECONDS=3600
STORAGE_GCS_DEFAULT_ACL=private
```

### Permissões necessárias para signed URLs

A Service Account precisa de permissões adicionais para gerar signed URLs:

```bash
# No bucket
roles/storage.objectAdmin  # ou objectCreator + objectViewer

# Para signed URLs (no projeto)
roles/iam.serviceAccountTokenCreator
```

Comando para adicionar permissão de token creator:
```bash
gcloud projects add-iam-policy-binding MEU_PROJETO \
  --member="serviceAccount:EMAIL_DA_SA@MEU_PROJETO.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"
```

## API: `core.storage`

### `save_file(relative_path, content, content_type=None) -> str`

Salva o conteúdo no backend configurado (local ou GCS).

- **relative_path**: caminho relativo, ex.: `uploads/2025/02/abc.jpg`.
- **content**: bytes do arquivo.
- **content_type**: MIME type (opcional; usado no GCS).
- **Retorno**: **path relativo** a ser armazenado no modelo.

```python
from core.storage import save_file

path = save_file("uploads/2025/02/foto.jpg", file_bytes, "image/jpeg")
# Retorna sempre: "uploads/2025/02/foto.jpg"
# O path é armazenado no model; use get_file_url() para obter a URL de acesso.
```

### `get_file_url(path, expiration=None) -> str`

Gera URL de acesso ao arquivo. Para buckets privados, retorna **signed URL**.

- **path**: path relativo armazenado no modelo.
- **expiration**: tempo de expiração em segundos ou timedelta (default: `storage_gcs_expiration_seconds`).
- **Retorno**: URL de acesso (signed URL para bucket privado).

```python
from core.storage import get_file_url

url = get_file_url("uploads/2025/02/foto.jpg")
# Bucket privado → "https://storage.googleapis.com/bucket/...?X-Goog-Signature=..."
# Bucket público → "https://storage.googleapis.com/bucket/uploads/2025/02/foto.jpg"
# Local → "/media/uploads/2025/02/foto.jpg"

# Com expiração customizada (5 minutos)
url = get_file_url("uploads/foto.jpg", expiration=300)
```

### `delete_file(path_or_url) -> bool`

Remove o arquivo físico do backend.

- **path_or_url**: valor armazenado no modelo (path relativo, URL pública ou `gs://bucket/key`).
- **Retorno**: `True` se removeu ou não existia; `False` em erro (erro é logado).

```python
from core.storage import delete_file

delete_file("uploads/2025/02/foto.jpg")
```

### `file_exists(path) -> bool`

Verifica se o arquivo existe no storage.

```python
from core.storage import file_exists

if file_exists("uploads/foto.jpg"):
    print("Arquivo existe!")
```

## FileField Nativo (estilo Django)

O framework oferece `AdvancedField.file()` - um FileField nativo que funciona igual ao Django:

```python
from core import Model, Field
from core.fields import AdvancedField

class Course(Model):
    __tablename__ = "courses"
    
    id: Mapped[int] = Field.pk()
    name: Mapped[str] = Field.string(255)
    
    # Coluna do banco (string que armazena o path)
    cover_image_url: Mapped[str | None] = Field.string(500, nullable=True)
    
    # FileField nativo - interface rica para arquivos
    cover = AdvancedField.file("cover_image_url", upload_to="courses/covers/")

# Uso:
course.cover.name     # "courses/covers/abc.jpg" (path armazenado)
course.cover.url      # "https://...?X-Goog-Signature=..." (signed URL)
course.cover.save("foto.jpg", content, "image/jpeg")  # Upload
course.cover.delete() # Remove do storage
bool(course.cover)    # True se tem arquivo
course.cover.exists() # Verifica se existe no storage
```

### Parâmetros do FileField

```python
AdvancedField.file(
    db_column="cover_image_url",    # Coluna do banco que armazena o path
    upload_to="courses/covers/",     # Diretório de upload (ou função)
    url_expiration=3600,             # Expiração da signed URL (segundos)
)
```

### Upload dinâmico com função

```python
def course_cover_path(instance, filename):
    """Gera path baseado no ID do curso."""
    return f"courses/{instance.id}/covers/{filename}"

class Course(Model):
    cover_url: Mapped[str | None] = Field.string(500, nullable=True)
    cover = AdvancedField.file("cover_url", upload_to=course_cover_path)
```

### Métodos do FieldFile

| Método | Descrição |
|--------|-----------|
| `.name` | Path relativo do arquivo |
| `.url` | URL de acesso (signed URL para bucket privado) |
| `.save(filename, content, content_type)` | Salva arquivo no storage |
| `.delete(save_model=False)` | Remove arquivo do storage |
| `.exists()` | Verifica se arquivo existe |
| `bool(file)` | True se tem arquivo |

### Alternativa: `storage_file_property`

Para casos mais simples (somente leitura), existe também o `storage_file_property`:

```python
from core.storage import storage_file_property

class Course(Model):
    cover_image_url: Mapped[str | None] = Field.string(500, nullable=True)
    cover_image = storage_file_property("cover_image_url")

# Apenas leitura:
course.cover_image.url   # Signed URL
course.cover_image.name  # Path
```

## Uso em Schemas (API Response)

Para retornar signed URLs automaticamente nas respostas da API, use um `model_validator`:

```python
from pydantic import model_validator
from core.serializers import OutputSchema
from core.storage import get_file_url

class CourseResponse(OutputSchema):
    id: UUID
    name: str
    cover_image_url: str | None = None
    
    @model_validator(mode="after")
    def transform_file_urls(self):
        """Transforma paths em signed URLs automaticamente."""
        if self.cover_image_url:
            self.cover_image_url = get_file_url(self.cover_image_url)
        return self

# Agora a API retorna signed URLs automaticamente:
# GET /api/courses/123
# {
#   "id": "...",
#   "name": "Curso X",
#   "cover_image_url": "https://storage.googleapis.com/...?X-Goog-Signature=..."
# }
```

## Como obter credenciais no Google Cloud

### 1. ID do projeto (`STORAGE_GCS_PROJECT`)

- No topo da página do Console, ao lado do logo do Google Cloud, aparece o **nome do projeto** e um **ID** (ex.: `meu-projeto-123456`).
- Use esse ID em `storage_gcs_project` (ou deixe em branco se for usar só o JSON — o projeto já vem dentro do JSON).

### 2. Bucket (`STORAGE_GCS_BUCKET_NAME`)

- No menu lateral: **Storage** → **Buckets** (ou [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser)).
- Se ainda não tiver bucket: **CREATE BUCKET** → escolha nome, região e tipo de acesso.

### 3. Service Account e arquivo JSON

1. No menu lateral: **IAM & Admin** → **Service Accounts**.
2. **CREATE SERVICE ACCOUNT** → Nome: `storage-uploader` → **Create and Continue**.
3. Na lista, clique na Service Account → aba **KEYS** → **ADD KEY** → **Create new key** → **JSON**.
4. Guarde o arquivo JSON em local seguro (ex.: `config/gcp-service-account.json`).

**Permissões necessárias:**

```bash
# No bucket (Storage → Buckets → Permissions)
Storage Object Admin

# Para signed URLs (IAM → projeto)
Service Account Token Creator
```

### Exemplo completo de `.env`

```bash
# Bucket privado com signed URLs
STORAGE_BACKEND=gcs
STORAGE_GCS_PROJECT=meu-projeto-123456
STORAGE_GCS_BUCKET_NAME=meu-bucket-uploads
STORAGE_GCS_CREDENTIALS_FILE=config/gcp-service-account.json
STORAGE_GCS_USE_SIGNED_URLS=true
STORAGE_GCS_EXPIRATION_SECONDS=3600
STORAGE_GCS_DEFAULT_ACL=private
```

```bash
# Bucket público (sem signed URLs)
STORAGE_BACKEND=gcs
STORAGE_GCS_PROJECT=meu-projeto-123456
STORAGE_GCS_BUCKET_NAME=meu-bucket-publico
STORAGE_GCS_CREDENTIALS_FILE=config/gcp-service-account.json
STORAGE_GCS_USE_SIGNED_URLS=false
STORAGE_GCS_DEFAULT_ACL=publicRead
STORAGE_MEDIA_URL=https://storage.googleapis.com/meu-bucket-publico/
```

## Uso no Admin Panel

- **Campos de arquivo**: o admin detecta automaticamente colunas como `image`, `avatar`, `photo`, `file_path`, `attachment_url` e exibe o widget **file_upload** (drag-and-drop, preview, link para o arquivo atual).
- **Upload**: ao soltar ou escolher arquivo, o frontend chama `POST /api/{app}/{model}/upload-file`; o backend usa `save_file` e devolve path, que é salvo no campo ao salvar o formulário.
- **Exclusão**: ao deletar um registro, o modal pergunta se deseja **também deletar X arquivo(s) do storage**.

## Servir arquivos locais

Com `storage_backend="local"`, os arquivos ficam em `storage_local_media_root` (ex.: `media/`). Para o frontend conseguir abrir os arquivos:

```python
from fastapi.staticfiles import StaticFiles
from core.config import get_settings

settings = get_settings()
if settings.storage_backend == "local":
    app.mount("/media", StaticFiles(directory=settings.storage_local_media_root), name="media")
```

## Funções auxiliares

### `get_storage_file_fields(admin_instance) -> list[str]`

Retorna os nomes dos campos do model que são de arquivo (widget `file_upload`).

### `collect_file_paths(instance, field_names) -> list[str]`

Coleta os valores (path/URL) de arquivo de uma instância para os campos dados.

```python
from core.storage import collect_file_paths, get_storage_file_fields, delete_file

file_fields = get_storage_file_fields(admin_instance)
paths = collect_file_paths(obj, file_fields)
for path in paths:
    delete_file(path)
```

## Ver também

- [Settings — Storage / File Uploads](02-settings.md#storage--file-uploads) — configuração completa
- [Admin — Campos de arquivo e exclusão](40-admin.md#campos-de-arquivo-storage-e-exclusão) — widget file_upload
