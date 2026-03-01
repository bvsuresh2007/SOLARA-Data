"""
Ask Me Anything — AI-powered natural language query over sales/inventory data.

POST /api/ama/ask
"""

import json
import logging
import re
from datetime import date
from typing import Optional

from anthropic import Anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models.metadata import Portal

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AMARequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    portal_id: Optional[int] = None


class AMAResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# SQL Safety
# ---------------------------------------------------------------------------

_DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"EXEC|EXECUTE|COPY|SET\s+ROLE|SET\s+SESSION|COMMIT|ROLLBACK|"
    r"SAVEPOINT|LOCK|VACUUM|REINDEX|CLUSTER|NOTIFY|LISTEN|LOAD|"
    r"DO\s+\$|pg_sleep|pg_terminate|pg_cancel)\b",
    re.IGNORECASE,
)

_MULTIPLE_STATEMENTS = re.compile(r";\s*\S")  # semicolon followed by non-whitespace


def validate_sql_readonly(sql: str) -> tuple[bool, str]:
    """Return (is_safe, reason). Only SELECT/WITH queries are allowed."""
    stripped = sql.strip().rstrip(";").strip()

    # Must start with SELECT or WITH
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, "Query must be a SELECT statement."

    # No multiple statements
    if _MULTIPLE_STATEMENTS.search(stripped):
        return False, "Multiple SQL statements are not allowed."

    # No dangerous keywords
    match = _DANGEROUS_KEYWORDS.search(stripped)
    if match:
        return False, f"Disallowed SQL keyword: {match.group(0)}"

    # No SQL comments (could hide malicious content)
    if "--" in stripped or "/*" in stripped:
        return False, "SQL comments are not allowed."

    return True, ""


# ---------------------------------------------------------------------------
# System Prompt (DB schema for Claude)
# ---------------------------------------------------------------------------

