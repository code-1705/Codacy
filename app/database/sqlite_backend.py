"""
FinGuard Tier 2: Local SQLite Backend
High-performance local ACID audit store and in-process vector cosine similarity engine.
"""
import sqlite3
import json
import time
import os
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

DEFAULT_SQLITE_PATH = ".finguard/memory.db"

# Rule elevation mapping for matched bug categories
CATEGORY_TO_ELEVATED_RULES = {
    "DOUBLE_SPEND_RACE": ["RULE-RACE-CONDITION", "AST-FIN-004"],
    "MISSING_IDEMPOTENCY_RETRY": ["AST-FIN-002", "RULE-RETRY-IDEMPOTENCY"],
    "FLOAT_PRECISION_DRIFT": ["AST-FIN-001"],
    "TRANSACTION_LOCK_EXHAUSTION": ["AST-FIN-003"],
}

DEFAULT_SEED_INCIDENTS = [
    {
        "pr_url": "https://github.com/org/payments/pull/1042",
        "bug_category": "DOUBLE_SPEND_RACE",
        "description": "Concurrent withdrawal debit allowed customer wallet balance to drop below zero due to uncommitted race condition.",
        "root_cause": "Missing row-level lock (SELECT FOR UPDATE) before balance decrement in concurrent transaction.",
        "remediation": "Enforce SELECT ... FOR UPDATE or optimistic version concurrency lock on account ledger prior to debit.",
        "fix_commit_sha": "a1b2c3d4e5f678901234567890abcdef12345678"
    },
    {
        "pr_url": "https://github.com/org/billing/pull/2180",
        "bug_category": "MISSING_IDEMPOTENCY_RETRY",
        "description": "Network gateway retry billed customer card twice due to missing idempotency key guard on payment route.",
        "root_cause": "FastAPI payment endpoint lacked Idempotency-Key header validation and duplicate request cache check.",
        "remediation": "Demand Idempotency-Key header and store transaction idempotency token in unique index before charging.",
        "fix_commit_sha": "b2c3d4e5f6a178901234567890abcdef12345679"
    },
    {
        "pr_url": "https://github.com/org/ledger/pull/3091",
        "bug_category": "FLOAT_PRECISION_DRIFT",
        "description": "Fee calculation using raw Python float literals caused IEEE 754 precision drift resulting in $0.03 ledger mismatch.",
        "root_cause": "Used float arithmetic and casting instead of decimal.Decimal or integer micro-cents.",
        "remediation": "Migrate all currency rates and fee calculations to decimal.Decimal or integer micro-cents.",
        "fix_commit_sha": "c3d4e5f6a1b278901234567890abcdef12345680"
    },
    {
        "pr_url": "https://github.com/org/settlement/pull/4412",
        "bug_category": "TRANSACTION_LOCK_EXHAUSTION",
        "description": "External payment gateway HTTP call inside database transaction lock caused connection pool exhaustion and deadlocks.",
        "root_cause": "Invoked requests.post() directly inside with db.begin() ACID transaction block.",
        "remediation": "Execute external network requests outside transaction lock; record state changes in separate fast transaction.",
        "fix_commit_sha": "d4e5f6a1b2c378901234567890abcdef12345681"
    }
]

DEFAULT_RULES = [
    ReviewRule("AST-FIN-001", "FloatInCurrencyArithmetic", base_weight=1.5, current_weight=1.5),
    ReviewRule("AST-FIN-002", "MissingIdempotencyGuard", base_weight=2.0, current_weight=2.0),
    ReviewRule("AST-FIN-003", "NetworkCallInsideTransactionBlock", base_weight=2.2, current_weight=2.2),
    ReviewRule("AST-FIN-004", "UncheckedDebitReturn", base_weight=1.8, current_weight=1.8),
    ReviewRule("RULE-RACE-CONDITION", "ConcurrentBalanceMutationRace", base_weight=1.8, current_weight=1.8),
    ReviewRule("RULE-RETRY-IDEMPOTENCY", "MissingWebhookRetryGuard", base_weight=2.5, current_weight=2.5),
]


