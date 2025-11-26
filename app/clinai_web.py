"""
app/clinai_web.py

The main logic file for the ClinAI web application.

This module contains the core functionalities and routing for ClinaAI.
"""

from __future__ import annotations

import json
import uuid
from typing import Dict, Optional, List
from datetime import date

import pathlib
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import base64
import io
import asyncio
import edge_tts
import tempfile
import os
from faster_whisper import WhisperModel

import subprocess
FFMPEG_BIN = r"C:\ffmpeg\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe" # path to ffmpeg

# ---- Imports from your existing app ----
from app.services.call_service import (start_call,end_call,set_intent,log_turn,
    was_resolved,call_notes,)
from app.services.patient_service import intake_patient, get_by_phone
from app.services.rx_refills import match_medication, handle_refill_request, MEDS
from app.voice.llm import (query_ollama, add_to_history, main_system_prompt, info_system_prompt,
    human_system_prompt, reason_system_prompt)
from classifiers.intent_model.intent_classifier import classify_intent
from classifiers.appt_context_model.appt_context_classifier import classify_appt_context
from classifiers.confirmation_model.confirmation_classifier import classify_confirmation
import app.services.appointments as ap

# ---------------------------------------------------
# FastAPI app
# ---------------------------------------------------

app = FastAPI(title="ClinAI Web Demo")

BASE_DIR = pathlib.Path(__file__).resolve().parent

# Serve static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/")
async def root():
    # Serve the main HTML page
    return FileResponse(BASE_DIR / "static" / "index.html")

# ----- TTS config -----
EDGE_TTS_VOICE = "en-US-AvaNeural"
EDGE_TTS_VOICE_INTRO = "en-US-RogerNeural"
EDGE_TTS_FAKE_REP_VOICE = "en-AU-WilliamMultilingualNeural"
FAKE_REP_TRIGGER = "Hi, this is William"
EDGE_TTS_RATE = "+15%"

async def tts_to_mp3_bytes(text: str, voice: str) -> bytes:
    """
    Use Edge TTS to synthesize `text` into MP3 bytes (in-memory),
    without playing locally.
    """
    mp3_fp = io.BytesIO()
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=EDGE_TTS_RATE,
    )

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_fp.write(chunk["data"])

    mp3_fp.seek(0)
    return mp3_fp.read()

# ----- Whisper STT for browser audio -----

print("[ClinAI-Web] Loading Whisper model...")
WHISPER_MODEL = WhisperModel("medium", device="cuda", compute_type="float16")


def _seg_conf(seg):
    # prefer avg_logprob / avg_log_prob
    return getattr(seg, "avg_logprob", getattr(seg, "avg_log_prob", -10.0))

# return avg confidence score for transcribed text
def _avg_conf_and_text(segments):
    segs = list(segments)
    if not segs:
        return -10.0, ""
    text = " ".join(s.text.strip() for s in segs).strip()
    conf = sum(_seg_conf(s) for s in segs) / max(len(segs), 1)
    return conf, text

# Run Whisper on a WAV file and apply confidence gating logic
def transcribe_file_with_gate(path: str, min_conf: float = -0.70) -> str:
    try:
        # transcribe speech
        segments_iter, _ = WHISPER_MODEL.transcribe(
            path,
            language="en",
            beam_size=1,
            word_timestamps=False,
        )
        segments = list(segments_iter)
    except Exception as e:
        print("[STT] Whisper error in web app:", e)
        return ""

    avg_conf, text = _avg_conf_and_text(segments)
    if not text:
        return ""

    # adjust confidence score for prompts with less words
    word_count = len(text.split())
    if word_count < 3:
        adj_conf = avg_conf + 0.40
    elif word_count == 3:
        adj_conf = avg_conf + 0.35
    else:
        adj_conf = avg_conf

    print(f"[STT] text={text!r} avg_conf={avg_conf:.2f} adj_conf={adj_conf:.2f}")
    # return inaudible note if conf threshold not met
    if adj_conf < min_conf:
        return "[Inaudible Message]"
    return text

# ---------------------------------------------------
# Session models for API
# ---------------------------------------------------

class StartSessionRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: str
    dob: Optional[str] = None


class StartSessionResponse(BaseModel):
    session_id: str
    messages: List[Dict[str, str]]  # [{"role": "assistant", "content": "..."}]
    audio_b64: Optional[str] = None


class TurnRequest(BaseModel):
    session_id: str
    user_input: str


class TurnResponse(BaseModel):
    agent_message: str
    end_call: bool
    audio_b64: Optional[str] = None
    # For voice mode: what the STT heard from user
    user_transcript: Optional[str] = None

# ---------------------------------------------------
# Core stateful session (port of main loop)
# ---------------------------------------------------

