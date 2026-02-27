"""
Storage de arquivos — plug-and-play local ou Google Cloud Storage.

Suporta:
- Backend local (disco)
- Google Cloud Storage (público ou privado com signed URLs)

Inspirado em Django + django-storages. O model armazena apenas o path
relativo, e a URL é gerada dinamicamente via get_file_url().

Uso:
    from core.storage import save_file, delete_file, get_file_url

    # Upload - retorna apenas o path relativo
    path = save_file("uploads/2025/02/abc.jpg", file_bytes, "image/jpeg")
    # → "uploads/2025/02/abc.jpg"

    # Obter URL para download (signed URL para bucket privado)
    url = get_file_url(path)
    # → "https://storage.googleapis.com/bucket/uploads/...?X-Goog-Signature=..."

    # Delete
    delete_file(path)
"""

from __future__ import annotations

import logging
import os
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.storage")

# Cache do client GCS para evitar criar conexões repetidas
_gcs_client = None


def _get_settings() -> Any:
    from core.config import get_settings
    return get_settings()


def _get_gcs_client():
    """Obtém client GCS com cache para reutilização."""
    global _gcs_client
    if _gcs_client is not None:
        return _gcs_client
    
    try:
        from google.cloud import storage as gcs_storage
    except ImportError:
        raise RuntimeError(
            "Storage backend 'gcs' requer a dependência opcional 'google-cloud-storage'. "
            "Instale com: pip install 'google-cloud-storage' ou use o extra apropriado do core-framework."
        )
    
    settings = _get_settings()
    credentials_file = getattr(settings, "storage_gcs_credentials_file", None)
    project = getattr(settings, "storage_gcs_project", None)
    
    if credentials_file:
        _gcs_client = gcs_storage.Client.from_service_account_json(
            credentials_file, project=project
        )
    else:
        _gcs_client = gcs_storage.Client(project=project)
    
    return _gcs_client


def save_file(relative_path: str, content: bytes, content_type: str | None = None) -> str:
    """
    Salva conteúdo no backend configurado (local ou GCS).
    
    Args:
        relative_path: Caminho relativo (ex: uploads/2025/02/uuid-foto.jpg).
        content: Conteúdo binário do arquivo.
        content_type: MIME type (opcional; usado no GCS).
    
    Returns:
        Path relativo a ser armazenado no modelo. Use get_file_url() para obter
        a URL de acesso (suporta signed URLs para buckets privados).
    """
    settings = _get_settings()
    backend = getattr(settings, "storage_backend", "local")
    
    if backend == "local":
        root = Path(getattr(settings, "storage_local_media_root", "media"))
        root = root if root.is_absolute() else Path.cwd() / root
        full = root / relative_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
        return relative_path
    
    if backend == "gcs":
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if not bucket_name:
            raise RuntimeError("storage_gcs_bucket_name is required when storage_backend is 'gcs'")
        
        client = _get_gcs_client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(relative_path)
        blob.upload_from_string(
            content,
            content_type=content_type or "application/octet-stream",
        )
        
        # Se ACL pública configurada, tenta tornar público
        default_acl = getattr(settings, "storage_gcs_default_acl", None)
        if default_acl == "publicRead":
            try:
                blob.make_public()
            except Exception as e:
                logger.debug("Could not set ACL on blob %s: %s", relative_path, e)
        
        # Sempre retorna apenas o path relativo (como Django faz)
        return relative_path
    
    raise ValueError(f"Unknown storage_backend: {backend}")


