"""
magicpin AI Challenge - Candidate Bot Server
============================================

FastAPI implementation exposing the complete judging and testing API contract:
- GET  /v1/healthz     (Liveness & context counter probe)
- GET  /v1/metadata    (Bot identity, model, & approach summary)
- POST /v1/context     (Atomic context ingestion & version management)
- POST /v1/tick        (Simulated time tick & proactive message initiation)
- POST /v1/reply       (Multi-turn conversational response & intent execution)
- POST /v1/teardown    (Optional test teardown & context reset)

Also exposes:
- compose(category, merchant, trigger, customer=None) -> dict
"""

from __future__ import annotations

import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Local imports
from composer import compose as core_compose
from conversation_handlers import conversation_manager

app = FastAPI(
    title="magicpin Vera AI Challenge Bot",
    description="Intelligent Merchant & Customer Engagement Bot for local commerce",
    version="1.0.0"
)

START_TIME = time.time()

# In-memory store for 4-contexts: key = (scope, context_id) -> {"version": int, "payload": dict}
contexts: Dict[tuple[str, str], Dict[str, Any]] = {}

# Set of already suppressed keys (dedup)
suppressed_keys: set[str] = set()

DATASET_DIR = Path(__file__).parent / "dataset"
CACHE_FILE = Path("/tmp/vera_contexts_cache.json") if os.name != "nt" else Path(__file__).parent / ".contexts_cache.json"

def preload_local_dataset():
    if DATASET_DIR.exists():
        try:
            cat_dir = DATASET_DIR / "categories"
            if cat_dir.exists():
                for f in cat_dir.glob("*.json"):
                    data = json.load(open(f, encoding="utf-8"))
                    slug = data.get("slug", f.stem)
                    contexts[("category", slug)] = {"version": 1, "payload": data}

            merch_dir = DATASET_DIR / "merchants"
            if merch_dir.exists():
                for f in merch_dir.glob("*.json"):
                    data = json.load(open(f, encoding="utf-8"))
                    mid = data.get("merchant_id", f.stem)
                    contexts[("merchant", mid)] = {"version": 1, "payload": data}

            cust_dir = DATASET_DIR / "customers"
            if cust_dir.exists():
                for f in cust_dir.glob("*.json"):
                    data = json.load(open(f, encoding="utf-8"))
                    cid = data.get("customer_id", f.stem)
                    contexts[("customer", cid)] = {"version": 1, "payload": data}

            trg_dir = DATASET_DIR / "triggers"
            if trg_dir.exists():
                for f in trg_dir.glob("*.json"):
                    data = json.load(open(f, encoding="utf-8"))
                    tid = data.get("id", f.stem)
                    contexts[("trigger", tid)] = {"version": 1, "payload": data}
        except Exception as e:
            print(f"Warning: Preload encountered: {e}")

    # Overlay cached updates if file exists
    if CACHE_FILE.exists():
        try:
            cache_data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            for item in cache_data:
                key = (item["scope"], item["context_id"])
                contexts[key] = {"version": item["version"], "payload": item["payload"]}
        except Exception:
            pass

def persist_context_cache():
    try:
        cache_data = []
        for (scope, cid), val in contexts.items():
            if val.get("version", 1) > 1:
                cache_data.append({"scope": scope, "context_id": cid, "version": val["version"], "payload": val["payload"]})
        CACHE_FILE.write_text(json.dumps(cache_data), encoding="utf-8")
    except Exception:
        pass

# Preload on module import
preload_local_dataset()


# =============================================================================
# API SCHEMAS
# =============================================================================

class ContextPushBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class TickBody(BaseModel):
    now: str
    available_triggers: List[str] = Field(default_factory=list)


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "magicpin Vera AI Challenge Bot",
        "endpoints": {
            "healthz": "/v1/healthz",
            "metadata": "/v1/metadata",
            "context": "POST /v1/context",
            "tick": "POST /v1/tick",
            "reply": "POST /v1/reply"
        }
    }


@app.get("/v1/healthz")
@app.get("/healthz")
async def healthz():
    """Liveness probe reporting uptime and loaded contexts across all 4 scopes."""
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": counts
    }


