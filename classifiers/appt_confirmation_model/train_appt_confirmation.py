from transformers import (DistilBertTokenizerFast, DistilBertForSequenceClassification, 
                          Trainer, TrainingArguments, set_seed)
from datasets import load_dataset, Dataset
from sklearn.model_selection import train_test_split
import pandas as pd
import torch
import os

set_seed(42)

# 1️⃣ Define labels
LABELS = ["CONFIRM", "REJECT", "UNSURE"]
label2id = {l:i for i,l in enumerate(LABELS)}
id2label = {i:l for l,i in label2id.items()}

directory_path = "./data/appt_confirmation_examples"

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
    temp_df = pd.read_csv(f".//data//appt_confirmation_examples//{file}")
    df = pd.concat([df, temp_df])
# drop any duplicate rows    
df = df.drop_duplicates()
print(len(df))

df["label"] = df["label"].str.upper().str.strip()
df["labels"] = df["label"].map(label2id).astype("int64")

# Split
train_df, val_df = train_test_split(df, test_size=0.15, stratify=df["labels"], random_state=42)

# HF datasets
tok = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")
def tok_fn(ex): return tok(ex["text"], truncation=True, padding="max_length", max_length=96)

train_ds = Dataset.from_pandas(train_df[["text","labels"]].reset_index(drop=True)).map(tok_fn, batched=True)
val_ds   = Dataset.from_pandas(val_df[["text","labels"]].reset_index(drop=True)).map(tok_fn, batched=True)

model = DistilBertForSequenceClassification.from_pretrained(
    "distilbert-base-uncased",
    num_labels=len(LABELS),
    id2label=id2label,
    label2id=label2id
)

args = TrainingArguments(
    output_dir="./classifiers/appt_confirmation_classifier",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=4,
    weight_decay=0.01,
    logging_dir="./logs",
    load_best_model_at_end=False,
)

trainer = Trainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds)
trainer.train()
trainer.save_model("./classifiers/appt_confirmation_classifier")
tok.save_pretrained("./classifiers/appt_confirmation_classifier")