def get_file_url(path: str, expiration: int | timedelta | None = None) -> str:
    """
    Gera URL de acesso ao arquivo.
    
    Para buckets privados no GCS, gera signed URL com tempo de expiração.
    Para buckets públicos ou local, retorna URL direta.
    
    Args:
        path: Path relativo armazenado no modelo (ex: uploads/foto.jpg).
        expiration: Tempo de expiração da signed URL em segundos ou timedelta.
                   Default: storage_gcs_signed_url_expiration (3600s = 1 hora).
    
    Returns:
        URL de acesso ao arquivo (signed URL para bucket privado).
    
    Exemplo:
        # No model
        class MyModel(Model):
            file_path: str
            
            @property
            def file_url(self):
                return get_file_url(self.file_path)
    """
    if not path or not isinstance(path, str):
        return ""
    
    path = path.strip()
    if not path:
        return ""
    
    # Se já é URL completa, retorna direto
    if path.startswith("http://") or path.startswith("https://") or path.startswith("gs://"):
        return path
    
    settings = _get_settings()
    backend = getattr(settings, "storage_backend", "local")
    
    if backend == "local":
        media_url = getattr(settings, "storage_media_url", "/media/")
        base = media_url.rstrip("/")
        return f"{base}/{path}"
    
    if backend == "gcs":
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if not bucket_name:
            return path
        
        # Verifica se deve usar signed URLs (bucket privado)
        use_signed = getattr(settings, "storage_gcs_use_signed_urls", True)
        
        if not use_signed:
            # Bucket público - retorna URL direta
            media_url = getattr(settings, "storage_media_url", None)
            if media_url:
                base = media_url.rstrip("/")
                return f"{base}/{path}"
            return f"https://storage.googleapis.com/{bucket_name}/{path}"
        
        # Bucket privado - gera signed URL
        if expiration is None:
            expiration = getattr(settings, "storage_gcs_expiration_seconds", 3600)
        
        if isinstance(expiration, int):
            expiration = timedelta(seconds=expiration)
        
        try:
            client = _get_gcs_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(path)
            
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET",
            )
            return signed_url
        except Exception as e:
            logger.warning("Failed to generate signed URL for %s: %s", path, e)
            # Fallback para URL pública
            return f"https://storage.googleapis.com/{bucket_name}/{path}"
    
    return path


def delete_file(path_or_url: str) -> bool:
    """
    Remove o arquivo físico do backend (local ou GCS).
    
    Args:
        path_or_url: Valor armazenado no modelo (path relativo, URL pública ou gs://...).
    
    Returns:
        True se removeu ou não existia; False em erro (logado).
    """
    if not path_or_url or not isinstance(path_or_url, str):
        return True
    path_or_url = path_or_url.strip()
    if not path_or_url:
        return True
    
    settings = _get_settings()
    backend = getattr(settings, "storage_backend", "local")
    
    # Extrai o path relativo de URLs
    relative_path = _extract_relative_path(path_or_url)
    
    if backend == "local":
        root = Path(getattr(settings, "storage_local_media_root", "media"))
        root = root if root.is_absolute() else Path.cwd() / root
        full = root / relative_path
        try:
            if full.is_file():
                full.unlink()
                return True
            return True
        except OSError as e:
            logger.warning("Failed to delete local file %s: %s", full, e)
            return False
    
    if backend == "gcs":
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if not bucket_name:
            return True
        try:
            client = _get_gcs_client()
            bucket = client.bucket(bucket_name)
            bucket.blob(relative_path).delete()
            return True
        except Exception as e:
            logger.warning("Failed to delete GCS key %s: %s", relative_path, e)
            return False
    
    return True


def _extract_relative_path(path_or_url: str) -> str:
    """Extrai o path relativo de uma URL ou gs:// path."""
    settings = _get_settings()
    
    # gs://bucket/key
    if path_or_url.startswith("gs://"):
        m = re.match(r"gs://[^/]+/(.+)", path_or_url)
        if m:
            return m.group(1)
        return path_or_url
    
    # URL com query string (signed URL)
    if "?" in path_or_url:
        path_or_url = path_or_url.split("?")[0]
    
    # URL pública do GCS
    bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
    if bucket_name:
        gcs_prefix = f"https://storage.googleapis.com/{bucket_name}/"
        if path_or_url.startswith(gcs_prefix):
            return path_or_url[len(gcs_prefix):]
    
    # Media URL configurada
    media_url = getattr(settings, "storage_media_url", None)
    if media_url:
        base = media_url.rstrip("/")
        if path_or_url.startswith(base + "/"):
            return path_or_url[len(base) + 1:]
    
    # Já é path relativo
    if not path_or_url.startswith("http://") and not path_or_url.startswith("https://"):
        return path_or_url
    
    return path_or_url


