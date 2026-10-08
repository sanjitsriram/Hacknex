"""Abstract provider interfaces and mock implementations for object storage."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseStorageProvider(ABC):
    """Abstract interface for document file storage (e.g. S3, GCS, Azure Blob)."""

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Upload byte payload and return persistent object key."""
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Retrieve stored bytes for an object key."""
        pass

    @abstractmethod
    async def generate_access_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        """Generate time-limited signed URL for client download."""
        pass


class MockStorageProvider(BaseStorageProvider):
    """In-memory object storage provider for testing and offline local development."""

    def __init__(self, base_url: str = "http://localhost:8000/storage") -> None:
        self._store: Dict[str, bytes] = {}
        self._content_types: Dict[str, str] = {}
        self._base_url = base_url

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        self._store[key] = data
        self._content_types[key] = content_type
        return key

    async def download(self, key: str) -> bytes:
        if key not in self._store:
            raise KeyError(f"Storage key '{key}' not found.")
        return self._store[key]

    async def generate_access_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        return f"{self._base_url}/{key}?exp={expires_in_seconds}"
