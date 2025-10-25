# intent_model/train_intent.py
import os, json
from sklearn.model_selection import train_test_split
from datasets import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          DistilBertForSequenceClassification, DistilBertTokenizerFast,
                          Trainer, TrainingArguments, set_seed)
import torch
import pandas as pd
import numpy as np
from evaluate import load

set_seed(42)

directory_path = "./data/intent_examples"

try:
    # Get the list of csv files in the directory
    contents = os.listdir(directory_path)

    csv_files = [item for item in contents]

except FileNotFoundError:
    print(f"Error: Directory '{directory_path}' not found.")
except NotADirectoryError:
    print(f"Error: '{directory_path}' is not a directory.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

# concat all csv files
df = pd.DataFrame()
for file in csv_files:
    temp_df = pd.read_csv(f".//data//intent_examples//{file}")
    df = pd.concat([df, temp_df])
# drop any duplicate rows    
df = df.drop_duplicates()
print(len(df))

# Label map (6 classes)
label_map_str2id = {
    "APPT_NEW": 0,
    "APPT_RESCHEDULE": 1,
    "APPT_CANCEL": 2,
    "RX_REFILL": 3,
    "ADMIN_INFO": 4,
    "OTHER": 5,
    "HUMAN_AGENT": 6
}
label_map_id2str = {v: k for k, v in label_map_str2id.items()}

# Save alongsidetraining script
os.makedirs("./intent_model", exist_ok=True)
with open("./intent_model/label_map.json", "w") as f:
    json.dump({str(k): v for k, v in label_map_id2str.items()}, f, indent=2)

# Map labels to ints
df["labels"] = df["label"].map(label_map_str2id)

# Train / test split
train_df, test_df = train_test_split(
    df, test_size=0.1, stratify=df["labels"], random_state=42
)

# Hugging Face datasets
train_dataset = Dataset.from_pandas(train_df.reset_index(drop=True))
test_dataset  = Dataset.from_pandas(test_df.reset_index(drop=True))

# Tokenizer
base_model = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(base_model)

def tokenize(batch):
    return tokenizer(batch["text"], padding="max_length", truncation=True, max_length=128)

train_dataset = train_dataset.map(tokenize, batched=True)
test_dataset  = test_dataset.map(tokenize, batched=True)

# Set torch columns (use "labels", not "label")
train_dataset.set_format("torch", columns=["input_ids", "attention_mask", "labels"])
test_dataset.set_format("torch", columns=["input_ids", "attention_mask", "labels"])

# Model (6 labels) + set id2label/label2id so config carries names
model = AutoModelForSequenceClassification.from_pretrained(
    base_model, num_labels=7
)
model.config.id2label = label_map_id2str
model.config.label2id = label_map_str2id

# Metrics
accuracy_metric = load("accuracy")
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return accuracy_metric.compute(predictions=preds, references=labels)

# Training args
training_args = TrainingArguments(
    output_dir="./classifiers/intent_model/intent_classifier",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=5,
    weight_decay=0.01,
    logging_dir="./logs",
    logging_steps=20,
    save_total_limit=2,
    load_best_model_at_end=False,
)

# Trainer
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=test_dataset,
    tokenizer=tokenizer,
    compute_metrics=compute_metrics
)

trainer.train()
eval_results = trainer.evaluate()
print(eval_results)

# Save final model (will include id2label/label2id in config.json)
save_dir = "./classifiers/intent_model/intent_classifier"
trainer.save_model(save_dir)
tokenizer.save_pretrained(save_dir)

# Inference helper
def classify(text: str):
    tok = DistilBertTokenizerFast.from_pretrained(save_dir)
    mdl = DistilBertForSequenceClassification.from_pretrained(save_dir)
    enc = tok(text, return_tensors="pt", truncation=True, padding=True, max_length=128)
    mdl.eval()
    with torch.no_grad():
        out = mdl(**enc)
        pred_id = int(torch.argmax(out.logits, dim=1).item())
    return mdl.config.id2label[pred_id]