def file_exists(path: str) -> bool:
    """
    Verifica se o arquivo existe no storage.
    
    Args:
        path: Path relativo do arquivo.
    
    Returns:
        True se o arquivo existe.
    """
    if not path:
        return False
    
    settings = _get_settings()
    backend = getattr(settings, "storage_backend", "local")
    relative_path = _extract_relative_path(path)
    
    if backend == "local":
        root = Path(getattr(settings, "storage_local_media_root", "media"))
        root = root if root.is_absolute() else Path.cwd() / root
        return (root / relative_path).is_file()
    
    if backend == "gcs":
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if not bucket_name:
            return False
        try:
            client = _get_gcs_client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(relative_path)
            return blob.exists()
        except Exception:
            return False
    
    return False


def get_storage_file_fields(admin_instance: Any) -> list[str]:
    """
    Retorna os nomes dos campos do model que são de arquivo (widget file_upload).
    
    Usado para saber quais atributos da instância contêm path/URL de arquivo
    ao oferecer "deletar arquivo físico" e ao efetivamente apagá-los.
    """
    try:
        columns = admin_instance.get_column_info()
    except Exception:
        return []
    return [
        c["name"]
        for c in columns
        if c.get("widget") == "file_upload"
    ]


def collect_file_paths(instance: Any, field_names: list[str]) -> list[str]:
    """
    Coleta os valores (path/URL) de arquivo de uma instância para os campos dados.
    
    Retorna lista de strings não vazias que representam arquivos armazenados.
    """
    result: list[str] = []
    for name in field_names:
        try:
            val = getattr(instance, name, None)
        except Exception:
            continue
        if isinstance(val, str) and val.strip():
            result.append(val.strip())
    return result


# ============================================================================
# Storage Field - Para usar como property em models (estilo Django)
# ============================================================================

class StorageFile:
    """
    Wrapper para campos de arquivo em models.
    
    Permite acessar .url e .name de forma similar ao Django FileField.
    
    Uso no model:
        class MyModel(Model):
            _file_path: Mapped[str] = Field.string(max_length=500)
            
            @property
            def file(self) -> StorageFile:
                return StorageFile(self._file_path)
        
        # Uso:
        model.file.name  # "uploads/image.jpg"
        model.file.url   # "https://...?X-Goog-Signature=..." (signed URL)
        bool(model.file) # True se tem arquivo
    """
    
    def __init__(self, path: str | None, expiration: int | timedelta | None = None):
        self._path = path or ""
        self._expiration = expiration
    
    @property
    def name(self) -> str:
        """Retorna o path relativo do arquivo."""
        return self._path
    
    @property
    def url(self) -> str:
        """Retorna a URL de acesso (signed URL para bucket privado)."""
        if not self._path:
            return ""
        return get_file_url(self._path, self._expiration)
    
    @property
    def path(self) -> str:
        """Alias para name - retorna o path relativo."""
        return self._path
    
    def __bool__(self) -> bool:
        """Retorna True se tem arquivo."""
        return bool(self._path)
    
    def __str__(self) -> str:
        """Retorna o path do arquivo."""
        return self._path
    
    def __repr__(self) -> str:
        return f"StorageFile({self._path!r})"
    
    def exists(self) -> bool:
        """Verifica se o arquivo existe no storage."""
        return file_exists(self._path)
    
    def delete(self) -> bool:
        """Remove o arquivo do storage."""
        return delete_file(self._path)


def storage_file_property(field_name: str, expiration: int | timedelta | None = None):
    """
    Decorator para criar property de StorageFile em models.
    
    Uso:
        class MyModel(Model):
            cover_image_path: Mapped[str] = Field.string(max_length=500)
            
            cover_image = storage_file_property("cover_image_path")
        
        # Agora pode usar:
        model.cover_image.url   # Signed URL
        model.cover_image.name  # Path relativo
    """
    def getter(self):
        path = getattr(self, field_name, None)
        return StorageFile(path, expiration)
    
    return property(getter)
