"""
FinGuard Tier 2: Google Cloud SQL PostgreSQL 16 + pgvector Backend
High-performance managed PostgreSQL backend for Cloud Run production deployment.
"""
import time
import os
import json
from typing import List, Optional, Dict, Any, Tuple
from app.database.models import (
    ReviewSession,
    HistoricalIncident,
    ReviewRule,
    MatchedPrecedent,
    VectorQueryResult
)
from app.database.vector_math import (
    cosine_similarity,
    generate_deterministic_embedding,
    EMBEDDING_DIM
)
from app.database.sqlite_backend import (
    CATEGORY_TO_ELEVATED_RULES,
    DEFAULT_SEED_INCIDENTS,
    DEFAULT_RULES
)


class CloudSQLDatabaseBackend:
    """
    Google Cloud SQL PostgreSQL 16 database backend.
    Uses pgvector extension with HNSW indexing for sub-25ms vector cosine similarity searches.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self._is_connected = False
        self._conn = None
        if self.dsn:
            self._try_connect()

    def _try_connect(self):
        try:
            import psycopg2
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True
            self._is_connected = True
            self._init_pgvector_schema()
        except Exception:
            self._is_connected = False
            self._conn = None

    @property
    def is_available(self) -> bool:
        return self._is_connected and self._conn is not None

    def _init_pgvector_schema(self):
        if not self.is_available:
            return
        with self._conn.cursor() as cursor:
            # Enable extensions
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
            cursor.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

            # Table 1: Review Sessions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_sessions (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    repo_name VARCHAR(255) NOT NULL,
                    pr_id VARCHAR(64) NOT NULL,
                    commit_sha VARCHAR(40) NOT NULL,
                    author_id VARCHAR(128) NOT NULL,
                    payload_hash VARCHAR(64) NOT NULL,
                    findings_count INT DEFAULT 0,
                    dlp_status VARCHAR(32) NOT NULL,
                    execution_duration_ms INT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Table 2: Historical PR Incidents with pgvector
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS historical_pr_incidents (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    pr_url VARCHAR(512) NOT NULL,
                    bug_category VARCHAR(64) NOT NULL,
                    description TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    remediation TEXT NOT NULL,
                    fix_commit_sha VARCHAR(40) NOT NULL,
                    embedding vector({EMBEDDING_DIM}),
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # HNSW Index for sub-25ms nearest neighbor search
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_historical_pr_embeddings 
                ON historical_pr_incidents 
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)

            # Table 3: Review Rules
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_rules (
                    rule_id VARCHAR(64) PRIMARY KEY,
                    rule_name VARCHAR(255) NOT NULL,
                    base_weight FLOAT DEFAULT 1.0,
                    current_weight FLOAT DEFAULT 1.0,
                    ci_flakiness_correlation FLOAT DEFAULT 0.0,
                    revert_count INT DEFAULT 0,
                    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def seed_defaults_if_empty(self):
        if not self.is_available:
            return
        with self._conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM review_rules;")
            if cursor.fetchone()[0] == 0:
                for rule in DEFAULT_RULES:
                    cursor.execute("""
                        INSERT INTO review_rules (rule_id, rule_name, base_weight, current_weight, ci_flakiness_correlation, revert_count, last_updated)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (rule_id) DO NOTHING;
                    """, (rule.rule_id, rule.rule_name, rule.base_weight, rule.current_weight, rule.ci_flakiness_correlation, rule.revert_count))

            cursor.execute("SELECT COUNT(*) FROM historical_pr_incidents;")
            if cursor.fetchone()[0] == 0:
                for inc in DEFAULT_SEED_INCIDENTS:
                    full_text = f"{inc['bug_category']} {inc['description']} {inc['root_cause']} {inc['remediation']}"
                    emb = generate_deterministic_embedding(full_text)
                    emb_str = "[" + ",".join(str(x) for x in emb) + "]"
                    cursor.execute("""
                        INSERT INTO historical_pr_incidents (pr_url, bug_category, description, root_cause, remediation, fix_commit_sha, embedding, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::vector, NOW());
                    """, (inc['pr_url'], inc['bug_category'], inc['description'], inc['root_cause'], inc['remediation'], inc['fix_commit_sha'], emb_str))

    def log_session(self, session: ReviewSession) -> str:
        if not self.is_available:
            raise ConnectionError("Cloud SQL PostgreSQL is not connected.")
        with self._conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO review_sessions (id, repo_name, pr_id, commit_sha, author_id, payload_hash, findings_count, dlp_status, execution_duration_ms, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session.id, session.repo_name, session.pr_id, session.commit_sha,
                session.author_id, session.payload_hash, session.findings_count,
                session.dlp_status, session.execution_duration_ms, session.created_at
            ))
            return session.id

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        if not self.is_available:
            return None
        with self._conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, repo_name, pr_id, commit_sha, author_id, payload_hash, findings_count, dlp_status, execution_duration_ms, created_at
                FROM review_sessions WHERE id = %s
            """, (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReviewSession(
                id=str(row[0]),
                repo_name=row[1],
                pr_id=row[2],
                commit_sha=row[3],
                author_id=row[4],
                payload_hash=row[5],
                findings_count=row[6],
                dlp_status=row[7],
                execution_duration_ms=row[8],
                created_at=str(row[9])
            )

    def search_precedents(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> VectorQueryResult:
        if not self.is_available:
            raise ConnectionError("Cloud SQL PostgreSQL is not connected.")
        
        start_time = time.perf_counter()
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        with self._conn.cursor() as cursor:
            # 1 - cosine distance <=> gives cosine similarity
            cursor.execute("""
                SELECT pr_url, bug_category, description, root_cause, remediation, fix_commit_sha,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM historical_pr_incidents
                WHERE 1 - (embedding <=> %s::vector) >= %s
                ORDER BY similarity DESC
                LIMIT %s
            """, (vec_str, vec_str, min_similarity, top_k))
            
            rows = cursor.fetchall()

        matched_precedents: List[MatchedPrecedent] = []
        elevated_rule_set = set()

        for row in rows:
            category = row[1]
            matched_precedents.append(MatchedPrecedent(
                pr_id=row[0].split("/")[-1] if "/" in row[0] else row[0],
                bug_category=category,
                similarity_score=round(row[6], 4),
                description=row[2],
                root_cause=row[3],
                remediation=row[4],
                fix_commit_sha=row[5]
            ))
            if category in CATEGORY_TO_ELEVATED_RULES:
                elevated_rule_set.update(CATEGORY_TO_ELEVATED_RULES[category])

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return VectorQueryResult(
            matched_precedents=matched_precedents,
            elevated_rules=sorted(list(elevated_rule_set)),
            query_duration_ms=round(elapsed_ms, 2)
        )

    def get_rule(self, rule_id: str) -> Optional[ReviewRule]:
        if not self.is_available:
            return None
        with self._conn.cursor() as cursor:
            cursor.execute("""
                SELECT rule_id, rule_name, base_weight, current_weight, ci_flakiness_correlation, revert_count, last_updated
                FROM review_rules WHERE rule_id = %s
            """, (rule_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReviewRule(
                rule_id=row[0],
                rule_name=row[1],
                base_weight=row[2],
                current_weight=row[3],
                ci_flakiness_correlation=row[4],
                revert_count=row[5],
                last_updated=str(row[6])
            )

    def list_rules(self) -> List[ReviewRule]:
        if not self.is_available:
            return []
        with self._conn.cursor() as cursor:
            cursor.execute("""
                SELECT rule_id, rule_name, base_weight, current_weight, ci_flakiness_correlation, revert_count, last_updated
                FROM review_rules ORDER BY current_weight DESC
            """)
            return [
                ReviewRule(
                    rule_id=row[0],
                    rule_name=row[1],
                    base_weight=row[2],
                    current_weight=row[3],
                    ci_flakiness_correlation=row[4],
                    revert_count=row[5],
                    last_updated=str(row[6])
                )
                for row in cursor.fetchall()
            ]

    def update_rule_weight(
        self,
        rule_id: str,
        new_weight: float,
        ci_correlation: Optional[float] = None,
        increment_reverts: bool = False
    ):
        if not self.is_available:
            return
        bounded_weight = max(0.2, min(5.0, new_weight))
        with self._conn.cursor() as cursor:
            if ci_correlation is not None:
                cursor.execute("""
                    UPDATE review_rules
                    SET current_weight = %s,
                        ci_flakiness_correlation = %s,
                        revert_count = revert_count + %s,
                        last_updated = NOW()
                    WHERE rule_id = %s
                """, (bounded_weight, ci_correlation, 1 if increment_reverts else 0, rule_id))
            else:
                cursor.execute("""
                    UPDATE review_rules
                    SET current_weight = %s,
                        revert_count = revert_count + %s,
                        last_updated = NOW()
                    WHERE rule_id = %s
                """, (bounded_weight, 1 if increment_reverts else 0, rule_id))

