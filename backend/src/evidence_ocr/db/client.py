"""Managed PyMongo Async MongoDB client lifecycle and dependency provider."""

from typing import Optional
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError
from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.core.errors import DatabaseUnavailableError
from evidence_ocr.core.logging import get_logger

logger = get_logger("evidence_ocr.db")


class DatabaseManager:
    """Manages a single application-wide AsyncMongoClient connection to MongoDB Atlas."""

    def __init__(self) -> None:
        self._client: Optional[AsyncMongoClient] = None
        self._default_db_name: str = "evidence_ocr"
        self._is_connected: bool = False

    @property
    def is_connected(self) -> bool:
        """Return whether client is initialized."""
        return self._is_connected and self._client is not None

    async def connect(self, settings: Optional[Settings] = None) -> None:
        """Initialize the asynchronous MongoDB client with configured timeouts."""
        cfg = settings or get_settings()
        self._default_db_name = cfg.mongodb_db_name

        # Mask credentials in logs
        sanitized_uri = cfg.mongodb_uri
        if "@" in sanitized_uri:
            prefix = sanitized_uri.split("@")[0]
            if "://" in prefix:
                scheme, _ = prefix.split("://", 1)
                sanitized_uri = f"{scheme}://***:***@{sanitized_uri.split('@', 1)[1]}"

        logger.info(
            "Initializing PyMongo Async client for database '%s' at %s",
            self._default_db_name,
            sanitized_uri,
        )

        self._client = AsyncMongoClient(
            cfg.mongodb_uri,
            connectTimeoutMS=cfg.mongodb_connect_timeout_ms,
            serverSelectionTimeoutMS=cfg.mongodb_server_selection_timeout_ms,
            appname="EvidenceOCR-Backend",
        )
        self._is_connected = True

    async def close(self) -> None:
        """Close client connections cleanly during application shutdown."""
        if self._client is not None:
            logger.info("Closing MongoDB client connections...")
            await self._client.close()
            self._client = None
            self._is_connected = False
            logger.info("MongoDB client closed.")

    async def ping(self) -> bool:
        """Verify active cluster connectivity. Raises DatabaseUnavailableError if ping fails."""
        if self._client is None:
            raise DatabaseUnavailableError("MongoDB client is not initialized.")
        try:
            # Send admin ping with tight timeout
            await self._client.admin.command("ping")
            return True
        except (PyMongoError, Exception) as exc:
            logger.warning("MongoDB ping failed: %s", str(exc))
            raise DatabaseUnavailableError(f"Database cluster unreachable: {str(exc)}") from exc

    def get_database(self, db_name: Optional[str] = None) -> AsyncDatabase:
        """Retrieve target AsyncDatabase handle."""
        if self._client is None:
            raise DatabaseUnavailableError("Cannot access database: MongoDB client is not initialized.")
        target_name = db_name or self._default_db_name
        return self._client[target_name]


# Module-level singleton instance
_db_manager = DatabaseManager()


def get_db_manager() -> DatabaseManager:
    """Return the global DatabaseManager instance."""
    return _db_manager


async def get_db() -> AsyncDatabase:
    """FastAPI dependency for accessing the primary AsyncDatabase."""
    manager = get_db_manager()
    return manager.get_database()
