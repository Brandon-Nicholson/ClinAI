# intent_model/intent_classifier.py

import os
import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

# Use HF repo
MODEL_ID = os.getenv(
    "INTENT_MODEL_ID",
    "Exogenesis/clinai-intent-classifier",
)

_tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_ID)
_model = DistilBertForSequenceClassification.from_pretrained(MODEL_ID).eval()

def classify_intent(text: str, patient_intents: list) -> str:
    enc = _tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128,
    )
    with torch.no_grad():
        logits = _model(**enc).logits
        pred_id = int(torch.argmax(logits, dim=1).item())
        intent = _model.config.id2label[pred_id]
        patient_intents.append(intent)
    return intent