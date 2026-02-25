# Storage (arquivos)

Sistema de armazenamento de arquivos plug-and-play: **local** (disco) ou **Google Cloud Storage (GCS)**. Inspirado em Django + django-storages. Usado pelo Admin Panel para upload em campos de arquivo e para remover arquivos físicos na exclusão.

## Visão geral

- **Configuração**: em [Settings](02-settings.md#storage--file-uploads) você define `storage_backend` (`local` ou `gcs`) e os parâmetros do backend (bucket, credenciais, etc.).
- **Admin**: modelos com campos que armazenam path/URL de arquivo ganham o widget [file_upload no Admin](40-admin.md#campos-de-arquivo-storage-e-exclusão) (drag-and-drop, preview) e, ao deletar, a opção de apagar o arquivo físico do storage.
- **API programática**: use `core.storage` para salvar/remover arquivos fora do admin (jobs, APIs customizadas, etc.).

## Configuração

Toda a configuração fica em **Settings** (e `.env`). Resumo:

| Backend | Settings principais |
|--------|----------------------|
| **local** | `storage_backend="local"`, `storage_local_media_root`, `storage_media_url` |
| **gcs** | `storage_backend="gcs"`, `storage_gcs_bucket_name`, `storage_gcs_credentials_file` (ou ADC), `storage_media_url` |

Exemplos completos, tabela de todos os campos e equivalência com Django (`GS_BUCKET_NAME`, `GS_CREDENTIALS`, etc.): [Settings — Storage / File Uploads](02-settings.md#storage--file-uploads).

### Dependência opcional para GCS

```bash
pip install "core-framework[gcs]"
# ou
pip install google-cloud-storage
```

## Como obter credenciais e dados no Google Cloud

Para configurar o GCS no seu projeto, você precisa de: **ID do projeto**, **nome do bucket** e **arquivo JSON da Service Account** (credenciais). Tudo isso você obtém no [Google Cloud Console](https://console.cloud.google.com/).

### 1. ID do projeto (`STORAGE_GCS_PROJECT`)

- No topo da página do Console, ao lado do logo do Google Cloud, aparece o **nome do projeto** e um **ID** (ex.: `meu-projeto-123456`).
- Clique no nome do projeto para abrir o seletor; o **ID do projeto** está logo abaixo do nome.
- Use esse ID em `storage_gcs_project` (ou deixe em branco se for usar só o JSON — o projeto já vem dentro do JSON).

### 2. Bucket (`STORAGE_GCS_BUCKET_NAME`)

- No menu lateral: **Storage** → **Buckets** (ou [Cloud Storage → Buckets](https://console.cloud.google.com/storage/browser)).
- Se ainda não tiver bucket: **CREATE BUCKET** → escolha nome (ex.: `minha-app-uploads`), região e tipo de acesso. Anote o **nome do bucket** (só o nome, ex.: `minha-app-uploads`).
- Esse nome vai em `storage_gcs_bucket_name` / `STORAGE_GCS_BUCKET_NAME`.

### 3. Service Account e arquivo JSON (credenciais)

É isso que o framework usa para **autenticar** e gravar/ler no bucket (o “token” que o GCP pede é esse JSON).

1. No menu lateral: **IAM & Admin** → **Service Accounts** (ou [Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)).
2. **CREATE SERVICE ACCOUNT**:
   - Nome: ex. `storage-uploader`.
   - ID: pode deixar o sugerido.
   - **Create and Continue**.
3. **Grant access** (opcional nesta tela): pode pular; vamos dar permissão no bucket.
4. **Done**.
5. Na lista, clique na Service Account que você criou.
6. Aba **KEYS** → **ADD KEY** → **Create new key** → tipo **JSON** → **Create**.  
   O navegador baixa um arquivo `.json` (ex.: `meu-projeto-xxxxx.json`). **Guarde em local seguro e não commite no Git.**

Coloque o arquivo no projeto (ex.: `config/gcp-service-account.json` ou `.secrets/gcs.json`) e aponte no Settings:

- **Settings / .env**: `storage_gcs_credentials_file` = caminho para esse arquivo (ex.: `config/gcp-service-account.json`).

**Permissão no bucket**: a Service Account precisa poder escrever e ler objetos no bucket.

- Vá em **Storage** → **Buckets** → clique no seu bucket.
- Aba **PERMISSIONS** → **GRANT ACCESS**.
- **New principals**: cole o e-mail da Service Account (ex.: `storage-uploader@meu-projeto.iam.gserviceaccount.com`).
- **Role**: ex. **Storage Object Admin** (leitura + escrita + exclusão de objetos). Para só upload/leitura: **Storage Object Creator** + **Storage Object Viewer**.
- **Save**.

### 4. URL pública dos arquivos (`STORAGE_MEDIA_URL`)

Para o frontend (e o admin) abrirem os arquivos por link, você precisa da URL base do bucket:

- **Bucket público (recomendado para mídia)**:
  - Formato: `https://storage.googleapis.com/SEU_BUCKET_NAME/`
  - Ex.: se o bucket é `minha-app-uploads` → `https://storage.googleapis.com/minha-app-uploads/`
  - Para o bucket ser público: no bucket → **PERMISSIONS** → **Public access** → garantir que “Public access” está permitido; nos objetos, ACL `publicRead` (o framework já pode definir isso ao subir, se `storage_gcs_default_acl="publicRead"`).

- **Bucket privado**: aí você serviria via signed URLs ou outro esquema; a URL base pode ser a mesma, mas o acesso depende de signed URL ou IAM. Para começar, bucket público + `storage_media_url = "https://storage.googleapis.com/SEU_BUCKET_NAME/"` é o mais simples.

Resumo do que vai no seu projeto:

| Onde pegar no GCP | Variável / Setting | Exemplo |
|-------------------|--------------------|--------|
| Topo do Console (ID do projeto) | `STORAGE_GCS_PROJECT` | `meu-projeto-123456` |
| Storage → Buckets (nome do bucket) | `STORAGE_GCS_BUCKET_NAME` | `minha-app-uploads` |
| IAM → Service Accounts → Keys → JSON baixado | `STORAGE_GCS_CREDENTIALS_FILE` (caminho do arquivo) | `config/gcp-service-account.json` |
| Montado por você com o nome do bucket | `STORAGE_MEDIA_URL` | `https://storage.googleapis.com/minha-app-uploads/` |

Exemplo de `.env`:

```bash
STORAGE_BACKEND=gcs
STORAGE_GCS_PROJECT=meu-projeto-123456
STORAGE_GCS_BUCKET_NAME=minha-app-uploads
STORAGE_GCS_CREDENTIALS_FILE=config/gcp-service-account.json
STORAGE_MEDIA_URL=https://storage.googleapis.com/minha-app-uploads/
```

**Segurança**: adicione o caminho do JSON ao `.gitignore` (ex.: `config/gcp-service-account.json` ou `.secrets/`).

## API: `core.storage`

### `save_file(relative_path, content, content_type=None) -> str`

Salva o conteúdo no backend configurado (local ou GCS).

- **relative_path**: caminho relativo, ex.: `uploads/2025/02/abc.jpg`.
- **content**: bytes do arquivo.
- **content_type**: MIME type (opcional; usado no GCS).
- **Retorno**: path ou URL a ser armazenado no modelo (path relativo no local; URL ou path no GCS).

```python
from core.storage import save_file

path = save_file("uploads/2025/02/foto.jpg", file_bytes, "image/jpeg")
# local → "uploads/2025/02/foto.jpg"
# gcs   → "https://storage.googleapis.com/bucket/uploads/2025/02/foto.jpg" (se storage_media_url configurado)
```

### `delete_file(path_or_url) -> bool`

Remove o arquivo físico do backend.

- **path_or_url**: valor armazenado no modelo (path relativo, URL pública ou `gs://bucket/key`).
- **Retorno**: `True` se removeu ou não existia; `False` em erro (erro é logado).

```python
from core.storage import delete_file

delete_file("uploads/2025/02/foto.jpg")
delete_file("https://storage.googleapis.com/bucket/uploads/2025/02/foto.jpg")
```

### `get_storage_file_fields(admin_instance) -> list[str]`

Retorna os nomes dos campos do model que são de arquivo (widget `file_upload`) para um `ModelAdmin`. Útil para saber quais atributos da instância contêm path/URL ao implementar exclusão com remoção de arquivos.

```python
from core.storage import get_storage_file_fields

file_fields = get_storage_file_fields(admin_instance)  # ex.: ["avatar_url", "attachment_path"]
```

### `collect_file_paths(instance, field_names) -> list[str]`

Coleta os valores (path/URL) de arquivo de uma instância para os campos dados. Retorna lista de strings não vazias.

```python
from core.storage import collect_file_paths, get_storage_file_fields

file_fields = get_storage_file_fields(admin_instance)
paths = collect_file_paths(obj, file_fields)
for path in paths:
    delete_file(path)
```

## Uso no Admin Panel

- **Campos de arquivo**: o admin detecta automaticamente colunas como `image`, `avatar`, `photo`, `file_path`, `attachment_url` e exibe o widget **file_upload** (drag-and-drop, preview, link para o arquivo atual).
- **Upload**: ao soltar ou escolher arquivo, o frontend chama `POST /api/{app}/{model}/upload-file`; o backend usa `save_file` e devolve path/URL, que é salvo no campo ao salvar o formulário.
- **Exclusão**: ao deletar um registro, o modal pergunta se deseja **também deletar X arquivo(s) do storage**; em bulk delete, o body pode incluir `"delete_physical_files": true`.

Detalhes e como forçar o widget em um campo: [Admin — Campos de arquivo (Storage) e exclusão](40-admin.md#campos-de-arquivo-storage-e-exclusão).

## Servir arquivos locais

Com `storage_backend="local"`, os arquivos ficam em `storage_local_media_root` (ex.: `media/`). Para o frontend (e links do admin) conseguirem abrir os arquivos, você precisa expor esse diretório:

- **Desenvolvimento**: montar rota estática em `/media` apontando para o diretório (ex.: FastAPI `StaticFiles`).
- **Produção**: Nginx (ou outro) servindo o diretório em `STORAGE_MEDIA_URL` (ex.: `/media/`).

Exemplo com FastAPI:

```python
from fastapi.staticfiles import StaticFiles
from core.config import get_settings

settings = get_settings()
if settings.storage_backend == "local":
    app.mount("/media", StaticFiles(directory=settings.storage_local_media_root), name="media")
```

Com GCS, `storage_media_url` costuma ser a URL pública do bucket (ou do CDN), então não é necessário servir arquivos pela aplicação.

## Ver também

- [Settings — Storage / File Uploads](02-settings.md#storage--file-uploads) — configuração completa e exemplos de `.env`
- [Admin — Campos de arquivo e exclusão](40-admin.md#campos-de-arquivo-storage-e-exclusão) — widget file_upload e modal de delete
