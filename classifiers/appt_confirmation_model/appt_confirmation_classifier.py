import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

MODEL_DIR = "./classifiers/appt_confirmation_model/appt_confirmation_classifier"

_tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
_model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR).eval()

# use the fine-tuned distilBERT model to classify for intent
def classify_appt_confirmation(text: str) -> str:
    enc = _tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=128)
    with torch.no_grad():
        logits = _model(**enc).logits
        pred_id = int(torch.argmax(logits, dim=1).item())
        classification = _model.config.id2label[pred_id]
    return classification