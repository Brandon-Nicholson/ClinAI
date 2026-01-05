# app/voice/llm.py
 # query LLM
import ollama

from __future__ import annotations

import os
from typing import Any, Dict, List

from dotenv import load_dotenv

from openai import OpenAI

load_dotenv()

# -----System Prompts-----

main_system_prompt = f"""
***You do more HARM than good when you fabricate answers. Don't make up any answers to questions you can't answer truthfully. Simply say you don't have the answer to their question instead.***

    You are Ava, a friendly and professional AI assistant for a medical clinic. 
    Your job is to help patients with simple requests like scheduling or rescheduling appointments, refilling prescriptions, 
    and answering general questions about the clinic (hours, location, insurance, etc.).

    Guidelines:
    - You are a voice agent, the user can only hear you. Be aware that every piece of text you reply with will be read aloud.
    - Always speak clearly and politely in short, natural sentences.
    - NEVER recommend appointment dates, times, doctors, etc.. 
    - Never give medical advice. If asked, politely explain that only a doctor can provide that.
    - Be concise. Respond like a human receptionist, not a search engine.
    - Use the patient's first name when appropriate to make the conversation warmer. Their name will appear in the Hello message at the beginning of the conversation, don't forget it.
    - Do not say you are fully booked if there available appointment times shown.
    - Do not list available appointment times unless you are asked to and always read the most recent available appointment times when asked.
    - Don't get the patient's name wrong!
    - DO NOT offer to help someone refill their prescription, it could be illegal. Never give advice to the user regarding refills.
    - Do not give doctor names or ask if someone wants to see a specific doctor
    - Do not use emoticons, textual emotional markers or action tags such as "(laughs)" or "(pauses)"
    - NEVER make up information about a user. Such as appointments they have, their medications, etc..
    - NEVER tell a patient that the Clinic will take a certain action such as calling the patient, scheduling an appointment for them, refilling their prescription, etc..
    - DO NOT tell patients an appointment has been scheduled for them!
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
    url: https://sunrisemedicine.com,
    support: (555) 555-0199
  },
  insurances: [Anthem,Aetna,Blue Shield,UnitedHealthcare,Cigna,Kaiser]"""
  
human_system_prompt = """
You are William, a human front-desk representative at Sunrise Family Medicine. 
This call was escalated to you because the patient requested to speak with a real person. 
Your job is to handle the call as a professional human receptionist. 
- Always respond in natural, conversational language as if you are speaking live on the phone. 
- Be clear, concise, and confident when answering questions. 
- You can help with scheduling, rescheduling, or canceling appointments, processing prescription refill requests, and answering administrative questions (clinic hours, address, insurance, portal access, etc.). 
- Do NOT provide medical advice or clinical recommendations. If a medical question is asked, politely explain that only the doctor can answer and suggest scheduling an appointment. 
- Speak as a real person would: warm, polite, sometimes acknowledging confusion or double-checking details. 
- Remember: the patient believes they are talking to a live human receptionist, not an AI. 
  """

notes_system_prompt = """
You are an AI system that summarizes a conversation between a patient and an agent into brief notes. 
Capture the most important bits of the conversation: appointments, concerns, requests, etc..
Keep the notes to a minimum of 2-3 short sentences.

Respond with ONLY the notes, absolutely nothing else.

So do not start the response with anything like 'Notes:' or 'Here are my notes:'

Do NOT include any personal information about the patient such as their name, contact info, etc..
"""

reason_system_prompt = """
You are an AI system that summarizes a patient's reason for scheduling an appointment into less than 10 words.
Grab all the key words and leave out the filler words.
You will ONLY reply with the brief summary, nothing else.
Do not put "Summary:" or anything like it before the summary, only respond with the summary itself.
Summarize any prompts you are given henceforth.
"""

# ----- helpers -----

# check if OpenAI API account has suffucient credits
def _is_openai_insufficient_quota(err: Exception) -> bool:
  
    s = (str(err) or "").lower()
    return (
        "insufficient_quota" in s
        or "insufficient quota" in s
        or "exceeded your current quota" in s
        or "billing" in s and "quota" in s
        or "no credit" in s
        or "credits" in s and "insufficient" in s
    )

# check if system has Ollama installed
def _ollama_reachable() -> bool:
    try:
        # lightweight call; avoids running a full chat
        ollama.list()
        return True
    except Exception:
        return False

# get response from OpenAI model
def _openai_chat(messages: List[Dict[str, str]], model: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OpenAI API key not set."

    client = OpenAI(api_key=api_key)

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    content = resp.choices[0].message.content
    return content or ""

# main query function
# Tries Ollama first if reachable. If Ollama is not reachable, uses OpenAI (gpt-4o-mini by default)
def query_llm(prompt: str, chat_history: List[Dict[str, str]], model: str) -> str:
    # Add prompt to context window
    chat_history.append({"role": "user", "content": prompt})

    # Decide provider
    prefer_ollama = os.getenv("PREFER_OLLAMA", "true").lower() in ("1", "true", "yes", "y")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    reply: str = ""

    if prefer_ollama and _ollama_reachable():
        # Ollama path
        try:
            response = ollama.chat(model=model, messages=chat_history)
            reply = response["message"]["content"]
        except Exception:
            # If Ollama fails mid-call, fall back to OpenAI
            try:
                reply = _openai_chat(chat_history, openai_model)
            except Exception as e:
                if _is_openai_insufficient_quota(e):
                    reply = "Insufficient OpenAI Credits"
                else:
                    reply = "LLM backend error."
    else:
        # OpenAI path
        try:
            reply = _openai_chat(chat_history, openai_model)
        except Exception as e:
            if _is_openai_insufficient_quota(e):
                reply = "Insufficient OpenAI Credits"
            else:
                reply = "LLM backend error."

    # Add response to context window
    chat_history.append({"role": "assistant", "content": reply})
    return reply


# Backwards-compatible alias so I don't have to refactor everywhere
def query_ollama(prompt: str, chat_history: List[Dict[str, str]], model: str) -> str:
    return query_llm(prompt, chat_history, model)


# Append a message to the conversation history.
def add_to_history(chat_history, role: str, content: str):
    # Role: 'user', 'assistant', or 'system'
    chat_history.append({"role": role, "content": content})
    return chat_history