@app.get("/v1/metadata")
@app.get("/metadata")
async def metadata():
    """Candidate identity, model selection, and architecture overview."""
    team_members_raw = os.environ.get("TEAM_MEMBERS")
    if team_members_raw:
        try:
            team_members = json.loads(team_members_raw)
        except Exception:
            team_members = [team_members_raw]
    else:
        team_members = ["Candidate"]

    return {
        "team_name": os.environ.get("TEAM_NAME", "Team Vera"),
        "team_members": team_members,
        "model": os.environ.get("MODEL_NAME", "gpt-4o-mini"),
        "approach": "4-context structured composition engine with dynamic intent routing and zero-latency synthesis",
        "contact_email": os.environ.get("CONTACT_EMAIL", "team@example.com"),
        "version": "1.0.0",
        "submitted_at": "2026-04-26T08:00:00Z"
    }


@app.post("/v1/context")
@app.post("/context")
async def push_context(body: ContextPushBody):
    """
    Ingest a context push (category, merchant, customer, or trigger).
    Atomic update: replaces previous version if new version is strictly greater.
    Returns 409 if version is stale.
    """
    valid_scopes = {"category", "merchant", "customer", "trigger"}
    if body.scope not in valid_scopes:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"accepted": False, "reason": "invalid_scope", "details": f"Scope must be one of {valid_scopes}"}
        )

    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    
    # Version check for idempotency & stale updates
    if cur and cur.get("version", 0) >= body.version:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "accepted": False,
                "reason": "stale_version",
                "current_version": cur.get("version", 0)
            }
        )

    # Store atomically
    contexts[key] = {
        "version": body.version,
        "payload": body.payload
    }
    persist_context_cache()
    
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": now_iso
    }


@app.post("/v1/tick")
@app.post("/tick")
async def tick(body: TickBody):
    """
    Simulated clock tick. Inspects available triggers and generates proactive outreach actions.
    """
    actions = []
    
    for trg_id in body.available_triggers:
        trg_ctx = contexts.get(("trigger", trg_id), {}).get("payload")
        if not trg_ctx:
            continue

        merchant_id = trg_ctx.get("merchant_id")
        if not merchant_id:
            continue

        merchant = contexts.get(("merchant", merchant_id), {}).get("payload")
        if not merchant:
            continue

        cat_slug = merchant.get("category_slug") or trg_ctx.get("payload", {}).get("category")
        category = contexts.get(("category", cat_slug), {}).get("payload")
        if not category:
            # Fallback to minimal category stub
            category = {"slug": cat_slug or "general", "offer_catalog": [], "voice": {}, "peer_stats": {}}

        customer_id = trg_ctx.get("customer_id")
        customer = contexts.get(("customer", customer_id), {}).get("payload") if customer_id else None

        supp_key = trg_ctx.get("suppression_key", f"{trg_id}:{merchant_id}")
        if supp_key in suppressed_keys:
            continue
        suppressed_keys.add(supp_key)

        # Call composition engine
        composed = core_compose(category, merchant, trg_ctx, customer)

        action = {
            "conversation_id": f"conv_{merchant_id}_{trg_id}",
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": composed.get("template_name", "vera_standard_v1"),
            "template_params": composed.get("template_params", []),
            "body": composed.get("body", ""),
            "cta": composed.get("cta", "binary_yes_no"),
            "suppression_key": composed.get("suppression_key", supp_key),
            "rationale": composed.get("rationale", "")
        }
        actions.append(action)

        # Respect action count cap per tick
        if len(actions) >= 20:
            break

    return {"actions": actions}


@app.post("/v1/reply")
@app.post("/reply")
async def reply(body: ReplyBody):
    """
    Receives incoming reply from merchant (or customer) and returns next conversational action.
    """
    result = conversation_manager.process_reply(
        conversation_id=body.conversation_id,
        message=body.message,
        turn_number=body.turn_number,
        merchant_id=body.merchant_id,
        customer_id=body.customer_id,
        from_role=body.from_role
    )
    return result


@app.post("/v1/teardown")
@app.post("/teardown")
async def teardown():
    """Wipes in-memory contexts and conversation history cleanly at end of testing."""
    contexts.clear()
    suppressed_keys.clear()
    preload_local_dataset()
    return {"status": "ok", "message": "Contexts reset to initial dataset state"}


# =============================================================================
# COMPATIBILITY EXPORT
# =============================================================================

def compose(category: dict, merchant: dict, trigger: dict, customer: dict | None = None) -> dict:
    """Standard composition contract export required by challenge brief §7.1."""
    return core_compose(category, merchant, trigger, customer)