class ClinAISession:

    _sch = ap.start_scheduler() # Update status of appointments that already happened
    
    def __init__(self, patient, call):
        self.patient = patient
        self.call = call

        # LLM + chat context
        self.llm_model = "llama3.1:8b"
        self.chat_history = [
            {"role": "system", "content": main_system_prompt},
            {"role": "system", "content": info_system_prompt},
        ]

        # appointment + refill state
        self.temp_appt_date = ap.new_temp_appt_date()
        self.appt_state: Optional[str] = None
        self.reschedule_state: Optional[str] = None
        self.availability_state: Optional[str] = None
        self.refill_state: Optional[str] = None
        self.last_available_time: Optional[str] = None

        # overall call state
        self.patient_intents: List[str] = []
        self.escalated: bool = False
        self.loop_convo: bool = True
        self.awaiting_feedback: bool = False
        self.resolved: Optional[bool] = None

        # used in cancel flows
        self.pretty_cancel_date: Optional[str] = None
        self.cancel_appt_id: Optional[int] = None

    # ---------- lifecycle helpers ----------

    def start(self) -> List[Dict[str, str]]:
        # Called once after session is created. Returns intro + welcome messages.
        intro_msg = (
            "Your conversation may be monitored or recorded. "
            "You can say 'stop' or 'quit' at any time to exit the conversation."
        )
        add_to_history(self.chat_history, "system", intro_msg)
        log_turn(self.call.id, "assistant", intro_msg)

        welcome_msg = f"Hi {self.patient.first_name}, I'm Ava. How can I assist you today?"
        add_to_history(self.chat_history, "assistant", welcome_msg)
        log_turn(self.call.id, "assistant", welcome_msg)

        return [
            {"role": "assistant", "content": intro_msg},
            {"role": "assistant", "content": welcome_msg},
        ]

    def end(self):
        # Wrap up call in DB, including summary notes + intents
        intents_json = json.dumps(self.patient_intents)
        set_intent(self.call.id, intents_json)

        notes = call_notes(self.chat_history[:], self.llm_model)  # pass a copy
        end_call(
            self.call.id,
            resolved=self.resolved if self.resolved is not None else False,
            escalated=self.escalated,
            notes=notes,
        )

    # ---------- main turn handler ----------

    def handle_turn(self, user_input: str) -> Dict[str, object]:
        """
        Single conversational turn

        Returns:
            {"agent_message": str, "end_call": bool}
        """

        user_input = (user_input or "").strip()

        # If in the feedback phase, interpret this as resolved/not resolved.
        if self.awaiting_feedback:
            self.resolved = was_resolved(user_input)
            goodbye_msg = "Your feedback is appreciated. Goodbye!"
            add_to_history(self.chat_history, "assistant", goodbye_msg)
            log_turn(self.call.id, "assistant", goodbye_msg)
            return {"agent_message": goodbye_msg, "end_call": True}

        # Handle empty input if browser sent empty message
        if not user_input:
            repeat_msg = "Sorry, I didn’t catch that clearly. Could you repeat?"
            add_to_history(self.chat_history, "assistant", repeat_msg)
            log_turn(self.call.id, "assistant", repeat_msg)
            return {"agent_message": repeat_msg, "end_call": False}

        # Log user input
        add_to_history(self.chat_history, "user", user_input)
        log_turn(self.call.id, "user", user_input)

        # ---------- user wants to end call ----------
        exit_words = {
            "exit",
            "quit",
            "stop",
            "goodbye",
            "good bye",
            "up",
            "top",
            "exit.",
            "quit.",
            "stop.",
            "goodbye.",
            "good bye.",
            "up.",
            "top.",
            "exit!",
            "quit!",
            "stop!",
            "goodbye!",
            "good bye!",
            "up!",
            "top!",
        } # ('up' and 'top' are commonly transcribed from 'stop')

        if user_input.lower() in exit_words:
            feedback_msg = (
                f"The conversation has ended. Was your query resolved today, "
                f"{self.patient.first_name}?"
            )
            add_to_history(self.chat_history, "assistant", feedback_msg)
            log_turn(self.call.id, "assistant", feedback_msg)
            self.awaiting_feedback = True
            return {"agent_message": feedback_msg, "end_call": False}

        # ---------- classify intent ----------
        intent = classify_intent(user_input, self.patient_intents)
        print(f"Prompt Intent: {intent}")
        print(f"Appt State: {self.appt_state}")

        # conflict helpers
        if self.appt_state == "awaiting_cancellation_date":
            intent = "APPT_CANCEL"
        if self.refill_state == "drug_name":
            intent = "RX_REFILL"

        # 1. ---------- HUMAN ESCALATION ----------
        if intent == "HUMAN_AGENT" and not self.escalated:
            self.escalated = True

            escalation_msg = "Please hold while I transfer you to a human representative..."
            add_to_history(self.chat_history, "assistant", escalation_msg)
            log_turn(self.call.id, "assistant", escalation_msg)

            # swap system prompt to human version
            # remove first system prompt, then add new one
            self.chat_history.pop(0)
            add_to_history(self.chat_history, "system", human_system_prompt)

            fake_rep_msg = (
                "Hi, this is William with Sunrise Family Medicine. "
                "How can I help you today?"
            )
            add_to_history(self.chat_history, "assistant", fake_rep_msg)
            log_turn(self.call.id, "assistant", fake_rep_msg)

            # reset process states
            self.temp_appt_date = ap.new_temp_appt_date()
            self.appt_state = None
            self.availability_state = None
            self.reschedule_state = None
            self.refill_state = None

            combined = escalation_msg + " " + fake_rep_msg
            return {"agent_message": combined, "end_call": False}

        # 2. ---------- ADMIN INFO ----------
        if intent == "ADMIN_INFO":
            response = query_ollama(user_input, self.chat_history, self.llm_model)
            add_to_history(self.chat_history, "assistant", response)
            log_turn(self.call.id, "assistant", response)

            # reset pending_confirmation if we detoured
            if self.appt_state == "pending_confirmation":
                self.appt_state = None
                self.temp_appt_date = ap.new_temp_appt_date()

            return {"agent_message": response, "end_call": False}
        
        # 3. ---------- DATE/TIME EXTRACTION ----------
        run_dt_extraction = (
            intent in ["APPT_NEW", "APPT_CANCEL", "APPT_RESCHEDULE"]
            or self.appt_state in [
                "scheduling_appt",
                "pending_confirmation",
                "appt_confirmed",
                "appt_reason",
                "cancelling_appt",
                "confirm_cancellation",
                "awaiting_cancellation_date",
            ]
        )

        prev_temp_appt = self.temp_appt_date.copy()

        if run_dt_extraction:
            formatted_input = ap.format_prompt_time(user_input)
            results = ap.extract_schedule_json(formatted_input)

            if results:
                if (results[0]["date"] != self.temp_appt_date["date"] and 
                    self.availability_state != "confirm_last_slot" and
                    self.appt_state != "pending_confirmation"):
                    self.availability_state = "check_availability"

                self.temp_appt_date = ap.update_results(results[-1], self.temp_appt_date)
                self.temp_appt_date = ap.ampm_mislabel_fix(self.temp_appt_date)
                print(self.temp_appt_date)

            # "one" -> 01:00 edge case without appt action
            if (
                self.temp_appt_date["time"] == "01:00"
                and intent not in ["APPT_NEW", "APPT_CANCEL", "APPT_RESCHEDULE"]
                and self.appt_state
                not in [
                    "scheduling_appt",
                    "pending_confirmation",
                    "appt_confirmed",
                    "appt_reason",
                    "cancelling_appt",
                    "confirm_cancellation",
                    "awaiting_cancellation_dates",
                ]
            ):
                self.temp_appt_date = ap.new_temp_appt_date()

        # 4. ---------- APPOINTMENT CANCELLATION CONFIRM ----------
        if self.appt_state == "confirm_cancellation":
            confirm_appt_cancellation = classify_confirmation(user_input)

            if confirm_appt_cancellation == "CONFIRM":
                ap.cancel_appointment(self.cancel_appt_id)

                if self.reschedule_state == "cancel_for_rescheduling":
                    msg = (
                        "Your appointment has been cancelled. Please state a date and time "
                        "for your new appointment."
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.temp_appt_date = ap.new_temp_appt_date()
                    self.appt_state = "scheduling_appt"
                    self.reschedule_state = None
                    return {"agent_message": msg, "end_call": False}

                msg = (
                    "Your appointment has been cancelled. If you'd like to make another "
                    "appointment or request, just ask! If you'd like to end the call now, say stop."
                    )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.temp_appt_date = ap.new_temp_appt_date()
                self.appt_state = None
                self.availability_state = None
                return {"agent_message": msg, "end_call": False}

            elif confirm_appt_cancellation == "UNSURE":
                msg = (
                    f"Sorry, I didn't catch your answer. Would you still like to cancel your "
                    f"appointment for {self.pretty_cancel_date}?"
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}

            elif confirm_appt_cancellation == "REJECT":
                msg = (
                    "No problem, we won't cancel that appointment. Let me know if you need "
                    "anything else or say 'stop' to end the call."
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.temp_appt_date = ap.new_temp_appt_date()
                self.appt_state = None
                self.availability_state = None
                self.reschedule_state = None
                return {"agent_message": msg, "end_call": False}

        # 5. ---------- LAST AVAILABLE SLOT CONFIRM ----------
        if self.availability_state == "confirm_last_slot":
            # check if user changed the date/time this turn
            changed_dt = (
                prev_temp_appt.get("date") != self.temp_appt_date.get("date")
                or prev_temp_appt.get("time") != self.temp_appt_date.get("time")
            )
            print(f"changed_dt: {changed_dt}")
            # if user changes date/time during this turn (assume reject, focus on new appt date)
            if changed_dt: 
                # user changed both date and time in this turn
                if self.temp_appt_date["date"] and self.temp_appt_date["time"]:
                    # User said something about scheduling a different date/time
                    pretty_date = ap.prettify_date(self.temp_appt_date["date"])
                    msg = (
                        f"Okay, let's update that. To confirm, you'd like to schedule your "
                        f"appointment for {pretty_date} at "
                        f"{ap.format_appt_time(self.temp_appt_date['time'])}"
                        f"{self.temp_appt_date['ampm']}, is that correct?"
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    # stay in pending_confirmation with the new date/time
                    self.appt_state = "pending_confirmation"
                    return {"agent_message": msg, "end_call": False}

                elif self.temp_appt_date["date"] and not self.temp_appt_date["time"]:
                    # Reset to scheduling flow and trigger availability check
                    self.appt_state = "scheduling_appt"
                    self.availability_state = "check_availability"
                    # fall through to scheduling logic below
                    
            else:        
            # classify user confirmation response
                confirm_last_appt_time = classify_confirmation(user_input)
                if confirm_last_appt_time == "CONFIRM":
                    self.temp_appt_date["time"] = self.last_available_time
                    self.temp_appt_date = ap.ampm_mislabel_fix(self.temp_appt_date)
                    self.appt_state = "appt_confirmed"
                    self.availability_state = None
                    # fall through to "ask reason" below
                    
                elif confirm_last_appt_time == "UNSURE":
                    msg = (
                        f"Sorry, I didn't catch your answer. Please confirm, does "
                        f"{self.last_available_time} work for you?"
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    return {"agent_message": msg, "end_call": False}
                
                elif confirm_last_appt_time == "REJECT":
                    # no new date/time given
                    msg = "Please state another day you would like to schedule your appointment for... Or if you'd like to stop scheduling, just say so!"
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.temp_appt_date = ap.new_temp_appt_date()
                    self.appt_state = "scheduling_appt"
                    self.availability_state = None
                    return {"agent_message": msg, "end_call": False}
                
        # 6. ---------- CONFIRM APPOINTMENT DATE/TIME ----------
        if (
            not ap.missing_info_check(self.temp_appt_date)
            and self.appt_state == "pending_confirmation"
        ):
            # check if user changed the date/time this turn
            changed_dt = (
                prev_temp_appt.get("date") != self.temp_appt_date.get("date")
                or prev_temp_appt.get("time") != self.temp_appt_date.get("time")
            )
            # classify user prompt to see if they confirmed or denied the appointment date/time
            confirmed_appt = classify_confirmation(user_input)

            if confirmed_appt == "CONFIRM":
                self.appt_state = "appt_confirmed"
            elif confirmed_appt == "UNSURE":
                pretty_date = ap.prettify_date(self.temp_appt_date["date"])
                msg = (
                    f"Sorry, I didn't catch your answer. Can you confirm that you'd like "
                    f"to schedule your appointment on {pretty_date} at "
                    f"{ap.format_appt_time(self.temp_appt_date['time'])}"
                    f"{self.temp_appt_date['ampm']}?"
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}
            elif confirmed_appt == "REJECT":
                if changed_dt:
                    # User said something about scheduling a different date/time
                    pretty_date = ap.prettify_date(self.temp_appt_date["date"])
                    msg = (
                        f"Okay, let's update that. To confirm, you'd like to schedule your "
                        f"appointment for {pretty_date} at "
                        f"{ap.format_appt_time(self.temp_appt_date['time'])}"
                        f"{self.temp_appt_date['ampm']}, is that correct?"
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    # stay in pending_confirmation with the new date/time
                    self.appt_state = "pending_confirmation"
                    return {"agent_message": msg, "end_call": False}
                else:
                    msg = (
                        "Sorry if I misheard you. Please try stating your date and time again in one "
                        "sentence or you may exit the scheduling process by telling me so."
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.temp_appt_date = ap.new_temp_appt_date()
                    self.appt_state = "scheduling_appt"
                    return {"agent_message": msg, "end_call": False}
            
        # 7. ---------- EXIT CURRENT PIPELINE ----------
        if self.appt_state in [
            "pending_confirmation",
            "scheduling_appt",
            "appt_reason",
            "awaiting_cancellation_date",
        ] or self.refill_state in ["drug_name", "confirm_drug_name"]:
            exit_appt_scheduling = classify_appt_context(user_input)
            
            if exit_appt_scheduling == "EXIT_APPT":
                
                # If user is currently scheduling an appointment and says they want to cancel instead
                if intent == "APPT_CANCEL" and self.appt_state not in ["appt_reason", "appt_confirmed"]:
                    self.appt_state = "cancelling_appt"

                # custom exit message for each pipeline
                if self.refill_state in ["drug_name", "confirm_drug_name"]:
                    msg = (
                        "Got it, we will stop the refill process. If you'd like help with anything else, "
                        "just ask! If you'd like to exit the call, say stop."
                    )
                elif self.appt_state in ["pending_confirmation", "scheduling_appt", "appt_reason"]:
                    msg = (
                        "Got it, we will stop the scheduling process. If you'd like help with anything else, "
                        "just ask! If you'd like to exit the call, say stop."
                    )
                elif self.appt_state in ["awaiting_cancellation_date", "cancelling_appt"]:
                    msg = (
                        "Got it, we will stop the cancellation process. If you'd like help with anything else, "
                        "just ask! If you'd like to exit the call, say stop."
                    )
                else:    
                    msg = (
                        "Got it, we will stop this process. If you'd like help with anything else, "
                        "just ask! If you'd like to exit the call, say stop."
                    )
                           
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.temp_appt_date = ap.new_temp_appt_date()
                self.appt_state = None
                self.availability_state = None
                self.reschedule_state = None
                self.refill_state = None
                return {"agent_message": msg, "end_call": False}
        
        # 8. ---------- RX REFILL CONFIRMATION BRANCHES ----------
        if self.refill_state == "confirm_drug_name":
            confirm_drug_name = classify_confirmation(user_input)

            if confirm_drug_name == "CONFIRM":
                refill_confirmed_msg = handle_refill_request(
                    self.patient.id, self.call.id, self.med
                )
                add_to_history(self.chat_history, "assistant", refill_confirmed_msg)
                log_turn(self.call.id, "assistant", refill_confirmed_msg)
                self.refill_state = None
                return {"agent_message": refill_confirmed_msg, "end_call": False}

            elif confirm_drug_name == "UNSURE":
                msg = f"Sorry, I didn't catch your answer. Would you like a refill for {self.med}?"
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}

            elif confirm_drug_name == "REJECT":
                msg = (
                    "Sorry if I misheard you. Please try saying the name of the "
                    "medication again, or if you'd like to exit the refill process, just say so!"
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.refill_state = "drug_name"
                return {"agent_message": msg, "end_call": False}

        # 9. ---------- ASK REASON ONCE APPT CONFIRMED ----------
        if not ap.missing_info_check(self.temp_appt_date) and self.appt_state == "appt_confirmed":
            msg = "Perfect! And what is the reason for your appointment?"
            add_to_history(self.chat_history, "assistant", msg)
            log_turn(self.call.id, "assistant", msg)
            self.appt_state = "appt_reason"
            return {"agent_message": msg, "end_call": False}

        if self.appt_state == "appt_reason":
            appt_reason = user_input
            msg = (
                "Got it! Your appointment has been registered into our system. "
                "If you'd like to make another appointment or request, just ask! "
                "If you'd like to end the call now, say stop."
            )
            add_to_history(self.chat_history, "assistant", msg)
            log_turn(self.call.id, "assistant", msg)

            # AI summary of reasoning for appointment
            appt_reason_summary = query_ollama(appt_reason, [{"role": "system", "content": reason_system_prompt}],
                                               model="llama3.1:8b")
            
            db_timestamp_format = ap.parts_to_local_dt(self.temp_appt_date)
            ap.book_appointment(self.call.patient_id, self.call.id, db_timestamp_format, duration_min=30, reason=appt_reason_summary)

            self.temp_appt_date = ap.new_temp_appt_date()
            self.appt_state = None
            self.availability_state = None
            self.reschedule_state = None
            return {"agent_message": msg, "end_call": False}

        # 10. ---------- RESCHEDULE ----------
        reschedule_prefix = None  # local flag for this turn only
        
        if intent == "APPT_RESCHEDULE":
            # create prefix for next message from agent in cancellation pipeline
            reschedule_prefix = "Okay, let's reschedule for you!"
            self.reschedule_state = "cancel_for_rescheduling"
            self.appt_state = "cancelling_appt" # sends user down to cancellation pipeline
        
        # 11. ---------- NEW APPOINTMENT ----------
        multidate_msg_prepend = None
        if intent == "APPT_NEW" or self.appt_state == "scheduling_appt":
            self.appt_state = "scheduling_appt"

            # Helper to prepend multi_date_msg once (for when user tries to schedule multiple dates in same prompt)
            def prepend_multidate_msg(text: str) -> str:
                nonlocal multidate_msg_prepend
                if multidate_msg_prepend:
                    combined = f"{multidate_msg_prepend} {text}"
                    multidate_msg_prepend = None  # make sure we don't reuse it later in this turn
                    return combined
                return text
            # make sure time is within hours of operation
            check_appt_timestamp = ap.check_time(self.temp_appt_date) # None if no conflicts
            if check_appt_timestamp:
                msg = check_appt_timestamp
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False} 

            blanks = ap.missing_info_check(self.temp_appt_date) # contains all keys with missing appt info
            # prettify date e.g. 2025-11-11 -> November 11th
            pretty_date = (
                ap.prettify_date(self.temp_appt_date["date"])
                if self.temp_appt_date["date"]
                else None
            )

            # multiple captured dates -> handle first only
            if results and ap.len_deduped_results(results) > 1 and results[0]["date"]:
                multidate_msg_prepend = f"Let's handle these one at a time starting with the appointment for {pretty_date}."
                while len(results) > 1:
                    results.pop(0)
                
            # missing date or time
            if None in blanks:
                msg = "What date and time would you like to schedule for?"
                msg = prepend_multidate_msg(msg)
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}

            # if date is missing
            if not self.temp_appt_date["date"]:
                msg = (
                    f"Please say the date that you would like to schedule your appointment for at "
                    f"{ap.format_appt_time(self.temp_appt_date['time'])}{self.temp_appt_date['ampm']}."
                )
                msg = prepend_multidate_msg(msg)
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}

            # date present, time missing: give availability
            if not self.temp_appt_date["time"]:
                if self.availability_state == "check_availability":
                    msg = f"Let me check our availability for {pretty_date}."
                    msg = prepend_multidate_msg(msg)
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)

                    day_appts_sys_prompt, available_appt_times = ap.check_appt_availability(
                        self.temp_appt_date["date"], ap.TIME_SLOTS
                    )

                    if not available_appt_times:
                        msg2 = (
                            f"Sorry, we are fully booked for {pretty_date}. Please try a different day."
                        )
                        add_to_history(self.chat_history, "assistant", msg2)
                        log_turn(self.call.id, "assistant", msg2)
                        return {"agent_message": msg + " " + msg2, "end_call": False}

                    # avoids agent reading every available slot on fully open day
                    if day_appts_sys_prompt == "full_availability_weekday":
                        msg2 = (
                            f"We have full availability on {pretty_date}. Please choose any "
                            "appointment time you'd like from 8:00am to 4:30pm, on the hour or half hour."
                        )
                        add_to_history(self.chat_history, "assistant", msg2)
                        log_turn(self.call.id, "assistant", msg2)
                        self.availability_state = None
                        return {"agent_message": msg + " " + msg2, "end_call": False}

                    if day_appts_sys_prompt == "full_availability_friday":
                        msg2 = (
                            f"We have full availability on {pretty_date}. Please choose any "
                            "appointment time you'd like from 8:00am to 3:30pm, on the hour or half hour."
                        )
                        add_to_history(self.chat_history, "assistant", msg2)
                        log_turn(self.call.id, "assistant", msg2)
                        self.availability_state = None
                        return {"agent_message": msg + " " + msg2, "end_call": False}

                    # partial availability: let LLM describe
                    add_to_history(self.chat_history, "system", day_appts_sys_prompt)
                    prompt_for_availability = (
                        f"Please give me the available times for {self.temp_appt_date['date']}"
                    )
                    availabilities_response = query_ollama(
                        prompt_for_availability, self.chat_history, self.llm_model
                    )
                    add_to_history(self.chat_history, "assistant", availabilities_response)
                    log_turn(self.call.id, "assistant", availabilities_response)

                    if len(available_appt_times) == 1: # if there's only one appt slot left
                        self.availability_state = "confirm_last_slot"
                        self.last_available_time = available_appt_times[0]
                        return {
                            "agent_message": msg + " " + availabilities_response,
                            "end_call": False,
                        }

                    self.availability_state = None
                    return {
                        "agent_message": msg + " " + availabilities_response,
                        "end_call": False,
                    }

            # date+time present -> confirm + check availability
            if not blanks:
                incorrect_time = ap.check_time(self.temp_appt_date)
                if incorrect_time:
                    msg = incorrect_time
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    return {"agent_message": msg, "end_call": False}

                _, available_appt_times = ap.check_appt_availability(
                    self.temp_appt_date["date"], ap.TIME_SLOTS
                )

                if not available_appt_times: # if day is completely booked
                    msg = f"Sorry, we are fully booked for {pretty_date}. Please try a different day."
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.temp_appt_date = ap.new_temp_appt_date()
                    return {"agent_message": msg, "end_call": False}

                if self.temp_appt_date["time"] not in available_appt_times: # if that time is booked
                    booked_time_msg = (
                        f"Sorry, {self.temp_appt_date['time']} is already booked for {pretty_date}."
                    )
                    add_to_history(self.chat_history, "assistant", booked_time_msg)
                    log_turn(self.call.id, "assistant", booked_time_msg)

                    nearest_slots = ap.nearest_available_slots(
                        ap.TIME_SLOTS, available_appt_times, self.temp_appt_date["time"]
                    )

                    if isinstance(nearest_slots, tuple):
                        self.last_available_time = nearest_slots[1]
                        self.availability_state = "confirm_last_slot"
                        msg = nearest_slots[0]
                    else:
                        self.appt_state = None # in case user says 'yes' or 'no' 
                        msg = f"{nearest_slots}"

                    return {"agent_message": booked_time_msg + " " + msg, "end_call": False}

                confirm_appt_msg = (
                    f"To confirm, you'd like to schedule your appointment for {pretty_date} at "
                    f"{ap.format_appt_time(self.temp_appt_date['time'])}"
                    f"{self.temp_appt_date['ampm']}, is that correct?"
                )
                confirm_appt_msg = prepend_multidate_msg(confirm_appt_msg)
                self.appt_state = "pending_confirmation"
                add_to_history(self.chat_history, "assistant", confirm_appt_msg)
                log_turn(self.call.id, "assistant", confirm_appt_msg)
                return {"agent_message": confirm_appt_msg, "end_call": False}

        # 12. ---------- CANCEL APPOINTMENT ----------
        if intent == "APPT_CANCEL" or self.appt_state == "cancelling_appt":
            self.appt_state = "cancelling_appt"
            patient_appts, patient_appt_dicts = ap.patient_existing_appts(self.patient.id)
            self.cancel_appt_id = None
            
            # Helper to prepend "Okay, let's reschedule..." once if we're in that pipeline
            def prepend_prefix(text: str) -> str:
                nonlocal reschedule_prefix
                if reschedule_prefix:
                    combined = f"{reschedule_prefix} {text}"
                    reschedule_prefix = None  # make sure we don't reuse it later in this turn
                    return combined
                return text
            
            if not patient_appts:
                msg = (
                    "Our database is showing that you do not have any scheduled appointments "
                    "at this time. If you would like to make a new one, just ask!"
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.appt_state = None
                return {"agent_message": msg, "end_call": False}
            
            # user gave date+time
            if self.temp_appt_date["date"] and self.temp_appt_date["time"]:
                
                self.pretty_cancel_date = (
                    f"{ap.prettify_date(self.temp_appt_date['date'])} at "
                    f"{self.temp_appt_date['time']}"
                )
                for appt in patient_appt_dicts:
                    if (
                        self.temp_appt_date["date"] == appt["date"]
                        and self.temp_appt_date["time"] == appt["time"]
                    ):
                        ask_msg = (
                            f"To confirm, you would like to cancel your appointment for "
                            f"{self.pretty_cancel_date}{appt['ampm']}."
                        )
                        ask_msg = prepend_prefix(ask_msg)
                        add_to_history(self.chat_history, "assistant", ask_msg)
                        log_turn(self.call.id, "assistant", ask_msg)
                        self.appt_state = "confirm_cancellation"
                        self.cancel_appt_id = appt["id"]
                        
                        return {"agent_message": ask_msg, "end_call": False}

                msg = (
                    f"{self.pretty_cancel_date} does not match up with any existing appointments for you "
                    "in our system. Please try repeating the date and time of the appointment "
                    "you would like to cancel."
                )
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.appt_state = "awaiting_cancellation_date"
                return {"agent_message": msg, "end_call": False}

            # user gave date only
            if self.temp_appt_date["date"] and not self.temp_appt_date["time"]:
                # checks for appts scheduled on that date with formatted time
                appts_for_day = [
                    ap.add_ampm(ap.format_appt_time(appt["time"]))
                    for appt in patient_appt_dicts
                    if self.temp_appt_date["date"] == appt["date"]
                ]

                if not appts_for_day:
                    msg = (
                        f"Our database is showing that you do not have any scheduled "
                        f"appointments for {ap.prettify_date(self.temp_appt_date['date'])}. "
                        "Please try a different date."
                    )
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.appt_state = "awaiting_cancellation_date"
                    return {"agent_message": msg, "end_call": False}

                if len(appts_for_day) == 1:
                    # find that appt object
                    for appt in patient_appt_dicts:
                        if (
                            appt["date"] == self.temp_appt_date["date"]
                            and appt["time"] == appts_for_day[0]
                        ):
                            self.pretty_cancel_date = (
                                f"{ap.prettify_date(self.temp_appt_date['date'])} at "
                                f"{appts_for_day[0]}"
                            )
                            ask_msg = (
                                f"You have one appointment for {self.pretty_cancel_date}"
                                f"{appt['ampm']}, would you like to cancel that?"
                            )
                            ask_msg = prepend_prefix(ask_msg)
                            add_to_history(self.chat_history, "assistant", ask_msg)
                            log_turn(self.call.id, "assistant", ask_msg)
                            self.appt_state = "confirm_cancellation"
                            self.cancel_appt_id = appt["id"]
                            return {"agent_message": ask_msg, "end_call": False}

                if len(appts_for_day) > 1:
                    msg = (
                        f"You have multiple appointment times for "
                        f"{ap.prettify_date(self.temp_appt_date['date'])}. "
                        f"Which one would you like to cancel, {", ".join(appts_for_day[0:-1])} "
                        f"or {appts_for_day[-1]}?"
                    )
                    msg = prepend_prefix(msg)
                    add_to_history(self.chat_history, "assistant", msg)
                    log_turn(self.call.id, "assistant", msg)
                    self.appt_state = "awaiting_cancellation_date"
                    return {"agent_message": msg, "end_call": False}

            # if patient has exactly 1 appt and user didn't specify date yet
            if len(patient_appt_dicts) == 1:
                appt = patient_appt_dicts[0]
                self.pretty_cancel_date = (
                    f"{ap.prettify_date(appt['date'])} at {appt['time']}"
                )
                msg = patient_appts  # string list from patient_existing_appts
                msg = prepend_prefix(msg)
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.appt_state = "confirm_cancellation"
                self.cancel_appt_id = appt["id"]
                return {"agent_message": msg, "end_call": False}

            # multiple appts, but no date/time specified yet
            msg = patient_appts
            msg = prepend_prefix(msg)
            add_to_history(self.chat_history, "assistant", msg)
            log_turn(self.call.id, "assistant", msg)
            self.appt_state = "awaiting_cancellation_date"
            return {"agent_message": msg, "end_call": False}

        # 13. ---------- RX REFILL ----------
        if intent == "RX_REFILL" and self.refill_state != "drug_name":
            # attempt to extract meidcation name
            med_candidate = match_medication(user_input) # uses regex and fuzzy matching
            
            # skips drug_name logic and goes straight to confirmation of drug name
            if med_candidate:
                self.refill_state = "confirm_drug_name"
                self.med = med_candidate
                
                msg = f"To confirm, you would like a refill for {med_candidate}, right?"
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}
            
            else: # ask user to name medication
                msg = "Please exclusively name the medication you would like to refill."
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                self.refill_state = "drug_name"
                return {"agent_message": msg, "end_call": False}

        if self.refill_state == "drug_name":
            med = match_medication(user_input)
            if not med: # inform user list of supported meds
                msg = (f"I'm sorry, I didn't catch the name of the medication." 
                    f" Please note that we currently only support {', '.join(MEDS[0:-1])} and {MEDS[-1]}."
                    f" Try exclusively naming the medication again if it's supported.")
                
                add_to_history(self.chat_history, "assistant", msg)
                log_turn(self.call.id, "assistant", msg)
                return {"agent_message": msg, "end_call": False}

            self.med = med
            msg = f"To confirm, you would like a refill for {med}?"
            add_to_history(self.chat_history, "assistant", msg)
            log_turn(self.call.id, "assistant", msg)
            self.refill_state = "confirm_drug_name"
            return {"agent_message": msg, "end_call": False}

        # 14. ---------- FALLBACK: LLM ANSWER ----------
        # Typically if intent == ADMIN_INFO or intent == OTHER and state machines are None
        response = query_ollama(user_input, self.chat_history, self.llm_model)
        add_to_history(self.chat_history, "assistant", response)
        log_turn(self.call.id, "assistant", response)
        return {"agent_message": response, "end_call": False}


# ---------- In-memory session store ----------

sessions: Dict[str, ClinAISession] = {}

# -------------------------------------------------------------------------
# API endpoints
# -------------------------------------------------------------------------

@app.post("/start_session", response_model=StartSessionResponse)
async def start_session(req: StartSessionRequest):
    """
    Start a ClinAI web session.

    - If only phone is provided: try to look up existing patient by phone.
    - If found -> use that patient.
    - If not found -> require full info (first_name, last_name, dob) and create via intake_patient.
    - If full info is provided from the start, just call intake_patient (it will create or update).
    """

    # ---------- Try returning-patient flow (phone only) ----------
    if not req.first_name and not req.last_name and not req.dob:
        patient = get_by_phone(req.phone)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No patient found with that phone number. "
                    "Please register by providing your name and date of birth."
                ),
            )
    # ---------- Registration flow ----------
    else:
        dob_val = None
        if req.dob:
            dob_val = date.fromisoformat(req.dob)

        patient = intake_patient(
            first_name=req.first_name,
            last_name=req.last_name,
            phone=req.phone,
            dob=dob_val,
        )

    # ---------- Start call + agent session ----------
    call = start_call(patient_id=patient.id, from_number=patient.phone)
    session = ClinAISession(patient, call)

    session_id = str(uuid.uuid4())
    sessions[session_id] = session

    messages = session.start()  # returns intro + welcome messages

    # ---------- Build intro+welcome audio ----------
    '''
    Messages from ClinAISession.start() look like:
    [
    {"role": "assistant", "content": intro_msg},
    {"role": "assistant", "content": welcome_msg},
    ]
    '''
    audio_buf = io.BytesIO()

    for idx, m in enumerate(messages):
        if m["role"] != "assistant":
            continue

        text = m["content"]
        # First assistant message = monitoring notice -> Roger
        # Second assistant message = greeting -> Ava
        if idx == 0:
            voice = EDGE_TTS_VOICE_INTRO
        else:
            voice = EDGE_TTS_VOICE

        try:
            chunk = await tts_to_mp3_bytes(text, voice)
            audio_buf.write(chunk)
        except Exception as e:
            print(f"[WARN] Failed to synthesize intro chunk {idx}: {e}")

    audio_bytes = audio_buf.getvalue()
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else None

    return StartSessionResponse(
        session_id=session_id,
        messages=messages,
        audio_b64=audio_b64,
    )

