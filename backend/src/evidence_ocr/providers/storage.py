"""Abstract provider interfaces and concrete implementations for object and GridFS storage."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, Optional
from bson import ObjectId
from gridfs import AsyncGridFSBucket
from gridfs.errors import NoFile
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.core.errors import EntityNotFoundError, StorageOperationError
from evidence_ocr.core.logging import get_logger

logger = get_logger("evidence_ocr.providers.storage")


class BaseStorageProvider(ABC):
    """Abstract interface for document file storage (e.g. MongoDB GridFS, S3, GCS)."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Upload byte payload and return persistent object key or GridFS file ID string."""
        pass

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Retrieve stored bytes for an object key or GridFS file ID."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete stored object by key or GridFS file ID."""
        pass

    @abstractmethod
    async def open_download_stream(self, key: str) -> Any:
        """Open an asynchronous read stream for the stored file."""
        pass

    @abstractmethod
    async def generate_access_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        """Generate access URL or relative streaming path for client retrieval."""
        pass


class GridFSStorageProvider(BaseStorageProvider):
    """Production storage provider backed exclusively by PyMongo AsyncGridFSBucket on MongoDB Atlas."""

    def __init__(self, db: AsyncDatabase, bucket_name: str = "evidence_files") -> None:
        self._db = db
        self._bucket_name = bucket_name
        self._bucket = AsyncGridFSBucket(db, bucket_name=bucket_name)

    @property
    def bucket(self) -> AsyncGridFSBucket:
        return self._bucket

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store bytes into GridFS and return hexadecimal GridFS file ID."""
        meta = dict(metadata or {})
        meta["content_type"] = content_type
        meta["key"] = key
        try:
            grid_in = self._bucket.open_upload_stream(filename=key, metadata=meta)
            await grid_in.write(data)
            await grid_in.close()
            file_id_str = str(grid_in._id)
            logger.debug("Stored %d bytes in GridFS bucket '%s' with id %s", len(data), self._bucket_name, file_id_str)
            return file_id_str
        except Exception as exc:
            logger.error("Failed to upload binary to GridFS bucket '%s': %s", self._bucket_name, exc)
            raise StorageOperationError(f"GridFS upload failed: {str(exc)}") from exc

    async def upload_stream(
        self,
        key: str,
        stream: Any,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: int = 64 * 1024,
    ) -> str:
        """Stream chunks into GridFS without loading entire payload into memory at once."""
        meta = dict(metadata or {})
        meta["content_type"] = content_type
        meta["key"] = key
        try:
            grid_in = self._bucket.open_upload_stream(filename=key, metadata=meta)
            while True:
                chunk = await stream.read(chunk_size)
                if not chunk:
                    break
                await grid_in.write(chunk)
            await grid_in.close()
            file_id_str = str(grid_in._id)
            logger.debug("Streamed file to GridFS bucket '%s' with id %s", self._bucket_name, file_id_str)
            return file_id_str
        except Exception as exc:
            logger.error("Failed to stream binary to GridFS: %s", exc)
            raise StorageOperationError(f"GridFS streaming upload failed: {str(exc)}") from exc

    async def download(self, key: str) -> bytes:
        """Retrieve complete file bytes from GridFS."""
        grid_out = await self.open_download_stream(key)
        try:
            return await grid_out.read()
        except Exception as exc:
            logger.error("Error reading GridFS stream for key %s: %s", key, exc)
            raise StorageOperationError(f"Failed to read GridFS file: {str(exc)}") from exc

    async def open_download_stream(self, key: str) -> Any:
        """Open an AsyncGridOut download stream by ObjectId or filename."""
        try:
            if ObjectId.is_valid(key):
                return await self._bucket.open_download_stream(ObjectId(key))
            return await self._bucket.open_download_stream_by_name(key)
        except NoFile:
            raise EntityNotFoundError("GridFSFile", key)
        except Exception as exc:
            logger.error("Failed to open download stream for key %s: %s", key, exc)
            raise StorageOperationError(f"GridFS download failed: {str(exc)}") from exc

    async def delete(self, key: str) -> bool:
        """Remove file and associated chunks from GridFS. Returns True on success."""
        try:
            if ObjectId.is_valid(key):
                await self._bucket.delete(ObjectId(key))
                logger.info("Successfully deleted GridFS file id %s", key)
                return True
            else:
                await self._bucket.delete_by_name(key)
                logger.info("Successfully deleted GridFS file by name %s", key)
                return True
        except NoFile:
            logger.warning("Attempted to delete non-existent GridFS file %s", key)
            return False
        except Exception as exc:
            logger.error("Failed to delete GridFS file %s: %s", key, exc)
            return False

    async def generate_access_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        """Return relative API endpoint for file streaming."""
        # For GridFS, access is streamed securely via backend router
        return f"/api/v1/documents/{key}/file"


class MockGridOut:
    """Mock stream mimicking AsyncGridOut for unit tests and local mocks."""

    def __init__(self, data: bytes, filename: str = "mock_file.dat", content_type: str = "application/octet-stream") -> None:
        self._data = data
        self.filename = filename
        self.length = len(data)
        self.metadata = {"content_type": content_type}
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        if size == -1:
            chunk = self._data[self._pos:]
            self._pos = len(self._data)
            return chunk
        chunk = self._data[self._pos: self._pos + size]
        self._pos += len(chunk)
        return chunk


class MockStorageProvider(BaseStorageProvider):
    """In-memory object storage provider for testing and isolated unit tests."""

    def __init__(self, base_url: str = "/api/v1/documents") -> None:
        self._store: Dict[str, bytes] = {}
        self._content_types: Dict[str, str] = {}
        self._base_url = base_url

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        self._store[key] = data
        self._content_types[key] = content_type
        return key

    async def download(self, key: str) -> bytes:
        if key not in self._store:
            raise EntityNotFoundError("StorageKey", key)
        return self._store[key]

    async def open_download_stream(self, key: str) -> MockGridOut:
        if key not in self._store:
            raise EntityNotFoundError("StorageKey", key)
        content_type = self._content_types.get(key, "application/octet-stream")
        return MockGridOut(self._store[key], filename=key, content_type=content_type)

    async def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            self._content_types.pop(key, None)
            return True
        return False

    async def generate_access_url(self, key: str, expires_in_seconds: int = 3600) -> str:
        return f"{self._base_url}/{key}/file"
