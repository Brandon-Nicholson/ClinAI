"""
main.py
"""

# Imports from modular voice pipeline
from app.ui.intake_form import run_intake_form
from app.services.call_service import start_call, end_call, set_intent, log_turn, was_resolved
from app.voice.synthesizer import stop_speaking, EdgeTTSPlayer
from app.voice.transcriber import start_microphone, listen_and_transcribe_whisper
from app.voice.llm import query_ollama, add_to_history, main_system_prompt, info_system_prompt, human_system_prompt
from faster_whisper import WhisperModel
from classifiers.intent_model.intent_classifier import classify_intent
from classifiers.appt_context_model.appt_context_classifier import classify_appt_context
from classifiers.appt_confirmation_model.appt_confirmation_classifier import classify_appt_confirmation
from datetime import date
import app.services.appointments as ap
import time
import re
import json

# ---------------------------
# EdgeTTS main loop
# ---------------------------
def main_edge():
    # submit patient info before talking to agent
    patient = run_intake_form()
    if not patient:
        print("Call aborted: no patient submitted.")
        return
    
    print(f"Starting ClinAI agent for patient: {patient.first_name} {patient.last_name}")
    
    # Load Whisper model for STT (speech-to-text)
    print("Loading Whisper model...")
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

    # Store running conversation so the LLM has context
    chat_history = [{"role": "system", "content": main_system_prompt},
                    {"role": "system", "content": info_system_prompt}] # pre-load system prompts to context window
    llm_model = "llama3.1:8b"

    # Initialize EdgeTTS with chosen voice and rate
    # intro message
    tts_intro = EdgeTTSPlayer(rate="+25%", voice="en-US-RogerNeural")
    # main assistant
    tts = EdgeTTSPlayer(rate="+15%", voice="en-US-AriaNeural")
    # fake human representative
    tts_fake_rep = EdgeTTSPlayer(rate="+15%", voice="en-AU-WilliamMultilingualNeural")

    # start a call record
    call = start_call(patient.id, patient.phone)
    
    # initialize list of patient intents
    patient_intents = []
    
    # intro messages
    intro_msg = "Your call may be monitored or recorded for quality assurance. Exclusively say 'stop'.. or 'quit'.. at any time to exit the conversation."
    tts_intro.speak_and_wait(intro_msg)
    add_to_history(chat_history, "system", intro_msg) # adds default responses to chat_history
    welcome_msg = f"Hi {patient.first_name}... I'm Ava. How can I assist you today?"
    tts.speak_and_wait(welcome_msg)
    add_to_history(chat_history, "system", welcome_msg)
    log_turn(call.id, "assistant", welcome_msg)

    # count number of times max wait time for input was exceeded
    max_wait_counter = 0
    
    # true if call was escalated to human
    escalated = False
    
    # initially set LLM response to an empty string
    response = "" # needs to be defined before listen_and_transcribe_whisper is called
    
    # placeholder dict for appt dates
    temp_appt_date = ap.new_temp_appt_date() # resets after appointments are updated in db
    # current state of appt handling
    appt_state = None
    
    # keeps convo loop going if True
    loop_convo = True
    try:
        while True:
            # before listening, cut off any ongoing speech
            tts.stop()

            # Start microphone stream
            q, stream = start_microphone()
            user_input = listen_and_transcribe_whisper(whisper_model, q, response)
            # Stop and close mic stream after transcribing
            stream.stop(); stream.close()

            # add 1 to max_wait_counter if set wait time without speaking is exceeded
            if user_input is None:
                max_wait_counter+=1
                
                # only allow 1 max_wait_exceeded during patient feedback
                if not loop_convo:
                    tts.speak_and_wait("Goodbye!")                    
                    resolved = None
                    log_turn(call.id, "assistant", "Goodbye!")
                    break
                
                # end the call if patient goes too long without speaking
                elif max_wait_counter > 2:
                    max_wait_msg = "Looks like we got disconnected. I’ll end the call for now, but you can always reach us again. Goodbye"
                    tts.speak_and_wait(max_wait_msg)
                    resolved = None
                    log_turn(call.id, "assistant", max_wait_msg)
                    break
                
                # try to get patient's attention if they're not speaking
                check_presence = f"Are you still there, {patient.first_name}?"
                tts.speak_and_wait(check_presence)
                add_to_history(chat_history, "assistant", check_presence)
                log_turn(call.id, "assistant", check_presence)
                continue
            
            # skip empties or junk (no letters/numbers)
            if not user_input or not re.search(r"[A-Za-z0-9]", user_input):
                repeat_msg = "Sorry, I didn’t catch that clearly. Could you repeat?"
                tts.speak_and_wait(repeat_msg)
                add_to_history(chat_history, "assistant", repeat_msg)
                log_turn(call.id, "assistant", repeat_msg)
                continue
            else:
                # revert counter back to 0 if utterance
                max_wait_counter = 0

            print(f"You: {user_input}")
            
            # get bool from was_resolved when convo ends
            if not loop_convo and user_input:
                resolved = was_resolved(user_input)
                goodbye_msg = "Your feedback is appreciated, Goodbye!"
                tts.speak_and_wait(goodbye_msg)
                log_turn(call.id, "assistant", goodbye_msg)
                break
            
            
            if user_input.lower().strip() in ["exit", "quit", "stop", "goodbye", "good bye", 
                                              "exit.", "quit.", "stop.", "goodbye.", "good bye.",
                                              "exit!", "quit!", "stop!", "goodbye!", "good bye!"]:
                print("Goodbye!")
                
                # ask if query was resolved
                feedback_msg = f"The conversation has ended. Was your query resolved today, {patient.first_name}?"
                tts.speak_and_wait(feedback_msg)
                tts.stop()
                loop_convo = False
                continue
            # log user input -> db
            log_turn(call.id, "user", user_input)
            
            # classify user intent unless appt scheduling is in process
            intent = classify_intent(user_input, patient_intents)
            # print(intent)
            # perform next action based on intent
            print(appt_state)
            print("Thinking...")
            
            # 1. Check for escalation to representative
            if intent == "HUMAN_AGENT" and not escalated:
                escalated = True
                
                escalation_msg = "Please hold while I transfer you to a human."
                tts.speak(escalation_msg)
                add_to_history(chat_history, "assistant", escalation_msg)
                time.sleep(8)
                log_turn(call.id, "assistant", escalation_msg)
                
                # change main assistant voice to fake human rep voice
                tts = tts_fake_rep
                
                # remove old system prompt from context window
                chat_history.pop(0)
                
                # add new system prompt
                add_to_history(chat_history, "system", human_system_prompt)
                
                # introduce fake rep
                fake_rep_msg = "Hi, this is William with Sunrise Family Medicine. How can I help you today?"
                tts.speak_and_wait(fake_rep_msg)
                add_to_history(chat_history, "assistant", fake_rep_msg)
                log_turn(call.id, "assistant", fake_rep_msg)
                
                # reset appt date holder
                temp_appt_date = ap.new_temp_appt_date()
                # reset appt_state back to None
                appt_state = None
                continue
            
            # 2. Check if user needs admin info
            if intent == "ADMIN_INFO":
                # get LLM query help
                response = query_ollama(user_input, chat_history, llm_model)
                tts.speak_and_wait(response)
                log_turn(call.id, "assistant", response)
                # set appt_state back to in_progress if currently pending_confirmation
                if appt_state == "pending_confirmation":
                    appt_state = "None"
                    temp_appt_date = ap.new_temp_appt_date() # reset date holder
                    print(appt_state)
                continue
            
            # classifier detects if user wants to exit appointment scheduling pipeline
            if appt_state == "pending_confirmation" or appt_state == "in_progress":
                exit_appt_scheduling = classify_appt_context(user_input)
                # exit pipeline if user implies they no longer want to schedule appt
                if exit_appt_scheduling == "EXIT_APPT":
                    exit_appt_pipeline_msg = "Got it. If you'd like help with anything else, just ask! If you'd like to exit the call, say stop."
                    tts.speak_and_wait(exit_appt_pipeline_msg)
                    log_turn(call.id, "assistant", exit_appt_pipeline_msg)
                    # reset appt variables
                    temp_appt_date = ap.new_temp_appt_date()
                    appt_state = None
                    continue
                
            # schedule appointment if user makes appt date and confirms it
            if not ap.missing_info_check(temp_appt_date) and appt_state == "pending_confirmation":
                confirmed_appt = classify_appt_confirmation(user_input)
                # set appt_state to confirmed if confirmed
                if confirmed_appt == "CONFIRM":
                    appt_state = "appt_confirmed"
                # Ask user to try again if confirmation denied
                elif confirmed_appt == "REJECT":
                    appt_denied_msg = "Sorry if I misheard you. Please try stating your date and time again in one sentence or you may exit the scheduling process by telling me so."
                    tts.speak_and_wait(appt_denied_msg)
                    log_turn(call.id, "assistant", appt_denied_msg)
                    # reset appt date holder
                    temp_appt_date = ap.new_temp_appt_date()
                    # switch appt_state to in_progress
                    appt_state = "in_progress"
                    continue
                # Ask user to confirm again if unsure
                elif confirmed_appt == "UNSURE":
                    unsure_msg = f"Sorry, I didn't catch your answer. Can you confirm that you'd like to schedule your appointment on {pretty_date} at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}?"
                    tts.speak_and_wait(unsure_msg)
                    log_turn(call.id, "assistant", unsure_msg)
                    continue
                
            # check if appt info is complete and appt is confirmed by user
            if not ap.missing_info_check(temp_appt_date) and appt_state == "appt_confirmed":
                appt_confirmation_msg = "Perfect, your appointment has been registered into our system. If you'd like to make another appointment or request, just ask! If you'd like to end the call now, say stop."
                tts.speak_and_wait(appt_confirmation_msg)
                add_to_history(chat_history, "assistant", appt_confirmation_msg)
                log_turn(call.id, "assistant", appt_confirmation_msg)
                
                # update db
                
                # reset appt date holder after appt has been made
                temp_appt_date = ap.new_temp_appt_date()
                # reset appt_state back to None
                appt_state = None
                continue
            
            # 3. Check for new appointment
            if intent == "APPT_NEW" or appt_state == "in_progress":
                appt_state = "in_progress"
                formatted_input = ap.format_prompt_time(user_input) # format time e.g. "9:00am"
                results = ap.extract_schedule_json(formatted_input) # regex date/time extractor
                
                if results:
                    # update global placeholder dict for appt date using first captured appt date (results[-1])
                    temp_appt_date = ap.update_results(results[-1], temp_appt_date)
                    temp_appt_date = ap.ampm_mislabel_fix(temp_appt_date) # fix potentially mislabeled am/pm
                # return a list of any missing info
                blanks = ap.missing_info_check(temp_appt_date)
                
                # format date to be read by voice using first date captured
                if temp_appt_date['date']:
                    d = date.fromisoformat(temp_appt_date['date'])   # YYYY-MM-DD
                    pretty_date = f"{d.strftime('%B')} {ap.ordinal(d.day)}"
                    
                # if more than one appt date was captured
                if ap.len_deduped_results(results) > 1 and results[0]['date']:
                        
                    # remove any extra appt requests to only handle first
                    while len(results) > 1:
                        results.pop(0)
                    
                    # inform user that they will schedule appointments one at a time
                    multiple_dates_msg = f"Let's handle these one at a time starting with the appointment for {pretty_date}."    
                    tts.speak_and_wait(multiple_dates_msg)
                    add_to_history(chat_history, "assistant", multiple_dates_msg)
                    log_turn(call.id, "assistant", multiple_dates_msg)
                    
                # ask for date and time if no appt info has been given
                if None in blanks:
                    ask_datetime_msg = "What date and time would you like to schedule for?"
                    tts.speak_and_wait(ask_datetime_msg)
                    add_to_history(chat_history, "assistant", ask_datetime_msg)
                    log_turn(call.id, "assistant", ask_datetime_msg)
                    continue
                
                # if only date is missing
                elif not temp_appt_date['date']:
                    missing_date_msg = f"Please say the date that you would like to schedule your appointment for at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}."
                    tts.speak_and_wait(missing_date_msg)
                    add_to_history(chat_history, "assistant", missing_date_msg)
                    log_turn(call.id, "assistant", missing_date_msg)
                    continue
                
                # if only time is missing    
                elif not temp_appt_date['time']:
                    print(temp_appt_date)
                    missing_time_msg = f"Please state the time that you would like to schedule your appointment for on {pretty_date}."
                    tts.speak_and_wait(missing_time_msg)
                    add_to_history(chat_history, "assistant", missing_time_msg)
                    log_turn(call.id, "assistant", missing_time_msg)
                    continue
                
                # ask for confirmation once appt info is complete
                elif not blanks:
                    incorrect_time = ap.check_time(temp_appt_date['time'], temp_appt_date['ampm'], temp_appt_date['date'])
                    if incorrect_time:
                        incorrect_time_msg = incorrect_time
                        tts.speak_and_wait(incorrect_time_msg)
                        add_to_history(chat_history, "assistant", incorrect_time_msg)
                        log_turn(call.id, "assistant", incorrect_time_msg)
                        continue
                        
                    if not incorrect_time:
                        confirm_appt_msg = f"To confirm, you'd like to schedule your appointment for {pretty_date} at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}, is that correct?"
                        appt_state = "pending_confirmation"
                        tts.speak_and_wait(confirm_appt_msg)
                        add_to_history(chat_history, "assistant", confirm_appt_msg)
                        log_turn(call.id, "assistant", confirm_appt_msg)
                        continue
                
            # get LLM query
            response = query_ollama(user_input, chat_history, llm_model)
            print(f"Agent: {response}")
            
            # log LLM output -> db
            log_turn(call.id, "assistant", response)

            # This plays asynchronously while loop keeps running
            tts.speak(response)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:

        tts.stop()
        
        # update db with intent
        db_intents = json.dumps(patient_intents)
        set_intent(call.id, db_intents)
        
        end_call(call.id, resolved=resolved, escalated=False, notes="blank")
        
if __name__ == "__main__":
    main_edge()