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
