# app/ui/intake_form.py
import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from app.services.patient_service import intake_patient

# Popup window for patient intake form before conversaion loop Returns the Patient object
def run_intake_form():
    patient_result = {}

    def submit():
        first = entry_first.get()
        last = entry_last.get()
        phone = entry_phone.get()
        dob_str = entry_dob.get()

        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            dob = None

        # validate before calling intake_patient
        '''
        if not first or not last or not phone or not dob:
            messagebox.showerror("Error", "All fields are required.")
            return
        '''
        
        p = intake_patient(first, last, phone, dob)
        patient_result["patient"] = p
        root.destroy()

    root = tk.Tk()
    root.title("ClinAI Intake")

    tk.Label(root, text="First Name").grid(row=0, column=0)
    tk.Label(root, text="Last Name").grid(row=1, column=0)
    tk.Label(root, text="Phone").grid(row=2, column=0)
    tk.Label(root, text="DOB (YYYY-MM-DD)").grid(row=3, column=0)

    entry_first = tk.Entry(root); entry_first.grid(row=0, column=1)
    entry_last = tk.Entry(root); entry_last.grid(row=1, column=1)
    entry_phone = tk.Entry(root); entry_phone.grid(row=2, column=1)
    entry_dob = tk.Entry(root); entry_dob.grid(row=3, column=1)

    tk.Button(root, text="Submit", command=submit).grid(row=4, columnspan=2)
    root.mainloop()

    return patient_result.get("patient")
