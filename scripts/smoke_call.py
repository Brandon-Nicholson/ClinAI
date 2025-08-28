# app/scripts/smoke_call.py
from datetime import date
from app.services.patient_service import intake_patient
from app.services.call_service import (
    start_call, log_turn, set_intent, create_task, end_call,
    get_transcripts, list_recent_calls
)

def main():
    # 1) Ensure a patient exists
    p = intake_patient("Deminio", "Renipono", "+15555559966", date(1969, 10, 15))
    print("Patient:", p.id, p.first_name, p.last_name, p.phone)

    # 2) Start a call
    c = start_call(patient_id=p.id, from_number=p.phone)
    print("Started call:", c.id)

    # 3) Log a couple turns
    log_turn(c.id, "user", "Hi, I need to book a cardiology appointment.")
    log_turn(c.id, "assistant", "Sure—what day works best for you?")

    # 4) Set intent
    set_intent(c.id, "Refill")
    
    # 5) Create a task for back office
    create_task(c.id, "schedule", {"specialty": "Cardiology", "preferred": "2025-09-01T10:00:00", "reason": "chest pain (mild)"})

    # 6) End the call with a short note (could be LLM-generated later)
    end_call(c.id, resolved=True, escalated=False, notes="Scheduling request captured; sent to clinic queue.")

    # 7) Print transcripts & recent calls for sanity
    turns = get_transcripts(c.id)
    print("Turns:", [(t.role, t.text) for t in turns])
    recent = list_recent_calls(3)
    print("Recent calls:", [(rc.id, rc.intent, rc.resolved) for rc in recent])

if __name__ == "__main__":
    main()
