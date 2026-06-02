#!/usr/bin/env python3
"""Extract a small sample of CRM data from a live Narrio Postgres database
and emit `db/seed.sql` (Postgres INSERT statements) + `db/fixtures.json`.

This script is for the *instructors* who set up the interview repo. Students
never run it — they only see the generated `seed.sql` + `fixtures.json`.

Usage:
    DATABASE_URL=postgres://user:pw@host:5432/narrio \
        python tools/extract_from_narrio.py \
        --user-email alice3@narrio.app \
        --limit 10 \
        --out-sql db/seed.sql \
        --out-json db/fixtures.json

The script picks the top `--limit` deals by activity count for the company
associated with `--user-email`, then pulls everything reachable: pipeline +
stages, buyer, contacts (via deal_contacts), and every activity linked to
the deal (and the same activities' links to buyers/contacts).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras

# Django ContentType IDs in the source DB (verified against narrio dev).
CT_DEAL = 19
CT_BUYER = 11
CT_CONTACT = 49
CT_TO_NAME = {CT_DEAL: "deal", CT_BUYER: "buyer", CT_CONTACT: "contact"}


@dataclass
class Bundle:
    company: dict | None = None
    pipelines: list[dict] = field(default_factory=list)
    pipeline_stages: list[dict] = field(default_factory=list)
    deals: list[dict] = field(default_factory=list)
    buyers: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    deal_contacts: list[dict] = field(default_factory=list)
    activities: list[dict] = field(default_factory=list)
    activity_links: list[dict] = field(default_factory=list)


# -----------------------------------------------------------------------------
# JSON / SQL serialisation helpers
# -----------------------------------------------------------------------------

def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.astimezone(timezone.utc).isoformat()
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _sql_literal(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, datetime):
        return "'" + v.astimezone(timezone.utc).isoformat() + "'"
    s = str(v).replace("'", "''")
    return "'" + s + "'"


def _insert(table: str, rows: list[dict], columns: list[str]) -> list[str]:
    if not rows:
        return [f"-- (no rows for {table})"]
    out = [f"-- {table}: {len(rows)} rows", f"INSERT INTO {table} ({', '.join(columns)}) VALUES"]
    values = []
    for r in rows:
        vals = ", ".join(_sql_literal(r.get(c)) for c in columns)
        values.append(f"  ({vals})")
    out.append(",\n".join(values) + ";")
    out.append("")
    return out


# -----------------------------------------------------------------------------
# Extraction
# -----------------------------------------------------------------------------

def extract(conn, user_email: str, limit: int) -> Bundle:
    bundle = Bundle()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # 1. Company for the user
    cur.execute(
        """
        SELECT c.id, c.name, c.created_at
        FROM companies c
        JOIN company_memberships cm ON cm.company_id = c.id
        JOIN users u ON u.id = cm.user_id
        WHERE u.email = %s
        ORDER BY cm.created_at ASC
        LIMIT 1
        """,
        (user_email,),
    )
    row = cur.fetchone()
    if not row:
        raise SystemExit(f"no company found for user_email={user_email}")
    bundle.company = dict(row)
    company_id = bundle.company["id"]
    print(f"company: {bundle.company['name']} ({company_id})", file=sys.stderr)

    # 2. Top N deals by activity count
    cur.execute(
        """
        SELECT d.*, ps.label AS _stage_label
        FROM deals d
        LEFT JOIN activity_links al
               ON al.entity_id = d.id AND al.entity_type_id = %s
        LEFT JOIN pipeline_stages ps ON ps.id = d.pipeline_stage_id
        WHERE d.company_id = %s AND d.deleted_at IS NULL
        GROUP BY d.id, ps.label
        ORDER BY COUNT(al.id) DESC
        LIMIT %s
        """,
        (CT_DEAL, company_id, limit),
    )
    raw_deals = [dict(r) for r in cur.fetchall()]
    deal_ids = [str(d["id"]) for d in raw_deals]
    buyer_ids = sorted({str(d["buyer_id"]) for d in raw_deals if d["buyer_id"]})
    pipeline_ids = sorted({str(d["pipeline_id"]) for d in raw_deals if d["pipeline_id"]})
    print(f"deals: {len(raw_deals)}, buyers: {len(buyer_ids)}, pipelines: {len(pipeline_ids)}", file=sys.stderr)

    bundle.deals = [
        {
            "id": d["id"],
            "company_id": company_id,
            "pipeline_id": d["pipeline_id"],
            "pipeline_stage_id": d["pipeline_stage_id"],
            "buyer_id": d["buyer_id"],
            "deal_name": d["deal_name"],
            "stage_label": d["_stage_label"],
            "deal_amount": d["deal_amount"],
            "currency": d["currency"],
            "deal_owner": d["deal_owner"],
            "close_date": d["close_date"],
            "is_closed": bool(d["is_closed"]),
            "is_closed_won": bool(d["is_closed_won"]),
            "source_created_at": d["source_created_at"],
            "last_activity_at": d["last_activity_at"],
            "created_at": d["created_at"],
            "updated_at": d["updated_at"],
        }
        for d in raw_deals
    ]

    # 3. Pipelines + stages for these deals
    if pipeline_ids:
        cur.execute(
            "SELECT id, company_id, pipeline_label AS label, object_type, display_order, is_active, created_at "
            "FROM pipelines WHERE id = ANY(%s::uuid[])",
            (pipeline_ids,),
        )
        bundle.pipelines = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT id, company_id, pipeline_id, label, display_order, created_at "
            "FROM pipeline_stages WHERE pipeline_id = ANY(%s::uuid[])",
            (pipeline_ids,),
        )
        bundle.pipeline_stages = [dict(r) for r in cur.fetchall()]

    # 4. Buyers
    if buyer_ids:
        cur.execute(
            "SELECT id, company_id, name, description, website_url, linkedin_url, "
            "       identity_analysis, created_at, updated_at "
            "FROM buyers WHERE id = ANY(%s::uuid[])",
            (buyer_ids,),
        )
        raw_buyers = [dict(r) for r in cur.fetchall()]
        for b in raw_buyers:
            ia = b.get("identity_analysis") or {}
            industry = None
            if isinstance(ia, dict):
                industry = ia.get("industry") or (ia.get("company_profile") or {}).get("industry")
            bundle.buyers.append({
                "id": b["id"], "company_id": b["company_id"], "name": b["name"],
                "description": b["description"], "website_url": b["website_url"],
                "linkedin_url": b["linkedin_url"], "industry": industry,
                "created_at": b["created_at"], "updated_at": b["updated_at"],
            })

    # 5. deal_contacts + contacts
    if deal_ids:
        cur.execute(
            "SELECT id, deal_id, contact_id, role, confidence, created_at "
            "FROM deal_contacts WHERE deal_id = ANY(%s::uuid[])",
            (deal_ids,),
        )
        bundle.deal_contacts = [dict(r) for r in cur.fetchall()]

    contact_ids = sorted({str(dc["contact_id"]) for dc in bundle.deal_contacts})
    if contact_ids:
        cur.execute(
            "SELECT id, company_id, buyer_id, name, first_name, last_name, email, phone, "
            "       position, linkedin_url, created_at, updated_at "
            "FROM contacts WHERE id = ANY(%s::uuid[]) AND deleted_at IS NULL "
            "                AND company_id = %s",
            (contact_ids, company_id),
        )
        bundle.contacts = [dict(r) for r in cur.fetchall()]
        # Drop deal_contacts pointing to contacts we didn't keep
        kept_contact_ids = {str(c["id"]) for c in bundle.contacts}
        bundle.deal_contacts = [
            dc for dc in bundle.deal_contacts
            if str(dc["contact_id"]) in kept_contact_ids
        ]
        contact_ids = sorted(kept_contact_ids)

    # 6. Activities + links (via activity_links scoped to our deals/buyers/contacts)
    raw_links: list[dict] = []
    for ct_id, ids in ((CT_DEAL, deal_ids), (CT_BUYER, buyer_ids), (CT_CONTACT, contact_ids)):
        if not ids:
            continue
        cur.execute(
            """
            SELECT id, activity_id, entity_type_id, entity_id, confidence, created_at
            FROM activity_links
            WHERE entity_type_id = %s AND entity_id = ANY(%s::uuid[])
            """,
            (ct_id, ids),
        )
        raw_links.extend(dict(r) for r in cur.fetchall())
    if raw_links:
        activity_ids = sorted({str(l["activity_id"]) for l in raw_links})

        if activity_ids:
            cur.execute(
                "SELECT id, company_id, activity_type, subject, full_text, direction, source, "
                "       timestamp, created_at "
                "FROM activities WHERE id = ANY(%s::uuid[])",
                (activity_ids,),
            )
            bundle.activities = [dict(r) for r in cur.fetchall()]

        bundle.activity_links = [
            {
                "id": l["id"], "activity_id": l["activity_id"],
                "entity_type": CT_TO_NAME[l["entity_type_id"]],
                "entity_id": l["entity_id"], "confidence": l["confidence"],
                "created_at": l["created_at"],
            }
            for l in raw_links if l["entity_type_id"] in CT_TO_NAME
        ]
        print(
            f"activities: {len(bundle.activities)}, activity_links: {len(bundle.activity_links)}",
            file=sys.stderr,
        )

    return bundle


# -----------------------------------------------------------------------------
# Emit SQL + JSON
# -----------------------------------------------------------------------------

SCHEMA_ORDER: list[tuple[str, list[str]]] = [
    ("companies",        ["id", "name", "created_at"]),
    ("pipelines",        ["id", "company_id", "label", "object_type", "display_order", "is_active", "created_at"]),
    ("pipeline_stages",  ["id", "company_id", "pipeline_id", "label", "display_order", "created_at"]),
    ("buyers",           ["id", "company_id", "name", "description", "website_url", "linkedin_url", "industry", "created_at", "updated_at"]),
    ("contacts",         ["id", "company_id", "buyer_id", "name", "first_name", "last_name", "email", "phone", "position", "linkedin_url", "created_at", "updated_at"]),
    ("deals",            ["id", "company_id", "pipeline_id", "pipeline_stage_id", "buyer_id", "deal_name", "stage_label", "deal_amount", "currency", "deal_owner", "close_date", "is_closed", "is_closed_won", "source_created_at", "last_activity_at", "created_at", "updated_at"]),
    ("deal_contacts",    ["id", "deal_id", "contact_id", "role", "confidence", "created_at"]),
    ("activities",       ["id", "company_id", "activity_type", "subject", "full_text", "direction", "source", "timestamp", "created_at"]),
    ("activity_links",   ["id", "activity_id", "entity_type", "entity_id", "confidence", "created_at"]),
]


def emit_sql(b: Bundle, path: str) -> None:
    lines: list[str] = [
        "-- =========================================================================",
        "-- crm-agent-app — generated seed data (extracted from a real CRM slice)",
        f"-- generated_at: {datetime.now(timezone.utc).isoformat()}",
        "-- =========================================================================",
        "BEGIN;",
        "",
    ]
    tables_by_name = {
        "companies":       [b.company] if b.company else [],
        "pipelines":       b.pipelines,
        "pipeline_stages": b.pipeline_stages,
        "buyers":          b.buyers,
        "contacts":        b.contacts,
        "deals":           b.deals,
        "deal_contacts":   b.deal_contacts,
        "activities":      b.activities,
        "activity_links":  b.activity_links,
    }
    for table, cols in SCHEMA_ORDER:
        lines.extend(_insert(table, tables_by_name[table], cols))
    lines.append("COMMIT;")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}", file=sys.stderr)


def emit_json(b: Bundle, path: str) -> None:
    payload = {
        "company":        b.company,
        "pipelines":      b.pipelines,
        "pipeline_stages": b.pipeline_stages,
        "buyers":         b.buyers,
        "contacts":       b.contacts,
        "deals":          b.deals,
        "deal_contacts":  b.deal_contacts,
        "activities":     b.activities,
        "activity_links": b.activity_links,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=_json_default)
    print(f"wrote {path}", file=sys.stderr)


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--user-email", required=True)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--out-sql", default="db/seed.sql")
    p.add_argument("--out-json", default="db/fixtures.json")
    args = p.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL env var is required")

    conn = psycopg2.connect(db_url, connect_timeout=15)
    try:
        bundle = extract(conn, args.user_email, args.limit)
    finally:
        conn.close()

    emit_sql(bundle, args.out_sql)
    emit_json(bundle, args.out_json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
