"""Database management and repository package."""

from evidence_ocr.db.client import DatabaseManager, get_db_manager

__all__ = ["DatabaseManager", "get_db_manager"]
