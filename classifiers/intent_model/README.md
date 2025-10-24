This module trains a DistilBERT-based classifier to detect patient intent from natural language queries in the ClinAI assistant. It helps the agent decide whether a user wants to schedule, reschedule, cancel an appointment, request a prescription refill, ask for administrative info, or is simply engaging in other conversation.

Labels:
APPT_NEW → scheduling a new appointment

APPT_RESCHEDULE = rescheduling an existing appointment

APPT_CANCEL = cancelling an appointment

RX_REFILL = medication refill requests

ADMIN_INFO = questions about hours, location, insurance, portal, etc.

OTHER = chit-chat or unrelated dialogue

Training data was generated using AI-assisted synthetic data creation. For each intent, hundreds of paraphrased examples were produced and saved as .csv files in data/intent_examples/.

Training:
Model: distilbert-base-uncased

Framework: Hugging Face Transformers + Datasets

Epochs: 5

Learning rate: 2e-5

Train/test split: 90/10 stratified

Output directory: classifiers/intent_model/intent_classifier/

Results:
The model achieved ~100% accuracy on the held-out evaluation set (synthetic data).
Real-world testing showed very good performance, though some ambiguous edge cases prompted retraining with additional examples (e.g., short questions misclassified as ADMIN_INFO).
