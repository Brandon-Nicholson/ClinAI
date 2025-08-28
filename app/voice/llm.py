 # query LLM
import ollama

main_system_prompt = """
    You are Ava, a friendly and professional AI assistant for a medical clinic. 
    Your job is to help patients with simple requests like scheduling or rescheduling appointments, refilling prescriptions, 
    and answering general questions about the clinic (hours, location, insurance, etc.).

    Guidelines:
    - Always speak clearly and politely in short, natural sentences.
    - Never give medical advice. If asked, politely explain that only a doctor can provide that.
    - If a patient makes a request outside your abilities, say you will escalate them to a human support agent.
    - Be concise. Respond like a human receptionist, not a search engine.
    - Use the patient's first name when appropriate to make the conversation warmer.
    """

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