@app.post("/turn", response_model=TurnResponse)
async def turn(req: TurnRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Core ClinAI logic
    result = session.handle_turn(req.user_input)
    agent_message = result["agent_message"]
    end_call_flag = bool(result.get("end_call", False))

    # To check if escalated to human rep
    rep_mode = getattr(session, "escalated", False)

    # Split message read between Ava and William on escalation to representative
    audio_b64: Optional[str] = None
    try:
        if rep_mode and FAKE_REP_TRIGGER in agent_message:
            # Split into transfer text (Ava) + rep intro (William)
            before, sep, after = agent_message.partition(FAKE_REP_TRIGGER)
            transfer_text = before.strip()
            rep_text = (sep + " " + after).strip()

            combined_mp3 = b""

            # Ava reads the transfer message
            if transfer_text:
                ava_bytes = await tts_to_mp3_bytes(
                    transfer_text, voice=EDGE_TTS_VOICE
                )
                combined_mp3 += ava_bytes
            
            # William reads his intro
            william_bytes = await tts_to_mp3_bytes(
                rep_text, voice=EDGE_TTS_FAKE_REP_VOICE
            )
            combined_mp3 += william_bytes

            audio_b64 = base64.b64encode(combined_mp3).decode("ascii")

        else:
            # Normal case: single voice for the whole message
            voice = EDGE_TTS_FAKE_REP_VOICE if rep_mode else EDGE_TTS_VOICE
            mp3_bytes = await tts_to_mp3_bytes(agent_message, voice=voice)
            audio_b64 = base64.b64encode(mp3_bytes).decode("ascii")

    except Exception as e:
        print(f"[WARN] TTS failed: {e}")
        audio_b64 = None

    # End the call if needed
    if end_call_flag:
        session.end()
        sessions.pop(req.session_id, None)

    return TurnResponse(
        agent_message=agent_message,
        end_call=end_call_flag,
        audio_b64=audio_b64,
    )

@app.post("/voice_turn", response_model=TurnResponse)
async def voice_turn(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
):
    """
    Voice turn for browser clients:

    - Browser records audio as WebM/Opus
    - it converts to 16k mono WAV via ffmpeg
    - Run Whisper with same gating logic as transcriber.py
    - If text == "" -> "Sorry, I didn’t catch that clearly. Could you repeat?"
    - Otherwise send text into ClinAISession.handle_turn
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Convert WebM/Opus -> 16k mono WAV (Faster-Whisper not compatible with WebM/Opus)
    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, "input.webm")
        out_path = os.path.join(tmpdir, "input_16k.wav")

        # Save uploaded file
        with open(in_path, "wb") as f:
            f.write(await audio.read())

        # Call ffmpeg
        ffmpeg_cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", in_path,
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        "-acodec", "pcm_s16le",
        out_path,
    ]

        proc = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            print("[STT] ffmpeg stderr:", proc.stderr.decode(errors="ignore")[:300])
            raise HTTPException(
                status_code=500,
                detail="ffmpeg failed to convert audio",
            ) 

        # looser threshold for drug names
        min_conf = -2.0 if getattr(session, "refill_state", None) == "drug_name" else -0.70
        text = transcribe_file_with_gate(out_path, min_conf=min_conf)

    # -------- Handle silence / low-confidence --------
    
    # if confidence threshold not met
    if text == "[Inaudible Message]":
        pass # let the LLM handle it
    
    # if no speech is detected
    elif not text:
        patient = getattr(session, "patient", None)
        first_name = getattr(patient, "first_name", None)
        if first_name:
            agent_message = f"Are you still there, {first_name}?"
        else:
            agent_message = "Are you still there?"

        # Use Ava before escalation, William after escalation
        rep_mode = getattr(session, "escalated", False)
        
        # Simple Ava voice for presence check
        audio_b64 = None
        try:
            voice = EDGE_TTS_FAKE_REP_VOICE if rep_mode else EDGE_TTS_VOICE
            mp3_bytes = await tts_to_mp3_bytes(agent_message, voice)
            audio_b64 = base64.b64encode(mp3_bytes).decode("ascii")
        except Exception as e:
            print(f"[WARN] TTS failed for silence prompt: {e}")
            audio_b64 = None
        
        return TurnResponse(
            agent_message=agent_message,
            end_call=False,
            audio_b64=audio_b64,
            user_transcript=None,
        )

    # Normal voice → text turn
    result = session.handle_turn(text)
    agent_message = result["agent_message"]
    end_call_flag = bool(result.get("end_call", False))

    # Escalation state (fake human rep)
    rep_mode = getattr(session, "escalated", False)

    # TTS (same logic as /turn)
    audio_b64: Optional[str] = None
    try:
        '''If we are in rep mode and the message contains William's intro,
          split it so Ava speaks the transfer, William speaks the intro.'''
        if rep_mode and FAKE_REP_TRIGGER in agent_message:
            before, sep, after = agent_message.partition(FAKE_REP_TRIGGER)
            transfer_text = before.strip()
            rep_text = (sep + " " + after).strip()

            combined_mp3 = b""

            # Ava reads the transfer message
            if transfer_text:
                ava_bytes = await tts_to_mp3_bytes(
                    transfer_text, voice=EDGE_TTS_VOICE
                )
                combined_mp3 += ava_bytes

            # William reads his intro
            william_bytes = await tts_to_mp3_bytes(
                rep_text, voice=EDGE_TTS_FAKE_REP_VOICE
            )
            combined_mp3 += william_bytes

            audio_b64 = base64.b64encode(combined_mp3).decode("ascii")

        else:
            # Normal case: single voice for the whole message
            voice = EDGE_TTS_FAKE_REP_VOICE if rep_mode else EDGE_TTS_VOICE
            mp3_bytes = await tts_to_mp3_bytes(agent_message, voice=voice)
            audio_b64 = base64.b64encode(mp3_bytes).decode("ascii")

    except Exception as e:
        print(f"[WARN] TTS failed (voice_turn): {e}")
        audio_b64 = None

    # Note: we do NOT end the call here; that logic is identical to /turn
    # and handled via `end_call_flag`.
    if end_call_flag:
        session.end()
        sessions.pop(session_id, None)

    return TurnResponse(
        agent_message=agent_message,
        end_call=end_call_flag,
        audio_b64=audio_b64,
        user_transcript=text,
    )
