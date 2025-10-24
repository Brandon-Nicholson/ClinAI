This module trains a DistilBERT-based classifier to detect patient if a patient wants to exit the appointment scheduling pipeline (or not) from natural language queries in the ClinAI assistant. The agent will stop trying to make an appointment for the patient if the classifier returns "EXIT_APPT

Labels:
STAY_APPT -> keep the appointment scheduling process going
EXIT_APPT -> exit the appointment scheduling process

Training data was generated using AI-assisted synthetic data creation. For each classification, hundreds of paraphrased examples were produced and saved as .csv files in data/appt_context_examples/.

Training:
Model: distilbert-base-uncased

Framework: Hugging Face Transformers + Datasets

Epochs: 4

Learning rate: 2e-5

Train/test split: 90/10 stratified

Output directory: classifiers/appt_context_model/appt_context_classifier/

Results:
The model achieved ~100% accuracy on the held-out evaluation set (synthetic data).
