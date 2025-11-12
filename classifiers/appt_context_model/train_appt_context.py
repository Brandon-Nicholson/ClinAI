# train_appt_context.py

from transformers import (DistilBertTokenizerFast, DistilBertForSequenceClassification, 
                          Trainer, TrainingArguments, set_seed)
from datasets import load_dataset, Dataset
from sklearn.model_selection import train_test_split
import pandas as pd
import torch
import os

set_seed(42)

# 1️⃣ Define labels
LABELS = ["STAY_APPT", "EXIT_APPT"]
label2id = {l:i for i,l in enumerate(LABELS)}
id2label = {i:l for l,i in label2id.items()}

directory_path = "./data/appt_context_examples"

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
    temp_df = pd.read_csv(f".//data//appt_context_examples//{file}")
    df = pd.concat([df, temp_df])
# drop any duplicate rows    
df = df.drop_duplicates()
print(len(df))

# Train / test split
train_df, val_df = train_test_split(
    df, test_size=0.1, stratify=df["label"], random_state=42
)

# Convert labels to numeric ids
train_df["labels"] = train_df["label"].map(label2id)
val_df["labels"]   = val_df["label"].map(label2id)

# Drop original string column
train_df = train_df.drop(columns=["label"]).dropna(subset=["labels"])
val_df   = val_df.drop(columns=["label"]).dropna(subset=["labels"])

# HuggingFace Dataset
train_ds = Dataset.from_pandas(train_df.reset_index(drop=True))
val_ds   = Dataset.from_pandas(val_df.reset_index(drop=True))

# 3️⃣ Tokenize
tok = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")
def tok_fn(ex):
    return tok(ex["text"], truncation=True, padding="max_length", max_length=128)
train_ds = train_ds.map(tok_fn, batched=True)
val_ds   = val_ds.map(tok_fn, batched=True)

# 4️⃣ Model
model = DistilBertForSequenceClassification.from_pretrained(
    "distilbert-base-uncased",
    num_labels=len(LABELS),
    id2label=id2label,
    label2id=label2id
)

# 5️⃣ Training args
args = TrainingArguments(
    output_dir="./classifiers/appt_context_model/appt_context_classifier",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=4,
    weight_decay=0.01,
    logging_dir="./logs",
    load_best_model_at_end=False
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=train_ds,
    eval_dataset=val_ds
)

trainer.train()
trainer.save_model("./classifiers/appt_context_model/appt_context_classifier")
tok.save_pretrained("./classifiers/appt_context_model/appt_context_classifier")
