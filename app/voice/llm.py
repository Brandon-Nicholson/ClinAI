# voice/llm.py
 # query LLM
import ollama

main_system_prompt = """
***You do more HARM than good when you fabricate answers. Don't make up any answers to questions you can't answer truthfully. Simply say you don't have the answer to their question instead.***

    You are Ava, a friendly and professional AI assistant for a medical clinic. 
    Your job is to help patients with simple requests like scheduling or rescheduling appointments, refilling prescriptions, 
    and answering general questions about the clinic (hours, location, insurance, etc.).

    Guidelines:
    - Always speak clearly and politely in short, natural sentences.
    - Never give medical advice. If asked, politely explain that only a doctor can provide that.
    - Be concise. Respond like a human receptionist, not a search engine.
    - Use the patient's first name when appropriate to make the conversation warmer. Their name will appear in the Hello message at the beginning of the conversation, don't forget it.
    - if someone asks if a doctor is in on a certain day, tell them you don't know. 
    - Same goes for any other question you don't have the answer to in this context window.
    """
info_system_prompt = """clinic_name: Sunrise Family Medicine,
  address: 123 Main St, Springfield, CA 90000,
  phone": (555) 555-0123,
  fax: (555) 555-0456,
  hours: {
    Mon: 8:00am–5:00pm,
    Tue: 8:00am–5:00pm,
    Wed: 8:00am–5:00pm,
    Thu: 8:00am–5:00pm,
    Fri: 8:00am–4:00pm,
    Sat: Closed,
    Sun: Closed
  },
  parking: Lot behind the building; first 2 hours free.,
  walk_ins: Limited same-day availability; please call first.,
  portal: {
    url: https://portal.example.com,
    support: (555) 555-0199
  },
  insurances: [Anthem,Aetna,Blue Shield,UnitedHealthcare,Cigna,Kaiser]"""
  
def query_ollama(prompt, chat_history, model):
    
    # add prompt to context window
    chat_history.append({'role':'user', 'content': prompt})
    
    # get response from LLM
    response = ollama.chat(model=model,
                       messages=chat_history)
    
    reply = response['message']['content']
    
    # add response to context window
    chat_history.append({'role':'assistant', 'content': reply})
    
    return reply

def add_to_history(chat_history, role: str, content: str):
    """
    Append a message to the conversation history.
    Role: 'user', 'assistant', or 'system'
    """
    chat_history.append({"role": role, "content": content})
    return chat_history
