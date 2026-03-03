"""
tools.py — All reusable pipeline tools.

Wraps db.py functions and adds:
  - execute_query()    : run SQL, return structured result dict + DataFrame
  - get_slim_schema()  : cached schema string for agent prompts
  - get_full_schema()  : full schema (debugging / admin)
  - test_db()          : connectivity check

All heavy DB logic lives in db.py.
This file is the single import point for pipeline.py and main.py.
"""

import pandas as pd
from typing import Optional
from db import (
    get_connection,
    create_db_engine,
    get_slim_schema   as _db_slim_schema,
    get_database_schema as _db_full_schema,
    validate_connection,
)


# ─── Schema Cache ─────────────────────────────────────────────────────────────

_slim_schema_cache: Optional[str] = None
_full_schema_cache: Optional[str] = None


def get_slim_schema(force_refresh: bool = False) -> str:
    """
    Return a compact schema string (table names + columns + PK/FK tags).
    Cached after first call — call with force_refresh=True to bust cache.
    Used by all agents in their prompts.
    """
    global _slim_schema_cache
    if _slim_schema_cache and not force_refresh:
        return _slim_schema_cache
    print("[TOOLS] Loading slim schema from database...")
    _slim_schema_cache = _db_slim_schema()
    print(f"[TOOLS] Slim schema loaded: {len(_slim_schema_cache)} chars")
    return _slim_schema_cache


def get_full_schema(force_refresh: bool = False) -> str:
    """
    Return the full schema with nullability info.
    Cached. Used for debugging or admin endpoints.
    """
    global _full_schema_cache
    if _full_schema_cache and not force_refresh:
        return _full_schema_cache
    print("[TOOLS] Loading full schema from database...")
    _full_schema_cache = _db_full_schema()
    print(f"[TOOLS] Full schema loaded: {len(_full_schema_cache)} chars")
    return _full_schema_cache


def bust_schema_cache() -> None:
    """Force both schema caches to reload on next call."""
    global _slim_schema_cache, _full_schema_cache
    _slim_schema_cache = None
    _full_schema_cache = None
    print("[TOOLS] Schema cache cleared.")


# ─── SQL Execution ────────────────────────────────────────────────────────────

def execute_query(sql: str) -> dict:
    """
    Execute a SELECT query against SQL Server using the SQLAlchemy engine.

    Returns:
    {
        "data":      list[dict],   # rows as list of dicts (JSON-serialisable)
        "columns":   list[str],    # column names in order
        "row_count": int,
        "df":        pd.DataFrame | None,
        "error":     str | None,   # None on success
    }
    """
    sql = sql.strip().rstrip(";")   # safety: no trailing semicolons

    # Block anything that isn't a SELECT/WITH (CTE)
    first_word = sql.split()[0].upper() if sql.split() else ""
    if first_word not in ("SELECT", "WITH"):
        return {
            "data": [], "columns": [], "row_count": 0, "df": None,
            "error": f"Only SELECT queries are allowed. Got: {first_word}",
        }

    try:
        engine = create_db_engine()
        df     = pd.read_sql(sql, engine)
        engine.dispose()

        # Convert any non-JSON-serialisable types (Decimal, date, etc.)
        data = _safe_records(df)

        return {
            "data":      data,
            "columns":   list(df.columns),
            "row_count": len(df),
            "df":        df,
            "error":     None,
        }

    except Exception as e:
        return {
            "data": [], "columns": [], "row_count": 0, "df": None,
            "error": str(e),
        }


def _safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to JSON-safe dicts."""
    records = []
    for row in df.to_dict(orient="records"):
        safe_row = {}
        for k, v in row.items():
            if pd.isna(v) if not isinstance(v, (list, dict)) else False:
                safe_row[k] = None
            elif hasattr(v, "item"):          # numpy scalar → Python native
                safe_row[k] = v.item()
            elif hasattr(v, "isoformat"):     # date/datetime → ISO string
                safe_row[k] = v.isoformat()
            else:
                safe_row[k] = v
        records.append(safe_row)
    return records


# ─── Connectivity ─────────────────────────────────────────────────────────────

def test_db() -> tuple[bool, str]:
    """
    Quick connectivity check.
    Returns (True, success_message) or (False, error_message).
    """
    return validate_connection()


# ─── Data Profiling (bonus utility for insight_agent prompts) ─────────────────

def profile_dataframe(df: pd.DataFrame, max_sample: int = 100) -> dict:
    """
    Build a lightweight profile of a DataFrame to pass to agents.
    Keeps token count small by summarising rather than dumping all rows.
    """
    if df is None or df.empty:
        return {"columns": [], "row_count": 0, "sample": [], "numeric_summary": {}}

    numeric_summary = {}
    for col in df.select_dtypes(include="number").columns:
        s = df[col].dropna()
        if len(s):
            numeric_summary[col] = {
                "min":    round(float(s.min()), 4),
                "max":    round(float(s.max()), 4),
                "mean":   round(float(s.mean()), 4),
                "median": round(float(s.median()), 4),
                "sum":    round(float(s.sum()), 4),
            }

    return {
        "columns":         list(df.columns),
        "dtypes":          {c: str(df[c].dtype) for c in df.columns},
        "row_count":       len(df),
        "sample":          _safe_records(df.head(max_sample)),
        "numeric_summary": numeric_summary,
    }