import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

MODEL_DIR = "./intent_model/intent_classifier"

# Load once
tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_DIR)
model = DistilBertForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()

def classify(text: str):
    enc = tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=128)
    with torch.no_grad():
        out = model(**enc)
        pred_id = int(torch.argmax(out.logits, dim=1).item())
    return model.config.id2label[pred_id]

tests = [
    # APPT_NEW
    "Book me in for next Monday morning.",
    "Could I get an appointment with Dr. Kim?",
    "I’d like to set something up for early next week.",

    # APPT_RESCHEDULE
    "Can we push my appointment back a week?",
    "I need to move my Friday slot to Tuesday.",
    "Please reschedule my checkup for a later date.",

    # APPT_CANCEL
    "I won’t be able to make my appointment, cancel it.",
    "Remove my booking for Wednesday with Dr. Brown.",
    "Can you cancel my visit next week?",

    # RX_REFILL
    "I’m out of Metformin, can you refill it?",
    "Need a new prescription for Atorvastatin.",
    "Please send a refill for my Lisinopril to CVS.",

    # ADMIN_INFO
    "What time do you close on Fridays?",
    "Where exactly is the clinic located?",
    "Do you guys take UnitedHealthcare insurance?",

    # OTHER
    "Thanks for all your help today.",
    "I’ve been feeling really tired lately.",
    "Good morning, how are you?",
]


for t in tests:
    print(f"{t:40} -> {classify(t)}")
