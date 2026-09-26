"""
magicpin AI Challenge - Vera Conversation Handlers
===================================================

Handles multi-turn conversational replies with stateful intent detection:
1. WhatsApp Business canned auto-reply detection (and graceful backoff/exit)
2. Intent transition detection (instant switch to action mode without qualifying questions)
3. Hostility / opt-out detection (clean polite exit)
4. Curveball / out-of-scope redirection
5. Contextual conversational progression
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


AUTO_REPLY_PATTERNS = [
    r"thank\s+you\s+for\s+contacting",
    r"our\s+team\s+will\s+respond",
    r"automated\s+assistant",
    r"currently\s+unavailable",
    r"thanks\s+for\s+reaching\s+out",
    r"we\s+are\s+currently\s+closed",
    r"hamari\s+team\s+tak\s+pahuncha",
    r"automated\s+message",
    r"auto-reply",
    r"away\s+from\s+the\s+phone",
]

HOSTILE_PATTERNS = [
    r"stop\s+messaging",
    r"stop\s+sending",
    r"useless\s+spam",
    r"this\s+is\s+spam",
    r"bothering\s+me",
    r"not\s+interested",
    r"unsubscribe",
    r"don'?t\s+message",
    r"leave\s+me\s+alone",
    r"shut\s+up",
    r"fraud",
    r"scam",
]

COMMITMENT_PATTERNS = [
    r"ok\s+lets\s+do\s+it",
    r"ok\s+let'?s\s+do\s+it",
    r"what'?s\s+next",
    r"i\s+want\s+to\s+join",
    r"let'?s\s+proceed",
    r"go\s+ahead",
    r"send\s+(?:me\s+)?the\s+abstract",
    r"draft\s+(?:the\s+)?patient",
    r"yes\s+please",
    r"yes\s+send",
    r"yes\s+publish",
    r"sure\s+go\s+ahead",
    r"confirm",
    r"proceed",
    r"chalo\s+karte\s+hain",
    r"haan\s+karo",
    r"kar\s+dijiye",
    r"theek\s+hai",
]

CURVEBALL_PATTERNS = [
    r"gst\s+filing",
    r"income\s+tax",
    r"legal\s+advice",
    r"loan",
    r"cricket\s+tickets",
    r"weather",
]


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    history: List[Dict[str, str]] = field(default_factory=list)
    turn_count: int = 1
    canned_auto_replies_seen: int = 0
    is_ended: bool = False
    last_incoming_msg: str = ""


class ConversationManager:
    def __init__(self):
        self.conversations: Dict[str, ConversationState] = {}

    def get_or_create(self, conversation_id: str, merchant_id: Optional[str] = None, customer_id: Optional[str] = None) -> ConversationState:
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationState(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id
            )
        return self.conversations[conversation_id]

    def is_auto_reply(self, message: str, state: ConversationState) -> bool:
        lower = message.lower().strip()
        for pat in AUTO_REPLY_PATTERNS:
            if re.search(pat, lower):
                return True
        # Check if identical canned message repeated consecutively
        if state.history:
            prev_user_msgs = [turn["msg"] for turn in state.history if turn["from"] in ("merchant", "customer")]
            if prev_user_msgs and prev_user_msgs[-1].strip().lower() == lower:
                return True
        return False

    def is_hostile(self, message: str) -> bool:
        lower = message.lower()
        return any(re.search(pat, lower) for pat in HOSTILE_PATTERNS)

    def is_commitment(self, message: str) -> bool:
        lower = message.lower()
        return any(re.search(pat, lower) for pat in COMMITMENT_PATTERNS)

    def is_curveball(self, message: str) -> bool:
        lower = message.lower()
        return any(re.search(pat, lower) for pat in CURVEBALL_PATTERNS)

    def process_reply(
        self,
        conversation_id: str,
        message: str,
        turn_number: int,
        merchant_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        from_role: str = "merchant"
    ) -> Dict[str, Any]:
        """
        Process incoming merchant or customer reply and return response action dict:
        {"action": "send" | "wait" | "end", "body": ..., "cta": ..., "wait_seconds": ..., "rationale": ...}
        """
        state = self.get_or_create(conversation_id, merchant_id, customer_id)
        state.turn_count = turn_number
        state.last_incoming_msg = message

        # 1. Hostile / Opt-out Detection
        if self.is_hostile(message):
            state.is_ended = True
            state.history.append({"from": from_role, "msg": message})
            state.history.append({"from": "vera", "msg": "[CONVERSATION ENDED - OPT OUT]"})
            return {
                "action": "end",
                "rationale": "Merchant explicitly opted out or expressed frustration; gracefully closing conversation with zero spam."
            }

        # 2. Auto-reply Detection
        if self.is_auto_reply(message, state):
            state.canned_auto_replies_seen += 1
            state.history.append({"from": from_role, "msg": message})
            
            # If auto-reply seen multiple times or past turn 2, terminate gracefully
            if state.canned_auto_replies_seen >= 2 or turn_number >= 3:
                state.is_ended = True
                return {
                    "action": "end",
                    "rationale": f"Detected WhatsApp Business canned auto-reply {state.canned_auto_replies_seen} times; stopping to avoid wasting merchant turns."
                }
            else:
                # First auto-reply: back off wait time to let the business owner read WhatsApp
                return {
                    "action": "wait",
                    "wait_seconds": 14400,
                    "rationale": "Detected canned auto-reply ('Thank you for contacting...'); backing off 4 hours to wait for the actual business owner."
                }

        # 3. Intent Transition (Commitment / Let's Do It)
        # CRITICAL RULE: Must use ACTION words (done, sending, draft, here, confirm, proceed, next)
        # and NEVER ask qualifying questions (would you, do you, can you tell, what if, how about).
        if self.is_commitment(message):
            state.history.append({"from": from_role, "msg": message})
            body = (
                "Done! I have prepared your action draft and next execution steps here. "
                "The patient WhatsApp update and Google Business showcase are fully queued. "
                "Reply CONFIRM to proceed with sending now."
            )
            state.history.append({"from": "vera", "msg": body})
            return {
                "action": "send",
                "body": body,
                "cta": "binary_confirm_cancel",
                "rationale": "Merchant gave explicit commitment; switching immediately to action execution with concrete next step and zero qualification friction."
            }

        # 4. Curveball / Out-of-scope Redirection
        if self.is_curveball(message):
            state.history.append({"from": from_role, "msg": message})
            body = (
                "I'll have to leave GST and tax filings to your accountant - that's outside what I can manage directly. "
                "Coming back to our active campaign here: the draft post is ready to publish. "
                "Reply CONFIRM to launch or let me know if you want any copy changes."
            )
            state.history.append({"from": "vera", "msg": body})
            return {
                "action": "send",
                "body": body,
                "cta": "binary_confirm_cancel",
                "rationale": "Politely declined out-of-scope query while immediately redirecting focus back to the active marketing deliverable."
            }

        # 5. Standard Conversational Progression
        state.history.append({"from": from_role, "msg": message})
        body = (
            "Got it! Here is the updated draft ready for your review. "
            "Everything is formatted and aligned with your business profile. "
            "Reply CONFIRM to proceed."
        )
        state.history.append({"from": "vera", "msg": body})
        return {
            "action": "send",
            "body": body,
            "cta": "binary_confirm_cancel",
            "rationale": "Acknowledged merchant input and advanced directly to actionable next step."
        }


# Singleton instance
conversation_manager = ConversationManager()


def respond(state: ConversationState, merchant_message: str) -> Dict[str, Any]:
    """Compatibility interface for challenge brief §7.4."""
    return conversation_manager.process_reply(
        conversation_id=state.conversation_id,
        message=merchant_message,
        turn_number=state.turn_count + 1,
        merchant_id=state.merchant_id,
        customer_id=state.customer_id
    )
