# app/scripts/smoke_patient.py
from app.services.patient_service import intake_patient
from datetime import date

p = intake_patient("Timothy", "Thompson", "+15555550000", date(1980, 9, 5))
print(p.dob)
