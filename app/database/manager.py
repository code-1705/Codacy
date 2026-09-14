"""
FinGuard Tier 2: Unified Database Manager
Provides seamless switching between Local SQLite (offline/developer) and Google Cloud SQL pgvector (Cloud Run production).
"""
import os
from typing import Optional, List, Dict, Any
from app.database.models import (
    ReviewSession,
    HistoricalIncident,
    ReviewRule,
    MatchedPrecedent,
    VectorQueryResult
)
from app.database.sqlite_backend import SQLiteDatabaseBackend, DEFAULT_SQLITE_PATH
from app.database.cloudsql_backend import CloudSQLDatabaseBackend


class DatabaseManager:
    """Unified access layer managing ACID audit sessions and semantic vector memory."""

    def __init__(
        self,
        backend: str = "sqlite",
        sqlite_path: str = DEFAULT_SQLITE_PATH,
        cloudsql_dsn: Optional[str] = None
    ):
        self.backend_type = backend.lower()
        self.sqlite = SQLiteDatabaseBackend(db_path=sqlite_path)
        self.cloudsql = CloudSQLDatabaseBackend(dsn=cloudsql_dsn) if cloudsql_dsn or os.getenv("DATABASE_URL") else None

    @property
    def active_backend_name(self) -> str:
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            return "cloudsql_pgvector"
        return "local_sqlite"

    def log_session(self, session: ReviewSession) -> str:
        """Logs an immutable review session to active ACID storage."""
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                return self.cloudsql.log_session(session)
            except Exception:
                pass
        return self.sqlite.log_session(session)

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        """Retrieves a review session by ID."""
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                res = self.cloudsql.get_session(session_id)
                if res:
                    return res
            except Exception:
                pass
        return self.sqlite.get_session(session_id)

    def search_precedents(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> VectorQueryResult:
        """Executes vector cosine similarity search for historical incident precedents."""
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                return self.cloudsql.search_precedents(query_embedding, top_k=top_k, min_similarity=min_similarity)
            except Exception:
                pass
        return self.sqlite.search_precedents(query_embedding, top_k=top_k, min_similarity=min_similarity)

    def search_precedents_by_text(
        self,
        text: str,
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> VectorQueryResult:
        """Executes vector similarity search using text diff or AST summary."""
        query_embedding = self.sqlite.search_precedents_by_text(text, top_k=top_k, min_similarity=min_similarity)
        return query_embedding

    def get_rule(self, rule_id: str) -> Optional[ReviewRule]:
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                res = self.cloudsql.get_rule(rule_id)
                if res:
                    return res
            except Exception:
                pass
        return self.sqlite.get_rule(rule_id)

    def list_rules(self) -> List[ReviewRule]:
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                rules = self.cloudsql.list_rules()
                if rules:
                    return rules
            except Exception:
                pass
        return self.sqlite.list_rules()

    def update_rule_weight(
        self,
        rule_id: str,
        new_weight: float,
        ci_correlation: Optional[float] = None,
        increment_reverts: bool = False
    ):
        if self.backend_type == "cloudsql" and self.cloudsql and self.cloudsql.is_available:
            try:
                self.cloudsql.update_rule_weight(
                    rule_id=rule_id,
                    new_weight=new_weight,
                    ci_correlation=ci_correlation,
                    increment_reverts=increment_reverts
                )
            except Exception:
                pass
        self.sqlite.update_rule_weight(
            rule_id=rule_id,
            new_weight=new_weight,
            ci_correlation=ci_correlation,
            increment_reverts=increment_reverts
        )

