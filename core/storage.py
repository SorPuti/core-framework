"""
Storage de arquivos — plug-and-play local ou Google Cloud Storage.

Usado pelo Admin Panel para upload de arquivos em campos que armazenam
path ou URL (file_upload widget). Também usado na exclusão para remover
arquivos físicos quando o usuário opta por "deletar arquivos junto".

Uso:
    from core.storage import save_file, delete_file, get_storage_file_fields, collect_file_paths

    path = save_file("uploads/2025/02/abc.jpg", file_bytes, "image/jpeg")
    delete_file(path)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("core.storage")


def _get_settings() -> Any:
    from core.config import get_settings
    return get_settings()


def save_file(relative_path: str, content: bytes, content_type: str | None = None) -> str:
    """
    Salva conteúdo no backend configurado (local ou GCS).
    
    Args:
        relative_path: Caminho relativo (ex: uploads/2025/02/uuid-foto.jpg).
        content: Conteúdo binário do arquivo.
        content_type: MIME type (opcional; usado no GCS).
    
    Returns:
        Path ou URL a ser armazenado no modelo (ex: uploads/2025/02/abc.jpg
        ou https://storage.googleapis.com/bucket/uploads/...).
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
        try:
            from google.cloud import storage as gcs_storage
        except ImportError:
            raise RuntimeError(
                "Google Cloud Storage requires 'google-cloud-storage'. "
                "Install with: pip install google-cloud-storage"
            )
        credentials_file = getattr(settings, "storage_gcs_credentials_file", None)
        project = getattr(settings, "storage_gcs_project", None)
        if credentials_file:
            client = gcs_storage.Client.from_service_account_file(
                credentials_file, project=project
            )
        else:
            client = gcs_storage.Client(project=project)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(relative_path)
        blob.upload_from_string(
            content,
            content_type=content_type or "application/octet-stream",
        )
        default_acl = getattr(settings, "storage_gcs_default_acl", None)
        if default_acl == "publicRead":
            try:
                blob.make_public()
            except Exception as e:
                logger.debug("Could not set ACL on blob %s: %s", relative_path, e)
        media_url = getattr(settings, "storage_media_url", None)
        if media_url:
            base = media_url.rstrip("/")
            return f"{base}/{relative_path}"
        return f"gs://{bucket_name}/{relative_path}"
    
    raise ValueError(f"Unknown storage_backend: {backend}")


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
    
    if path_or_url.startswith("gs://"):
        # gs://bucket/key
        try:
            from google.cloud import storage as gcs_storage
        except ImportError:
            logger.warning("Cannot delete GCS file: google-cloud-storage not installed")
            return False
        m = re.match(r"gs://([^/]+)/(.+)", path_or_url)
        if not m:
            return True
        bucket_name, key = m.group(1), m.group(2)
        try:
            client = gcs_storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(key)
            blob.delete()
            return True
        except Exception as e:
            logger.warning("Failed to delete GCS file %s: %s", path_or_url, e)
            return False
    
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        # URL pública — no GCS o objeto é identificado pelo path após o bucket
        media_url = getattr(settings, "storage_media_url", None)
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if backend == "gcs" and bucket_name and media_url:
            base = media_url.rstrip("/")
            if path_or_url.startswith(base + "/"):
                key = path_or_url[len(base) + 1 :].split("?")[0]
                try:
                    from google.cloud import storage as gcs_storage
                except ImportError:
                    return False
                try:
                    client = gcs_storage.Client()
                    bucket = client.bucket(bucket_name)
                    bucket.blob(key).delete()
                    return True
                except Exception as e:
                    logger.warning("Failed to delete GCS file by URL %s: %s", path_or_url, e)
                    return False
        return True  # URL externa — não tentamos apagar
    
    # Path relativo (local ou key GCS)
    if backend == "local":
        root = Path(getattr(settings, "storage_local_media_root", "media"))
        root = root if root.is_absolute() else Path.cwd() / root
        full = root / path_or_url
        try:
            if full.is_file():
                full.unlink()
                return True
            return True
        except OSError as e:
            logger.warning("Failed to delete local file %s: %s", full, e)
            return False
    
    if backend == "gcs":
        try:
            from google.cloud import storage as gcs_storage
        except ImportError:
            return False
        bucket_name = getattr(settings, "storage_gcs_bucket_name", None)
        if not bucket_name:
            return True
        try:
            client = gcs_storage.Client()
            bucket = client.bucket(bucket_name)
            bucket.blob(path_or_url).delete()
            return True
        except Exception as e:
            logger.warning("Failed to delete GCS key %s: %s", path_or_url, e)
            return False
    
    return True


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
