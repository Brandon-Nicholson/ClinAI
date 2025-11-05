import ollama
import datetime

today = datetime.date.today()
formatted = today.strftime("%A %B %d, %Y")

prompt = "can you schedule me for october 19th?"
chat_history = [{"role":"system", "content": prompt}]

chat_history.append({"role": "user", "content": prompt})
response = ollama.chat(model="llama3.1:8b",
                       messages=chat_history)

print(response["message"]["content"])



