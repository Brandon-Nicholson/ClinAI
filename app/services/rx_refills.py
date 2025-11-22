# app/services/rx_refills.py

from rapidfuzz import process
from app.db.session import get_session
from app.db.models import RefillRequest
from datetime import date
import re

# list of most common drugs for demo purposes
MEDS = [
    "omeprazole",
    "lisinopril",
    "atorvastatin",
    "metformin",
    "amoxicillin",
]

REFILL_COOLDOWN_DAYS = 30 # minimum wait time for refill

def extract_med_candidate(transcript: str) -> str | None:
    text = transcript.lower().strip()

    # Common patterns around refill phrasing
    patterns = [
        r"refill (?:of |for |on |my )(?P<med>[\w\s]+)",
        r"refill my (?P<med>[\w\s]+)",
        r"my (?P<med>[\w\s]+) prescription",
        r"for my (?P<med>[\w\s]+) prescription",
        r"refill (?P<med>[\w\s]+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            # grab candidate phrase and strip trailing filler like "please"
            candidate = m.group("med")
            # cut off trailing polite words
            candidate = re.sub(r"\b(please|thanks|thank you)\b.*$", "", candidate).strip()
            return candidate or None

    return None

def match_medication(transcript: str, meds=MEDS, threshold=50):
    # Just match against the whole transcript for now
    best, score, _ = process.extractOne(transcript.lower(), meds)
    return best if score >= threshold else None

def can_refill(last_fill_date: date | None) -> bool:
    if last_fill_date is None:
        # No record -> allow refill
        return True
    days_since = (date.today() - last_fill_date).days
    return days_since >= REFILL_COOLDOWN_DAYS

def handle_refill_request(patient_id: int, call_id: int, drug_name: str) -> str:
    with get_session() as session:
        # last refill for this patient + drug
        last_request = (
            session.query(RefillRequest)
            .filter_by(patient_id=patient_id, drug_name=drug_name)
            .order_by(RefillRequest.last_fill_date.desc())
            .first()
        )

        last_fill_date = last_request.last_fill_date if last_request else None
        # if user tries to refill twice in a month -> don't refill
        if not can_refill(last_fill_date):
            return (
                f"It looks like your last refill for {drug_name} was on "
                f"{last_fill_date:%B %d, %Y}. "
                f"Our policy only allows refills every {REFILL_COOLDOWN_DAYS} days."
            )

        # create new refill record
        new_refill = RefillRequest(
            patient_id=patient_id,
            call_id=call_id,
            drug_name=drug_name,
            last_fill_date=date.today(),
        )
        session.add(new_refill)
        session.commit()

        return f"I've submitted a refill request for {drug_name}! Please let me know if you need help with anything else or simply say stop to end the call."