import ollama

response = ollama.chat(model="llama3.1:8b",
                       messages=[{"role": "user", "content": "Hello World"}])

print(response['message']['content'])
