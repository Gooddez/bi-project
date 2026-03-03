"""
pipeline.py — Full BI pipeline orchestration.

Flow:
  1. sql_agent         → raw SQL from question
  2. validator_agent   → pre-execution SQL validation/cleanup
  3. execute_query()   → DataFrame
     └─ on error → validator_agent (with error msg) → retry once
  4. chart_agent       → chart config JSON
  5. build_chart()     → Altair Vega-Lite JSON spec
  6. insight_agent     → anomaly/insight JSON array
  7. explainer_agent   → plain language summary
"""

import json
import asyncio
import re
import pandas as pd
from google.genai import types

from agents import (
    sql_runner, validator_runner,
    chart_runner, insight_runner, explainer_runner,
)
from tools import get_slim_schema, execute_query, profile_dataframe
from chart_builder import build_chart


# ─── Generic agent runner ─────────────────────────────────────────────────────

async def run_agent(runner, prompt: str, output_key: str) -> str:
    """Run any ADK agent with a single-turn prompt, return state value."""
    session = await runner.session_service.create_session(
        user_id="user", app_name="bi_v2"
    )
    content = types.Content(role="user", parts=[types.Part(text=prompt)])

    per_author = {}
    async for event in runner.run_async(
        user_id="user", session_id=session.id, new_message=content
    ):
        author = getattr(event, "author", "?")
        delta  = (event.actions.state_delta or {}) if event.actions else {}
        if delta:
            per_author.setdefault(author, {}).update(delta)

    merged = {}
    for s in per_author.values():
        merged.update(s)
    return merged.get(output_key, "")


def clean_sql(text: str) -> str:
    """Strip markdown fences and trailing semicolons."""
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"```", "", text)
    return text.strip().rstrip(";").strip()


def safe_parse_json(text: str, fallback=None):
    """Parse JSON from agent output, stripping any surrounding text."""
    text = text.strip()
    # Strip markdown fences
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"```", "", text)
    # Find the first complete JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start != -1:
            end = text.rfind(end_char)
            if end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
    return fallback


# ─── Main pipeline ────────────────────────────────────────────────────────────

async def run_pipeline(question: str) -> dict:
    """
    Run the full 5-agent BI pipeline for a given question.
    Returns a dict with keys: sql, chart_spec, insights, explanation, data, error
    """
    print(f"\n{'='*60}\nQUESTION: {question}\n{'='*60}")
    schema = get_slim_schema()

    # ── Step 1: Generate SQL ──────────────────────────────────────────────────
    print("[1/5] sql_agent → generating SQL...")
    sql_raw = await run_agent(
        sql_runner,
        f"DATABASE SCHEMA:\n{schema}\n\nUSER QUESTION:\n{question}",
        "sql_query"
    )
    sql = clean_sql(sql_raw)
    print(f"      SQL: {repr(sql[:120])}")

    # ── Step 2: Validate SQL ──────────────────────────────────────────────────
    print("[2/5] validator_agent → validating SQL...")
    validated_raw = await run_agent(
        validator_runner,
        f"SQL TO VALIDATE:\n{sql}\n\nDATABASE SCHEMA:\n{schema}\n\nERROR MESSAGE:\n(none — pre-execution check)",
        "validated_sql"
    )
    sql = clean_sql(validated_raw) or sql
    print(f"      Validated SQL: {repr(sql[:120])}")

    # ── Step 3: Execute SQL ───────────────────────────────────────────────────
    print("[3/5] execute_query → running SQL...")
    result = execute_query(sql)

    if result["error"]:
        print(f"      Error: {result['error']} — attempting recovery...")
        recovered_raw = await run_agent(
            validator_runner,
            f"SQL TO FIX:\n{sql}\n\nERROR MESSAGE:\n{result['error']}\n\nDATABASE SCHEMA:\n{schema}",
            "validated_sql"
        )
        recovered_sql = clean_sql(recovered_raw)
        if recovered_sql:
            result = execute_query(recovered_sql)
            sql = recovered_sql
            print(f"      Recovery SQL: {repr(recovered_sql[:120])}")

    df        = result.get("df")
    exec_error = result.get("error")
    data      = result.get("data", [])
    columns   = result.get("columns", [])
    row_count = result.get("row_count", 0)

    print(f"      Rows: {row_count}, Error: {exec_error}")

    # ── Steps 4-7 only if we have data ───────────────────────────────────────
    chart_spec  = None
    insights    = []
    explanation = ""

    if df is not None and row_count > 0:
        # Rich profile for agent prompts (keeps token count low)
        profile      = profile_dataframe(df, max_sample=100)
        data_summary = (
            f"Columns & types: {json.dumps(profile['dtypes'])}\n"
            f"Row count: {profile['row_count']}\n"
            f"Numeric summary: {json.dumps(profile['numeric_summary'])}\n"
            f"Sample (first 5 rows): {json.dumps(profile['sample'][:5], default=str)}"
        )

        # ── Step 4+5: Chart selection + build ─────────────────────────────
        print("[4/5] chart_agent → selecting chart type...")
        chart_config_raw = await run_agent(
            chart_runner,
            f"ORIGINAL QUESTION:\n{question}\n\nDATA SUMMARY:\n{data_summary}",
            "chart_config"
        )
        chart_config = safe_parse_json(chart_config_raw, fallback={})
        print(f"      Chart config: {chart_config}")

        if chart_config and row_count > 1:
            chart_spec = build_chart(chart_config, df)
            print(f"      Chart built: {'yes' if chart_spec else 'no'}")

        # ── Steps 5+6: Insight + Explainer (run concurrently) ─────────────
        print("[5/5] insight_agent + explainer_agent → analysing...")
        insight_prompt = (
            f"ORIGINAL QUESTION:\n{question}\n\n"
            f"SQL QUERY:\n{sql}\n\n"
            f"DATA SUMMARY:\n{data_summary}\n\n"
            f"FULL DATA:\n{json.dumps(data[:100], default=str)}"
        )
        explain_prompt = (
            f"ORIGINAL QUESTION:\n{question}\n\n"
            f"SQL QUERY:\n{sql}\n\n"
            f"DATA SUMMARY:\n{data_summary}"
        )

        insight_raw, explanation = await asyncio.gather(
            run_agent(insight_runner, insight_prompt, "insights_json"),
            run_agent(explainer_runner, explain_prompt, "explanation"),
        )

        insights_parsed = safe_parse_json(insight_raw, fallback=[])
        insights = insights_parsed if isinstance(insights_parsed, list) else []
        print(f"      Insights: {len(insights)}, Explanation: {len(explanation)} chars")

    return {
        "sql":         sql,
        "chart_spec":  chart_spec,   # Vega-Lite JSON string or None
        "insights":    insights,      # list of insight dicts
        "explanation": explanation,   # plain text
        "data":        data,
        "columns":     columns,
        "row_count":   row_count,
        "error":       exec_error,
    }