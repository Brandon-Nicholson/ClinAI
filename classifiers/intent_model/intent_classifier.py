# intent_model/intent_classifer.py

import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

MODEL_DIR = "./classifiers/intent_model/intent_classifier"

_tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
_model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR).eval()

# use the fine-tuned distilBERT model to classify for intent
def classify_intent(text: str, patient_intents: list) -> str:
    enc = _tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=128)
    with torch.no_grad():
        logits = _model(**enc).logits
        pred_id = int(torch.argmax(logits, dim=1).item())
        intent = _model.config.id2label[pred_id]
        patient_intents.append(intent)
    return intent

# print(classify_intent("What about 330?", ['ADMIN_INFO']))