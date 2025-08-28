# app/services/call_service.py
from __future__ import annotations
from typing import Optional, Dict, List

from sqlalchemy import select, func
from app.db.session import get_session
from app.db.models import Call, Transcript, Task

# Core lifecycle
def start_call(patient_id: Optional[int] = None, from_number: Optional[str] = None) -> Call:
    """Create a Call row when the conversation starts."""
    with get_session() as s:
        c = Call(patient_id=patient_id, from_number=from_number)
        s.add(c); s.commit(); s.refresh(c)
        return c

def log_turn(call_id: int, role: str, text: str) -> Transcript:
    """Append one transcript turn ('user' or 'assistant')."""
    if role not in ("user", "assistant"):
        raise ValueError("role must be 'user' or 'assistant'")
    with get_session() as s:
        t = Transcript(call_id=call_id, role=role, text=text)
        s.add(t); s.commit(); s.refresh(t)
        return t

def set_intent(call_id: int, intent: Optional[str]) -> None:
    """Store the LLM/classifier result for this call."""
    with get_session() as s:
        c = s.get(Call, call_id)
        if not c:
            raise ValueError(f"Call {call_id} not found")
        c.intent = intent
        s.commit()

def end_call(call_id: int, *, resolved: bool, escalated: bool, notes: Optional[str] = None) -> None:
    """Close out a call when finished; set resolved/escalated + optional summary notes."""
    with get_session() as s:
        c = s.get(Call, call_id)
        if not c:
            raise ValueError(f"Call {call_id} not found")
        c.ended_at = func.now()
        c.resolved = resolved
        c.escalated = escalated
        if notes:
            c.notes = notes
        s.commit()

# Tasks
def create_task(call_id: int, task_type: str, payload: Dict) -> Task:
    """Create a work item (schedule/refill/prior_auth/etc)."""
    with get_session() as s:
        t = Task(call_id=call_id, task_type=task_type, payload=payload)
        s.add(t); s.commit(); s.refresh(t)
        return t

# Helpful getters for UI / debugging
def get_call(call_id: int) -> Optional[Call]:
    with get_session() as s:
        return s.get(Call, call_id)

def get_transcripts(call_id: int) -> List[Transcript]:
    with get_session() as s:
        return list(
            s.execute(
                select(Transcript).where(Transcript.call_id == call_id).order_by(Transcript.id.asc())
            ).scalars()
        )

def list_recent_calls(limit: int = 10) -> List[Call]:
    with get_session() as s:
        return list(
            s.execute(select(Call).order_by(Call.id.desc()).limit(limit)).scalars()
        )
