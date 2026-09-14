"""FinGuard Tier 2: Cloud SQL & pgvector Database Package"""
from app.database.models import (
    ReviewSession,
    HistoricalIncident,
    ReviewRule,
    MatchedPrecedent,
    VectorQueryResult
)
from app.database.manager import DatabaseManager
from app.database.sqlite_backend import SQLiteDatabaseBackend
from app.database.cloudsql_backend import CloudSQLDatabaseBackend
from app.database.vector_math import (
    cosine_similarity,
    generate_deterministic_embedding,
    EMBEDDING_DIM
)

__all__ = [
    "DatabaseManager",
    "ReviewSession",
    "HistoricalIncident",
    "ReviewRule",
    "MatchedPrecedent",
    "VectorQueryResult",
    "SQLiteDatabaseBackend",
    "CloudSQLDatabaseBackend",
    "cosine_similarity",
    "generate_deterministic_embedding",
    "EMBEDDING_DIM",
]
