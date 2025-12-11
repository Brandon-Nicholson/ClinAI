# app/services/patient_service.py
from datetime import date
from sqlalchemy import select, func
from app.db.session import get_session
from app.db.models import Patient

# add new patient or update missing patient info
def intake_patient(first_name: str, last_name: str, phone: str, dob: date | None = None) -> Patient:
    """
    Placeholder for patient intake (simulating a submission form).
    - Checks if patient already exists by phone
    - Creates new patient if not found
    - Updates missing fields if found
    """
    with get_session() as s:  
        # check if patient already exists by phone number
        patient = s.execute(select(Patient).where(Patient.phone == phone)).scalar_one_or_none()
        
        # add new patient info if not currently in the db
        if not patient:
            patient = Patient(first_name=first_name, last_name=last_name, phone=phone, dob=dob)
            s.add(patient)
            s.commit() # populate patient.id first
            patient.mrn = f"MRN{patient.id:03d}"
        else:
            # Update only missing values
            if not patient.first_name and first_name:
                patient.first_name = first_name
            if not patient.last_name and last_name:
                patient.last_name = last_name
            if not patient.dob and dob:
                patient.dob = dob
        
        s.commit()
        s.refresh(patient)
        return patient


# helper functions
def get_by_phone(phone: str): # can be used to look up a patient by phone
    with get_session() as s:
        return s.execute(select(Patient).where(Patient.phone == phone)).scalar_one_or_none()

def get_by_id(pid: int):
    with get_session() as s:
        return s.get(Patient, pid)

def ensure_mrn(pid: int):
    with get_session() as s:
        p = s.get(Patient, pid)
        if p and (p.mrn is None or p.mrn == ""):
            p.mrn = f"MRN{p.id:03d}"
            s.commit()
            s.refresh(p)
        return p