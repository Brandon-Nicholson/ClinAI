import os
import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

# Hugging Face model repo (env override for prod)
MODEL_ID = os.getenv(
    "CONFIRM_MODEL_ID",
    "Exogenesis/clinai-confirmation-classifier",
)

_tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_ID)
_model = DistilBertForSequenceClassification.from_pretrained(MODEL_ID).eval()

# use the fine-tuned distilBERT model to classify for appointment confirmation
def classify_confirmation(text: str) -> str:
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
        classification = _model.config.id2label[pred_id]
    return classification
