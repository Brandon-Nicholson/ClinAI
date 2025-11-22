This module trains a DistilBERT-based classifier to detect patient if a patient confirms or denies an appointment date/time from natural language queries in the ClinAI assistant. The agent will update the db with the appointment info if confirmed, ask to try again or exit the appointment scheduling pipeline if the appointment is rejected or ask the user to repeat themselves if unsure of their response.

Labels:
CONFIRM -> confirm appointment and update db
REJECT -> reject appointment; try again or exit appt scheduler
UNSURE -> ask user to repeat their answer more clearly

Training data was generated using AI-assisted synthetic data creation. For each classification, hundreds of paraphrased examples were produced and saved as .csv files in data/appt_confirmation_examples/.

Training:
Model: distilbert-base-uncased

Framework: Hugging Face Transformers + Datasets

Epochs: 4

Learning rate: 2e-5

Train/test split: 90/10 stratified

Output directory: classifiers/appt_confirmation_model/appt_confirmation_classifier/

Results:
The model achieved ~99% accuracy on the held-out evaluation set (synthetic data).
