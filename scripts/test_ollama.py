import ollama
import datetime
from app.voice.llm import date_parser_system_prompt

today = datetime.date.today()
formatted = today.strftime("%A %B %d, %Y")

chat_history = [{"role":"system", "content": date_parser_system_prompt},
                {"role":"system", "content": f"Today is {formatted}. Make note of the current year and month. If someone asks to schedule an appointment for a month that has already passed this year, schedule it for NEXT year."},
                {"role":"system", "content": "ONLY ADD ANOTHER YEAR IF THE MONTH GIVEN HAS ALREADY PASSED THIS YEAR"}
                ]

prompt = "can you schedule me for october 19th"

chat_history.append({"role": "user", "content": prompt})
response = ollama.chat(model="llama3.1:8b",
                       messages=chat_history)

print(response["message"]["content"])



