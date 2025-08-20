 # query LLM
import ollama

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