class SQLiteDatabaseBackend:
    """Local SQLite database manager for offline / developer environments."""

    def __init__(self, db_path: str = DEFAULT_SQLITE_PATH):
        self.db_path = db_path
        # Ensure parent directory exists
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self._init_tables()
        self.seed_defaults_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Review Sessions Audit Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_sessions (
                    id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    pr_id TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    findings_count INTEGER DEFAULT 0,
                    dlp_status TEXT NOT NULL,
                    execution_duration_ms INTEGER NOT NULL,
                    quality_score REAL DEFAULT 10.0,
                    user_id TEXT DEFAULT 'default_user',
                    language TEXT DEFAULT 'python',
                    created_at TEXT NOT NULL
                )
            """)
            # Ensure columns exist if table was already created earlier
            try:
                cursor.execute("ALTER TABLE review_sessions ADD COLUMN quality_score REAL DEFAULT 10.0")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE review_sessions ADD COLUMN user_id TEXT DEFAULT 'default_user'")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE review_sessions ADD COLUMN language TEXT DEFAULT 'python'")
            except sqlite3.OperationalError:
                pass

            # 2. Historical PR Incidents Vector Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_pr_incidents (
                    id TEXT PRIMARY KEY,
                    pr_url TEXT NOT NULL,
                    bug_category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    remediation TEXT NOT NULL,
                    fix_commit_sha TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # 3. Dynamic Rule Registry Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS review_rules (
                    rule_id TEXT PRIMARY KEY,
                    rule_name TEXT NOT NULL,
                    base_weight REAL DEFAULT 1.0,
                    current_weight REAL DEFAULT 1.0,
                    ci_flakiness_correlation REAL DEFAULT 0.0,
                    revert_count INTEGER DEFAULT 0,
                    last_updated TEXT NOT NULL
                )
            """)
            conn.commit()

    def seed_defaults_if_empty(self):
        """Seeds initial FinTech incident precedents and review rules if tables are empty."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check review_rules
            cursor.execute("SELECT COUNT(*) FROM review_rules")
            if cursor.fetchone()[0] == 0:
                for rule in DEFAULT_RULES:
                    cursor.execute("""
                        INSERT INTO review_rules (rule_id, rule_name, base_weight, current_weight, ci_flakiness_correlation, revert_count, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (rule.rule_id, rule.rule_name, rule.base_weight, rule.current_weight, rule.ci_flakiness_correlation, rule.revert_count, rule.last_updated))

            # Check historical_pr_incidents
            cursor.execute("SELECT COUNT(*) FROM historical_pr_incidents")
            if cursor.fetchone()[0] == 0:
                for inc in DEFAULT_SEED_INCIDENTS:
                    full_text = f"{inc['bug_category']} {inc['description']} {inc['root_cause']} {inc['remediation']}"
                    embedding = generate_deterministic_embedding(full_text)
                    import uuid
                    inc_id = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO historical_pr_incidents (id, pr_url, bug_category, description, root_cause, remediation, fix_commit_sha, embedding_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """, (inc_id, inc['pr_url'], inc['bug_category'], inc['description'], inc['root_cause'], inc['remediation'], inc['fix_commit_sha'], json.dumps(embedding)))

            conn.commit()

    # --- Review Sessions (ACID Audit Log) ---

    def log_session(self, session: ReviewSession) -> str:
        """Appends an immutable review session audit log entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO review_sessions (
                    id, repo_name, pr_id, commit_sha, author_id, payload_hash,
                    findings_count, dlp_status, execution_duration_ms, quality_score, user_id, language, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session.id, session.repo_name, session.pr_id, session.commit_sha,
                session.author_id, session.payload_hash, session.findings_count,
                session.dlp_status, session.execution_duration_ms,
                getattr(session, "quality_score", 10.0),
                getattr(session, "user_id", "default_user"),
                getattr(session, "language", "python"),
                session.created_at
            ))
            conn.commit()
            return session.id

    def get_session(self, session_id: str) -> Optional[ReviewSession]:
        """Retrieves a review session audit record by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM review_sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            keys = row.keys()
            return ReviewSession(
                id=row["id"],
                repo_name=row["repo_name"],
                pr_id=row["pr_id"],
                commit_sha=row["commit_sha"],
                author_id=row["author_id"],
                payload_hash=row["payload_hash"],
                findings_count=row["findings_count"],
                dlp_status=row["dlp_status"],
                execution_duration_ms=row["execution_duration_ms"],
                quality_score=row["quality_score"] if "quality_score" in keys else 10.0,
                user_id=row["user_id"] if "user_id" in keys else "default_user",
                language=row["language"] if "language" in keys else "python",
                created_at=row["created_at"]
            )

    def get_user_growth(self, user_id: str) -> Dict[str, Any]:
        """Calculates persistent developer growth and quality score progression over time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, repo_name, pr_id, quality_score, findings_count, language, created_at
                FROM review_sessions
                WHERE user_id = ? OR author_id = ?
                ORDER BY created_at ASC
            """, (user_id, user_id))
            rows = cursor.fetchall()
            if not rows:
                return {
                    "user_id": user_id,
                    "total_reviews": 0,
                    "average_score": 10.0,
                    "score_trajectory": [],
                    "improvement_delta": 0.0,
                    "language_distribution": {},
                    "verdict": "New Developer: No prior review sessions recorded."
                }

            scores = [float(r["quality_score"] or 10.0) for r in rows]
            avg_score = round(sum(scores) / len(scores), 1)
            initial_score = scores[0]
            latest_score = scores[-1]
            delta = round(latest_score - initial_score, 1)

            lang_dist: Dict[str, int] = {}
            for r in rows:
                lang = r["language"] or "python"
                lang_dist[lang] = lang_dist.get(lang, 0) + 1

            trajectory = [
                {
                    "session_id": r["id"],
                    "pr_id": r["pr_id"],
                    "quality_score": float(r["quality_score"] or 10.0),
                    "findings_count": r["findings_count"],
                    "language": r["language"] or "python",
                    "created_at": r["created_at"]
                }
                for r in rows
            ]

            return {
                "user_id": user_id,
                "total_reviews": len(rows),
                "average_score": avg_score,
                "initial_score": initial_score,
                "latest_score": latest_score,
                "improvement_delta": delta,
                "score_trajectory": trajectory,
                "language_distribution": lang_dist,
                "verdict": f"Tracked {len(rows)} reviews. Trajectory delta: {delta:+.1f} points."
            }

    # --- Semantic Vector Precedent Search ---

    def insert_incident(self, incident: HistoricalIncident) -> str:
        """Inserts a historical incident precedent with its vector embedding."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO historical_pr_incidents (id, pr_url, bug_category, description, root_cause, remediation, fix_commit_sha, embedding_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident.id, incident.pr_url, incident.bug_category,
                incident.description, incident.root_cause, incident.remediation,
                incident.fix_commit_sha, json.dumps(incident.embedding), incident.created_at
            ))
            conn.commit()
            return incident.id

    def search_precedents(
        self,
        query_embedding: List[float],
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> VectorQueryResult:
        """
        Executes in-process vector cosine similarity search across historical incidents.
        Filters out matches below min_similarity (default 0.78).
        """
        start_time = time.perf_counter()
        matches: List[Tuple[float, sqlite3.Row]] = []

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM historical_pr_incidents")
            rows = cursor.fetchall()

            for row in rows:
                try:
                    vec = json.loads(row["embedding_json"])
                    sim = cosine_similarity(query_embedding, vec)
                    if sim >= min_similarity:
                        matches.append((sim, row))
                except Exception:
                    continue

        # Sort descending by similarity score
        matches.sort(key=lambda x: x[0], reverse=True)
        top_matches = matches[:top_k]

        matched_precedents: List[MatchedPrecedent] = []
        elevated_rule_set = set()

        for sim, row in top_matches:
            category = row["bug_category"]
            matched_precedents.append(MatchedPrecedent(
                pr_id=row["pr_url"].split("/")[-1] if "/" in row["pr_url"] else row["id"],
                bug_category=category,
                similarity_score=round(sim, 4),
                description=row["description"],
                root_cause=row["root_cause"],
                remediation=row["remediation"],
                fix_commit_sha=row["fix_commit_sha"]
            ))
            # Elevate corresponding rules
            if category in CATEGORY_TO_ELEVATED_RULES:
                elevated_rule_set.update(CATEGORY_TO_ELEVATED_RULES[category])

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return VectorQueryResult(
            matched_precedents=matched_precedents,
            elevated_rules=sorted(list(elevated_rule_set)),
            query_duration_ms=round(elapsed_ms, 2)
        )

    def search_precedents_by_text(
        self,
        text: str,
        top_k: int = 3,
        min_similarity: float = 0.78
    ) -> VectorQueryResult:
        """Helper to generate deterministic embedding and query precedents."""
        query_embedding = generate_deterministic_embedding(text)
        return self.search_precedents(query_embedding, top_k=top_k, min_similarity=min_similarity)

    # --- Review Rules & Dynamic Weights ---

    def get_rule(self, rule_id: str) -> Optional[ReviewRule]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM review_rules WHERE rule_id = ?", (rule_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return ReviewRule(
                rule_id=row["rule_id"],
                rule_name=row["rule_name"],
                base_weight=row["base_weight"],
                current_weight=row["current_weight"],
                ci_flakiness_correlation=row["ci_flakiness_correlation"],
                revert_count=row["revert_count"],
                last_updated=row["last_updated"]
            )

    def list_rules(self) -> List[ReviewRule]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM review_rules ORDER BY current_weight DESC")
            return [
                ReviewRule(
                    rule_id=row["rule_id"],
                    rule_name=row["rule_name"],
                    base_weight=row["base_weight"],
                    current_weight=row["current_weight"],
                    ci_flakiness_correlation=row["ci_flakiness_correlation"],
                    revert_count=row["revert_count"],
                    last_updated=row["last_updated"]
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
        """Updates rule priority weight bounded by [0.2, 5.0]."""
        bounded_weight = max(0.2, min(5.0, new_weight))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if ci_correlation is not None:
                cursor.execute("""
                    UPDATE review_rules
                    SET current_weight = ?,
                        ci_flakiness_correlation = ?,
                        revert_count = revert_count + ?,
                        last_updated = datetime('now')
                    WHERE rule_id = ?
                """, (bounded_weight, ci_correlation, 1 if increment_reverts else 0, rule_id))
            else:
                cursor.execute("""
                    UPDATE review_rules
                    SET current_weight = ?,
                        revert_count = revert_count + ?,
                        last_updated = datetime('now')
                    WHERE rule_id = ?
                """, (bounded_weight, 1 if increment_reverts else 0, rule_id))
            conn.commit()