DB_SCHEMA_PROMPT = """You are a SQL analyst for Solara, an e-commerce company that sells products across multiple online portals (Swiggy, Blinkit, Amazon, Zepto, Shopify, Myntra, Flipkart, Meesho, Nykaa Fashion, CRED, Vaaree, Offline).

You translate natural language questions into PostgreSQL SELECT queries, then explain the results in plain English.

## DATABASE SCHEMA

### portals
- id (SERIAL PK)
- name (VARCHAR 50, UNIQUE) — slug: 'swiggy', 'blinkit', 'amazon', 'zepto', 'shopify', 'myntra', 'flipkart', 'meesho', 'nykaa_fashion', 'cred', 'vaaree', 'offline'
- display_name (VARCHAR 100) — human-readable: 'Swiggy', 'Blinkit', 'Amazon', etc.
- is_active (BOOLEAN, default TRUE)

### cities
- id (SERIAL PK)
- name (VARCHAR 100)
- state (VARCHAR 100)
- region (VARCHAR 50) — 'North', 'South', 'East', 'West'
- is_active (BOOLEAN)

### warehouses
- id (SERIAL PK)
- name (VARCHAR 200)
- code (VARCHAR 100)
- portal_id (FK portals.id)
- city_id (FK cities.id)

### product_categories
- id (SERIAL PK)
- l1_name (VARCHAR 100) — top-level category
- l2_name (VARCHAR 100) — sub-category

### products
- id (SERIAL PK)
- sku_code (VARCHAR 100, UNIQUE) — internal Solara SKU like 'SOL-INS-WB-001'
- product_name (VARCHAR 500)
- category_id (FK product_categories.id)
- default_asp (NUMERIC 10,2) — default average selling price
- unit_type (VARCHAR 50)

### product_portal_mapping
- id (SERIAL PK)
- product_id (FK products.id)
- portal_id (FK portals.id)
- portal_sku (VARCHAR 500) — ASIN, Swiggy item code, etc.
- portal_product_name (VARCHAR 500)
- is_active (BOOLEAN)
- UNIQUE(portal_id, portal_sku)

### daily_sales (PRIMARY sales table — grain: portal + product + date)
- id (SERIAL PK)
- portal_id (FK portals.id)
- product_id (FK products.id)
- sale_date (DATE)
- units_sold (NUMERIC 12,2)
- asp (NUMERIC 10,2) — average selling price
- revenue (NUMERIC 14,2) — units_sold * asp
- data_source (VARCHAR 30) — 'excel', 'portal_csv', 'master_excel'
- UNIQUE(portal_id, product_id, sale_date)

### city_daily_sales (city-level breakdown — grain: portal + product + city + date)
- id (SERIAL PK)
- portal_id (FK portals.id)
- product_id (FK products.id)
- city_id (FK cities.id)
- sale_date (DATE)
- units_sold (NUMERIC 12,2)
- mrp (NUMERIC 10,2)
- selling_price (NUMERIC 10,2)
- revenue (NUMERIC 14,2) — GMV
- discount_amount (NUMERIC 12,2)
- net_revenue (NUMERIC 14,2)
- order_count (INTEGER)
- UNIQUE(portal_id, product_id, city_id, sale_date)

### inventory_snapshots (grain: portal + product + snapshot_date)
- id (SERIAL PK)
- portal_id (FK portals.id)
- product_id (FK products.id)
- snapshot_date (DATE)
- portal_stock (NUMERIC 12,2)
- backend_stock (NUMERIC 12,2) — Blinkit backend
- frontend_stock (NUMERIC 12,2) — Blinkit frontend
- solara_stock (NUMERIC 12,2) — Solara warehouse
- amazon_fc_stock (NUMERIC 12,2) — Amazon FC
- open_po (NUMERIC 12,2) — open purchase orders
- doc (NUMERIC 8,2) — days of coverage
- UNIQUE(portal_id, product_id, snapshot_date)

### monthly_targets (grain: portal + product + year + month)
- id (SERIAL PK)
- portal_id (FK portals.id)
- product_id (FK products.id)
- year (SMALLINT)
- month (SMALLINT)
- target_units (NUMERIC 12,2)
- target_revenue (NUMERIC 14,2)
- target_drr (NUMERIC 10,2) — target daily run rate
- achievement_pct (NUMERIC 8,4)
- UNIQUE(portal_id, product_id, year, month)

### monthly_ad_spend (grain: portal + year + month)
- id (SERIAL PK)
- portal_id (FK portals.id)
- year (SMALLINT)
- month (SMALLINT)
- total_revenue (NUMERIC 14,2)
- ad_spend (NUMERIC 14,2)
- tacos_pct (NUMERIC 8,4) — total advertising cost of sales %
- UNIQUE(portal_id, year, month)

### import_logs (audit trail)
- id (SERIAL PK)
- source_type (VARCHAR 30) — 'excel_import', 'portal_csv', 'portal_scraper'
- portal_id (FK portals.id)
- sheet_name (VARCHAR 200)
- file_name (VARCHAR 500)
- import_date (DATE)
- start_time (TIMESTAMP)
- end_time (TIMESTAMP)
- status (VARCHAR 20) — 'running', 'success', 'failed'
- records_imported (INTEGER)
- error_message (TEXT)

## IMPORTANT NOTES
- Currency is INR (Indian Rupees). Format large numbers in lakhs (L) or crores (Cr).
- The company is called "Solara". SKU codes start with "SOL-".
- Portal names in the `portals.name` column are lowercase slugs. Always join through portals table.
- The `daily_sales` table is the PRIMARY source for revenue/units. Use it unless the question specifically asks about city-level data.
- For "top selling" questions, use revenue unless the user says "by units".
- When filtering by portal, always join to the `portals` table and filter by `portals.name` (slug) or `portals.display_name` — never hardcode portal IDs.
- Exclude portals where is_active = false UNLESS the user specifically asks about inactive portals.
- There is an inactive portal 'easyecom' that is an aggregator — exclude it by default.
- There is also 'amazon_pi' (inactive) whose data should be treated as part of 'amazon'.

## RULES
1. Generate ONLY a single SELECT statement. No INSERT, UPDATE, DELETE, DROP, or any DDL/DML.
2. Always LIMIT results to at most 50 rows unless the user asks for a specific count.
3. Use proper JOINs — never use subqueries where a JOIN suffices.
4. Round monetary values to 2 decimal places. Round percentages to 1 decimal place.
5. If you cannot answer the question with the available schema, explain exactly what data is missing.
6. When the user's question is ambiguous, make reasonable assumptions and state them.

## OUTPUT FORMAT
Respond in this exact JSON format (no markdown, no code fences):
{"sql": "SELECT ...", "explanation": "Brief explanation of what the query does"}

If the question CANNOT be answered with the available data:
{"sql": null, "explanation": "I cannot answer this because [specific reason]. The database does not have [what's missing]."}
"""

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/ask", response_model=AMAResponse)
def ask_question(body: AMARequest, db: Session = Depends(get_db)):
    """Accept a natural language question, generate SQL, run it, and return
    a plain-English answer."""

    if not settings.llm_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI feature is not configured. Set ANTHROPIC_API_KEY in .env.",
        )

    # ----- 1. Build context about active dashboard filters ----- #
    context_parts: list[str] = []
    if body.start_date:
        context_parts.append(f"Date range starts from: {body.start_date}")
    if body.end_date:
        context_parts.append(f"Date range ends at: {body.end_date}")
    if body.portal_id:
        portal = db.query(Portal).filter(Portal.id == body.portal_id).first()
        if portal:
            context_parts.append(
                f"Currently selected portal: '{portal.name}' "
                f"(display_name='{portal.display_name}', id={portal.id})"
            )

    context_msg = ""
    if context_parts:
        context_msg = (
            "\n\nACTIVE DASHBOARD FILTERS (apply these as WHERE conditions):\n"
            + "\n".join(f"- {p}" for p in context_parts)
        )

    user_message = body.question + context_msg

    # ----- 2. Call Claude to generate SQL ----- #
    try:
        client = Anthropic(api_key=settings.llm_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=DB_SCHEMA_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        ai_text = response.content[0].text.strip()
    except Exception as exc:
        logger.exception("Claude API call failed")
        return AMAResponse(
            answer="Sorry, I couldn't process your question right now. Please try again later.",
            error=f"AI service error: {type(exc).__name__}",
        )

    # ----- 3. Parse Claude's JSON response ----- #
    try:
        parsed = json.loads(ai_text)
        sql: str | None = parsed.get("sql")
        explanation: str = parsed.get("explanation", "")
    except json.JSONDecodeError:
        # Claude didn't return valid JSON — treat the whole thing as explanation
        return AMAResponse(answer=ai_text)

    # If no SQL (question can't be answered with available data)
    if not sql:
        return AMAResponse(answer=explanation)

    # ----- 4. Validate SQL is read-only ----- #
    is_safe, reason = validate_sql_readonly(sql)
    if not is_safe:
        logger.warning("Claude generated unsafe SQL: %s — reason: %s", sql, reason)
        return AMAResponse(
            answer="I generated a query that wasn't safe to execute. Please rephrase your question.",
            error=reason,
        )

    # ----- 5. Execute the SQL ----- #
    try:
        result = db.execute(text(sql))
        columns = list(result.keys())
        rows = result.fetchall()
    except SQLAlchemyError as exc:
        logger.warning("SQL execution failed: %s — SQL: %s", exc, sql)
        return AMAResponse(
            answer="I couldn't execute the query against your database. "
            "This might mean the data you're asking about doesn't exist yet.",
            sql=sql,
            error=f"Query execution failed: {type(exc).__name__}",
        )

    # No rows
    if not rows:
        return AMAResponse(
            answer=f"{explanation}\n\nHowever, the query returned no results. "
            "This likely means there is no data matching your criteria in the database.",
            sql=sql,
        )

    # ----- 6. Format results and ask Claude to summarize ----- #
    result_lines = [" | ".join(columns)]
    result_lines.append("-" * len(result_lines[0]))
    for row in rows[:50]:
        result_lines.append(" | ".join(str(v) for v in row))
    result_text = "\n".join(result_lines)

    try:
        summary_response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=512,
            system=(
                "You are a data analyst assistant. Summarize the query results below in a clear, "
                "concise natural language answer. Use INR currency formatting for Indian Rupees "
                "(use lakhs/crores for large numbers, e.g. ₹4.58 Cr, ₹12.3 L). "
                "Be specific with numbers. Keep the response to 2-4 sentences maximum. "
                "Do not include SQL in your response."
            ),
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Original question: {body.question}\n\n"
                        f"Query explanation: {explanation}\n\n"
                        f"Results:\n{result_text}"
                    ),
                }
            ],
        )
        answer = summary_response.content[0].text.strip()
    except Exception:
        # If summarization fails, build a simple answer from explanation + first row
        answer = f"{explanation}\n\nResult: {dict(zip(columns, rows[0]))}"

    return AMAResponse(answer=answer, sql=sql)
