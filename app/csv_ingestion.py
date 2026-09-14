"""
FinGuard Historical CSV Ingestion Engine
Parses and vectorizes historical review data provided in the schema:
<id>, <type>, <description>
Examples:
  1, formatting, Avoid single-character variable names — they hurt readability
  2, performance, Cache repeated database lookups inside the request loop
  3, security, Never interpolate raw user input directly into SQL queries
Satisfies Track 1 mandate: Historical Review Data Ingestion & Learning.
"""
import csv
import io
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, asdict

from app.database.models import ReviewRule
from app.database.vector_math import generate_deterministic_embedding


@dataclass
class CSVIngestionRecord:
    rule_id: str
    rule_type: str  # e.g., "formatting", "performance", "security", "concurrency"
    description: str
    embedding: List[float]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_historical_csv_content(csv_text: str) -> List[CSVIngestionRecord]:
    """
    Parses CSV content matching schema: <id>, <type>, <description>.
    Supports raw text without headers or with headers ('id,type,description').
    Tolerates commas inside quoted descriptions.
    """
    records: List[CSVIngestionRecord] = []
    lines = [l.strip() for l in csv_text.splitlines() if l.strip()]
    if not lines:
        return records

    reader = csv.reader(lines)
    for row in reader:
        if not row:
            continue
        # Check if header row
        first_col = row[0].strip().lower()
        if first_col in ("id", "<id>"):
            continue

        if len(row) >= 3:
            rule_id = f"CSV-HIST-{row[0].strip()}"
            rule_type = row[1].strip().lower()
            # Join remaining columns in case description contained unescaped commas
            description = ", ".join(col.strip() for col in row[2:])
        elif len(row) == 2:
            rule_id = f"CSV-HIST-{row[0].strip()}"
            rule_type = "general"
            description = row[1].strip()
        else:
            continue

        if not description:
            continue

        full_text = f"[{rule_type.upper()}] {description}"
        embedding = generate_deterministic_embedding(full_text)

        records.append(CSVIngestionRecord(
            rule_id=rule_id,
            rule_type=rule_type,
            description=description,
            embedding=embedding
        ))

    return records


def ingest_csv_into_database(csv_text: str, db_manager) -> Dict[str, Any]:
    """
    Parses CSV and registers records into active database as ReviewRules and HistoricalIncidents.
    Immediately updates vector memory so Vertex AI / Gemini can retrieve them during grounding.
    """
    records = parse_historical_csv_content(csv_text)
    ingested_count = 0

    backend = getattr(db_manager, "sqlite", None)
    if not backend and hasattr(db_manager, "_get_connection"):
        backend = db_manager

    for rec in records:
        rule_name = f"{rec.rule_type.capitalize()}Guard: {rec.description[:40]}..."
        # 1. Store as ReviewRule
        rule = ReviewRule(
            rule_id=rec.rule_id,
            rule_name=rule_name,
            base_weight=1.5,
            current_weight=1.5,
            ci_flakiness_correlation=0.0,
            revert_count=0
        )
        if backend and hasattr(backend, "_get_connection"):
            with backend._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO review_rules (rule_id, rule_name, base_weight, current_weight, ci_flakiness_correlation, revert_count, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(rule_id) DO UPDATE SET
                        rule_name = excluded.rule_name,
                        current_weight = excluded.current_weight,
                        last_updated = datetime('now')
                """, (rule.rule_id, rule.rule_name, rule.base_weight, rule.current_weight, rule.ci_flakiness_correlation, rule.revert_count))
                
                # Also store into historical_pr_incidents so vector search immediately surfaces it
                import json
                cursor.execute("""
                    INSERT INTO historical_pr_incidents (id, pr_url, bug_category, description, root_cause, remediation, fix_commit_sha, embedding_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        description = excluded.description,
                        embedding_json = excluded.embedding_json
                """, (
                    rec.rule_id,
                    f"csv://imported/{rec.rule_id}",
                    rec.rule_type.upper(),
                    rec.description,
                    f"Historical rule from review dataset: {rec.description}",
                    rec.description,
                    "csv_import_sha0000",
                    json.dumps(rec.embedding)
                ))
                conn.commit()
                ingested_count += 1

    return {
        "status": "SUCCESS",
        "ingested_count": ingested_count,
        "rules": [r.to_dict() for r in records]
    }
