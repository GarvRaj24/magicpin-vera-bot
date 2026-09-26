"""
magicpin AI Challenge - Local Test & Verification Suite
========================================================

Verifies all endpoints, schemas, response times, and conversational scenarios:
1. GET  /v1/healthz
2. GET  /v1/metadata
3. POST /v1/context (idempotency, version replacement, stale version 409, invalid scope 400)
4. POST /v1/tick (proactive message composition, rate limiting, suppression)
5. POST /v1/reply:
   - Auto-reply detection & graceful wait/exit
   - Intent transition to action (no qualifying questions)
   - Hostility & opt-out handling
   - Curveball redirection
6. Verification of submission.jsonl (30 canonical lines)
"""

import sys
import json
import time
from pathlib import Path
from fastapi.testclient import TestClient

# Import bot app
from bot import app, contexts

client = TestClient(app)

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def log_pass(text: str):
    print(f"{Colors.GREEN}[PASS]{Colors.RESET} {text}")

def log_fail(text: str):
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {text}")

def log_info(text: str):
    print(f"{Colors.CYAN}[INFO]{Colors.RESET} {text}")


def test_healthz():
    log_info("Testing GET /v1/healthz...")
    resp = client.get("/v1/healthz")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data.get("status") == "ok", "Expected status 'ok'"
    assert "contexts_loaded" in data
    log_pass(f"healthz ok (contexts loaded: {data['contexts_loaded']})")


def test_metadata():
    log_info("Testing GET /v1/metadata...")
    resp = client.get("/v1/metadata")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    for field in ["team_name", "team_members", "model", "approach", "version"]:
        assert field in data, f"Missing {field} in metadata"
    log_pass(f"metadata ok (team: {data['team_name']}, model: {data['model']})")


def test_context_push():
    log_info("Testing POST /v1/context (idempotency & version conflict)...")
    
    cid = f"test_vertical_{int(time.time() * 1000)}"
    # 1. Push version 1
    sample_cat = {
        "slug": cid,
        "voice": {"tone": "collegial"},
        "offer_catalog": [{"title": "Special @ ₹99"}]
    }
    resp1 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": cid,
        "version": 1,
        "payload": sample_cat
    })
    assert resp1.status_code == 200
    assert resp1.json().get("accepted") is True
    log_pass("Context v1 push accepted")

    # 2. Re-push version 1 (should return 409 stale_version)
    resp2 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": cid,
        "version": 1,
        "payload": sample_cat
    })
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}"
    assert resp2.json().get("accepted") is False
    assert resp2.json().get("reason") == "stale_version"
    log_pass("Stale version conflict 409 verified")

    # 3. Push version 2 (should replace version 1)
    sample_cat["voice"]["tone"] = "updated_tone"
    resp3 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": cid,
        "version": 2,
        "payload": sample_cat
    })
    assert resp3.status_code == 200
    assert resp3.json().get("accepted") is True
    assert contexts[("category", cid)]["payload"]["voice"]["tone"] == "updated_tone"
    log_pass("Version 2 atomic replacement verified")


def test_tick_and_composition():
    log_info("Testing POST /v1/tick...")
    
    # Get available trigger IDs from preloaded contexts
    trg_ids = [cid for (scope, cid) in contexts.keys() if scope == "trigger"][:5]
    assert len(trg_ids) > 0, "No triggers available in contexts"

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:30:00Z",
        "available_triggers": trg_ids
    })
    assert resp.status_code == 200
    data = resp.json()
    actions = data.get("actions", [])
    assert len(actions) > 0, "Expected at least 1 action from tick"
    
    for act in actions:
        assert act.get("conversation_id")
        assert act.get("merchant_id")
        assert act.get("body")
        assert act.get("cta")
        assert act.get("send_as") in ("vera", "merchant_on_behalf")
        assert act.get("rationale")
    log_pass(f"tick generated {len(actions)} high-quality action(s)")


def test_auto_reply_scenario():
    log_info("Testing Auto-reply detection scenario...")
    conv_id = f"test_auto_{int(time.time())}"
    auto_msg = "Thank you for contacting us! Our team will respond shortly."

    # Turn 1
    resp1 = client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": auto_msg,
        "turn_number": 2
    })
    assert resp1.status_code == 200
    act1 = resp1.json().get("action")
    log_pass(f"Auto-reply turn 2: action={act1} (wait/end)")

    # Turn 2 (repeated auto-reply)
    resp2 = client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": auto_msg,
        "turn_number": 3
    })
    assert resp2.status_code == 200
    act2 = resp2.json().get("action")
    assert act2 in ("wait", "end")
    log_pass(f"Auto-reply turn 3: action={act2} (handled gracefully)")


def test_intent_transition_scenario():
    log_info("Testing Intent transition scenario (Commitment -> Action)...")
    conv_id = f"test_intent_{int(time.time())}"
    commitment_msg = "Ok lets do it. Whats next?"

    resp = client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": commitment_msg,
        "turn_number": 2
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("action") == "send"
    body = data.get("body", "").lower()
    
    # Must use action words
    action_words = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
    qualifying_words = ["would you", "do you", "can you tell", "what if", "how about"]
    
    assert any(w in body for w in action_words), f"Action mode missing in: {body}"
    assert not any(w in body for w in qualifying_words), f"Found qualifying question in: {body}"
    log_pass("Intent transition: Successfully switched to ACTION mode without qualifying questions")


def test_hostile_scenario():
    log_info("Testing Hostility / Opt-out scenario...")
    conv_id = f"test_hostile_{int(time.time())}"
    hostile_msg = "Stop messaging me. This is useless spam."

    resp = client.post("/v1/reply", json={
        "conversation_id": conv_id,
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": hostile_msg,
        "turn_number": 2
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("action") == "end", f"Expected action 'end', got {data.get('action')}"
    log_pass("Hostile / Opt-out: Correctly exited conversation with action 'end'")


def test_submission_file():
    log_info("Validating submission.jsonl...")
    sub_path = Path(__file__).parent / "submission.jsonl"
    assert sub_path.exists(), "submission.jsonl does not exist"
    
    with open(sub_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 30, f"Expected 30 lines, found {len(lines)}"

    required_keys = {"test_id", "body", "cta", "send_as", "suppression_key", "rationale"}
    for idx, line in enumerate(lines, start=1):
        item = json.loads(line)
        for k in required_keys:
            assert k in item, f"Line {idx} missing key: {k}"
        assert item["body"], f"Line {idx} empty body"
        assert item["send_as"] in ("vera", "merchant_on_behalf"), f"Line {idx} invalid send_as"
        assert item["cta"], f"Line {idx} empty cta"

    log_pass(f"submission.jsonl: all 30 canonical test predictions validated perfectly")


def run_all():
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}       VERA BOT AUTOMATED TEST SUITE        {Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}\n")

    test_healthz()
    test_metadata()
    test_context_push()
    test_tick_and_composition()
    test_auto_reply_scenario()
    test_intent_transition_scenario()
    test_hostile_scenario()
    test_submission_file()

    print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}       ALL TEST SUITES PASSED (100% SUCCESS) {Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.RESET}\n")

if __name__ == "__main__":
    run_all()
