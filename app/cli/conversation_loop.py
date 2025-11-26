"""
app/cli/conversation_loop.py
"""

# Imports from modular voice pipeline
from app.ui.intake_form import run_intake_form
from app.services.call_service import start_call, end_call, set_intent, log_turn, was_resolved, call_notes
from app.services.rx_refills import match_medication, handle_refill_request
from app.voice.synthesizer import stop_speaking, EdgeTTSPlayer
from app.voice.transcriber import start_microphone, listen_and_transcribe_whisper
from app.voice.llm import query_ollama, add_to_history, main_system_prompt, info_system_prompt, human_system_prompt, reason_system_prompt
from faster_whisper import WhisperModel
from classifiers.intent_model.intent_classifier import classify_intent
from classifiers.appt_context_model.appt_context_classifier import classify_appt_context
from classifiers.confirmation_model.confirmation_classifier import classify_confirmation
from datetime import date
import app.services.appointments as ap
import time
import json

# ---------------------------
# EdgeTTS main loop
# ---------------------------
def main_edge():
    _sch = ap.start_scheduler() # update status of appts that already happened
    # submit patient info before talking to agent
    patient = run_intake_form()
    if not patient:
        print("Call aborted: no patient submitted.")
        return
    
    print(f"Starting ClinAI agent for patient: {patient.first_name} {patient.last_name}")
    
    # Load Whisper model for STT (speech-to-text)
    print("Loading Whisper model...")
    whisper_model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    # Store running conversation so the LLM has context
    chat_history = [{"role": "system", "content": main_system_prompt},
                    {"role": "system", "content": info_system_prompt}] # pre-load system prompts to context window
    llm_model = "llama3.1:8b"

    # Initialize EdgeTTS with chosen voice and rate
    # intro message
    tts_intro = EdgeTTSPlayer(rate="+25%", voice="en-US-RogerNeural")
    # main assistant
    tts = EdgeTTSPlayer(rate="+15%", voice="en-US-AvaNeural")
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
    
    # true, false when user asked for feedback at end of call
    resolved = False # False by default
    
    # initially set LLM response to an empty string
    response = "" # needs to be defined before listen_and_transcribe_whisper is called
    
    # placeholder dict for appt dates
    temp_appt_date = ap.new_temp_appt_date() # resets after appointments are updated in db
    # current state of appt handling
    appt_state = None
    reschedule_state = None
    availability_state = None
    refill_state = None
    # keeps convo loop going if True
    loop_convo = True
    try:
        while True:
            
# --------------------- START MICROPHONE & TRANSCRIBE AUDIO ---------------------            
            
            # before listening, cut off any ongoing speech
            tts.stop()

            # Start microphone stream
            q, stream = start_microphone()
            # set confidence threshold much lower when a drug name is being transcribed
            if refill_state == "drug_name":
                user_input = listen_and_transcribe_whisper(whisper_model, q, response, min_conf=-2.0)
            else:
                user_input = listen_and_transcribe_whisper(whisper_model, q, response)
            
            print(f"[DEBUG] user_input={user_input!r}")
            # Stop and close mic stream after transcribing
            stream.stop(); stream.close()

# --------------------- HANDLE LACK OF INPUT FROM USER ---------------------

            # add 1 to max_wait_counter if set wait time without speaking is exceeded
            if user_input is None:
                max_wait_counter+=1
                
                # only allow 1 max_wait_exceeded during patient feedback
                if not loop_convo:
                    tts.speak_and_wait("Goodbye!")                    
                    resolved = None
                    add_to_history(chat_history, "assistant", "Goodbye!")
                    log_turn(call.id, "assistant", "Goodbye!")
                    break
                
                # end the call if patient goes too long without speaking
                elif max_wait_counter > 2:
                    max_wait_msg = "Looks like we got disconnected. I’ll end the call for now, but you can always reach us again. Goodbye"
                    tts.speak_and_wait(max_wait_msg)
                    resolved = None
                    add_to_history(chat_history, "assistant", max_wait_msg)
                    log_turn(call.id, "assistant", max_wait_msg)
                    break
                
                # try to get patient's attention if they're not speaking
                check_presence = f"Are you still there, {patient.first_name}?"
                tts.speak_and_wait(check_presence)
                add_to_history(chat_history, "assistant", check_presence)
                log_turn(call.id, "assistant", check_presence)
                continue

# --------------------- HANDLE UNINTELLIGIBLE AUDIO FROM USER ---------------------
            
            # skip empties
            if not user_input:
                repeat_msg = "Sorry, I didn’t catch that clearly. Could you repeat?"
                tts.speak_and_wait(repeat_msg)
                add_to_history(chat_history, "assistant", repeat_msg)
                log_turn(call.id, "assistant", repeat_msg)
                continue
            else:
                # revert counter back to 0 if user speaks
                max_wait_counter = 0

# --------------------- PRINT USER INPUT ---------------------

            print(f"You: {user_input}")

# --------------------- OFFICIALLY END CONVO AFTER USER PROVIDES FEEDBACK ---------------------
            
            # get bool from was_resolved when convo ends
            if not loop_convo and user_input:
                resolved = was_resolved(user_input)
                goodbye_msg = "Your feedback is appreciated, Goodbye!"
                tts.speak_and_wait(goodbye_msg)
                add_to_history(chat_history, "assistant", goodbye_msg)
                log_turn(call.id, "assistant", goodbye_msg)
                break

# --------------------- USER WANTS TO END THE CALL ---------------------            
            
            if user_input.lower().strip() in ["exit", "quit", "stop", "goodbye", "good bye", 
                                              "exit.", "quit.", "stop.", "goodbye.", "good bye.",
                                              "exit!", "quit!", "stop!", "goodbye!", "good bye!",
                                              "up", "up.","up!", "top", "top.", "top!"]: # up & top commonly mistaken as 'stop' by transcriber
                print("Goodbye!")
                
                # ask if query was resolved
                feedback_msg = f"The conversation has ended. Was your query resolved today, {patient.first_name}?"
                tts.speak_and_wait(feedback_msg)
                add_to_history(chat_history, "assistant", feedback_msg)
                log_turn(call.id, "assistant", feedback_msg)
                tts.stop()
                loop_convo = False # assign loop_convo -> false indicating there will only be one more input from user 
                continue
            # log user input -> db
            log_turn(call.id, "user", user_input)

# --------------------- INTENT CLASSIFIER DETECTS INTENT ---------------------
           
            # classify user intent unless appt scheduling is in process
            intent = classify_intent(user_input, patient_intents)
                
            # perform next action based on intent
            print(f"Prompt Intent: {intent}")
            print(f"Appt State: {appt_state}")
            print("Thinking...")
            
# --------------------- USER WANTS HUMAN ESCALATION ---------------------

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
                # reset availability_state
                availability_state = None
                # reset reschedule_state
                reschedule_state = None
                # reset refill_state
                refill_state = None
                continue

# --------------------- USER WANTS ADMIN INFO ---------------------       
     
            # 2. Check if user needs admin info
            if intent == "ADMIN_INFO":
                # get LLM query help
                response = query_ollama(user_input, chat_history, llm_model)
                tts.speak_and_wait(response)
                log_turn(call.id, "assistant", response)
                # set appt_state back to scheduling_appt if currently pending_confirmation
                if appt_state == "pending_confirmation":
                    appt_state = "None"
                    temp_appt_date = ap.new_temp_appt_date() # reset date holder
                    print(appt_state)
                continue
            
# --------------------- HELPERS TO AVOID INTENT CONFLICTS ---------------------
            
            # avoid conflict bewteen scheduling and cancelling appointments
            if appt_state == "awaiting_cancellation_date":
                intent = "APPT_CANCEL"
                
            # avoid conflict between rx refills and appointment actions
            if refill_state == "drug_name":
                intent = "RX_REFILL"
                
# --------------------- USER CONFIRMS OR REJECTS RX REFILL ---------------------

            # classification of user response on rx refill for drug name transcribed by agent
            if refill_state == "confirm_drug_name":
                confirm_drug_name = classify_confirmation(user_input)
                
                if confirm_drug_name == "CONFIRM":
                    refill_confirmed_msg = handle_refill_request(patient.id, call.id, med)
                    tts.speak_and_wait(refill_confirmed_msg)
                    add_to_history(chat_history, "assistant", refill_confirmed_msg)
                    log_turn(call.id, "assistant", refill_confirmed_msg)
                    refill_state = None
                    continue
                
                elif confirm_drug_name == "UNSURE":
                    confirm_refill_unsure_msg = f"Sorry, I didn't catch your answer. Would you like a refill for {med}?"
                    tts.speak_and_wait(confirm_refill_unsure_msg)
                    add_to_history(chat_history, "assistant", confirm_refill_unsure_msg)
                    log_turn(call.id, "assistant", confirm_refill_unsure_msg)
                    continue
                
                elif confirm_drug_name == "REJECT":
                    rejected_drug_refill_msg = "Sorry if I misheard you. Please try saying the name of the medication again, or if you'd like to exit the refill process, just say so!"
                    tts.speak_and_wait(rejected_drug_refill_msg)
                    add_to_history(chat_history, "assistant", rejected_drug_refill_msg)
                    log_turn(call.id, "assistant", rejected_drug_refill_msg)
                    refill_state = "drug_name"
                    continue
                    
# --------------------- USER CONFIRMS OR REJECTS APPOINTMENT CANCELLATION ---------------------

            # if user is being asked to confirm cancellation for booked appointment
            if appt_state == "confirm_cancellation":
                confirm_appt_cancellation = classify_confirmation(user_input)         
                
                if confirm_appt_cancellation == "CONFIRM":
                    # change status of appt to cancelled in db
                    cancel_appt = ap.cancel_appointment(cancel_appt_id) # returns True
                    
                    # if user is in the rescheduling process
                    if reschedule_state == "cancel_for_rescheduling":
                        confirm_appt_cancellation_msg = "Your appointment has been cancelled. Please state a date and time for your new appointment."
                        tts.speak_and_wait(confirm_appt_cancellation_msg)
                        add_to_history(chat_history, "assistant", confirm_appt_cancellation_msg)
                        log_turn(call.id, "assistant", confirm_appt_cancellation_msg)
                        # reset appt date holder
                        temp_appt_date = ap.new_temp_appt_date()
                        # set appt state to scheduling_appt to put user through scheduling pipeline
                        appt_state = "scheduling_appt"
                        continue
                        
                    confirm_appt_cancellation_msg = "Your appointment has been cancelled. If you'd like to make another appointment or request, just ask! If you'd like to end the call now, say stop."
                    tts.speak_and_wait(confirm_appt_cancellation_msg)
                    add_to_history(chat_history, "assistant", confirm_appt_cancellation_msg)
                    log_turn(call.id, "assistant", confirm_appt_cancellation_msg)
                    # reset all states
                    # reset appt date holder after appt has been made
                    temp_appt_date = ap.new_temp_appt_date()
                    # reset appt_state
                    appt_state = None
                    # reset availability_state
                    availability_state = None
                    continue
                
                # Ask user to confirm again if unsure
                elif confirm_appt_cancellation == "UNSURE":
                    cancel_appt_unsure_msg = f"Sorry, I didn't catch your answer. Would you still like to cancel your appointment for {pretty_cancel_date}" # asks if they want to cancel again
                    tts.speak_and_wait(cancel_appt_unsure_msg)
                    add_to_history(chat_history, "assistant", cancel_appt_unsure_msg)
                    log_turn(call.id, "assistant", cancel_appt_unsure_msg)
                    continue
                
                # if user rejects recommended last appointment time
                elif confirm_appt_cancellation == "REJECT":
                    # ask for another day
                    cancel_appt_denied_msg = "No problem, we won't cancel that appointment. Let me know if you need anything else or say 'stop' to end the call."
                    tts.speak_and_wait(cancel_appt_denied_msg)
                    add_to_history(chat_history, "assistant", cancel_appt_denied_msg)
                    log_turn(call.id, "assistant", cancel_appt_denied_msg)
                    # reset all states
                     # reset appt date holder after appt has been made
                    temp_appt_date = ap.new_temp_appt_date()
                    # set appt_state to still scheduling_appt
                    appt_state = None
                    # reset availability_state
                    availability_state = None
                    # reset reschedule_state
                    reschedule_state = None
                    continue

# --------------------- USER ACCEPTS OR REJECTS LAST AVAILABLE APPOINTMENT TIME ---------------------
                
            # if user is being asked to confirm the last available appointment on their desired appt date
            if availability_state == "confirm_last_slot":
                confirm_last_appt_time = classify_confirmation(user_input)
                
                if confirm_last_appt_time == "CONFIRM":
                    # update temp_appt_date time
                    temp_appt_date['time'] = last_available_time
                    temp_appt_date = ap.ampm_mislabel_fix(temp_appt_date) # fix potentially mislabeled am/pm
                    # update appt_state
                    appt_state = "appt_confirmed" # continues to asking patient for appt reason
                    # reset availability_state
                    availability_state = None
                
                # Ask user to confirm again if unsure
                elif confirm_last_appt_time == "UNSURE":
                    last_appt_unsure_msg = f"Sorry, I didn't catch your answer. Please confirm, does {last_available_time} work for you?"
                    tts.speak_and_wait(last_appt_unsure_msg)
                    add_to_history(chat_history, "assistant", last_appt_unsure_msg)
                    log_turn(call.id, "assistant", last_appt_unsure_msg)
                    continue
                
                # if user rejects recommended last appointment time
                elif confirm_last_appt_time == "REJECT":
                    # ask for another day
                    last_appt_denied_msg = "Please state another day you would like to schedule your appointment for."
                    tts.speak_and_wait(last_appt_denied_msg)
                    add_to_history(chat_history, "assistant", last_appt_denied_msg)
                    log_turn(call.id, "assistant", last_appt_denied_msg)
                    
                     # reset appt date holder after appt has been made
                    temp_appt_date = ap.new_temp_appt_date()
                    # set appt_state to still scheduling_appt
                    appt_state = "scheduling_appt"
                    # reset availability_state
                    availability_state = None
                    continue

# --------------------- CONFIRMATION CLASSIFIER DETECTS IF USER WANTS TO CONFIRM OR REJECT APPOINTMENT SLOT ---------------------
                
            # detect if user wants to confirm or reject appointment date/time
            if not ap.missing_info_check(temp_appt_date) and appt_state == "pending_confirmation":
                confirmed_appt = classify_confirmation(user_input)
                # set appt_state to confirmed if confirmed
                if confirmed_appt == "CONFIRM":
                    appt_state = "appt_confirmed" # continues to next step: asking reason for appt
                    
                # Ask user to confirm again if unsure
                elif confirmed_appt == "UNSURE":
                    unsure_msg = f"Sorry, I didn't catch your answer. Can you confirm that you'd like to schedule your appointment on {pretty_date} at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}?"
                    tts.speak_and_wait(unsure_msg)
                    add_to_history(chat_history, "assistant", unsure_msg)
                    log_turn(call.id, "assistant", unsure_msg)
                    continue
                
                # Ask user to try again if confirmation denied
                elif confirmed_appt == "REJECT":
                    appt_denied_msg = "Sorry if I misheard you. Please try stating your date and time again in one sentence or you may exit the scheduling process by telling me so."
                    tts.speak_and_wait(appt_denied_msg)
                    add_to_history(chat_history, "assistant", appt_denied_msg)
                    log_turn(call.id, "assistant", appt_denied_msg)
                    # reset appt date holder
                    temp_appt_date = ap.new_temp_appt_date()
                    # switch appt_state to scheduling_appt
                    appt_state = "scheduling_appt"
                    continue

# --------------------- CONTEXT CLASSIFIER DETECTS USER DESIRE TO EXIT CURRENT PROCESS/PIPELINE ---------------------
                    
            # classifier detects if user wants to exit appointment pipeline
            if appt_state in ["pending_confirmation", "scheduling_appt", "appt_reason", "awaiting_cancellation_date"] or refill_state in ["drug_name", "confirm_drug_name"]:
                exit_appt_scheduling = classify_appt_context(user_input)
                # if user intended to cancel an appt instead
                if intent == "APPT_CANCEL":
                    appt_state = "cancelling_appt"
                    pass
                # exit pipeline if user implies they no longer want to schedule appt
                if exit_appt_scheduling == "EXIT_APPT":
                    exit_appt_pipeline_msg = "Got it, we will stop this process. If you'd like help with anything else, just ask! If you'd like to exit the call, say stop."
                    tts.speak_and_wait(exit_appt_pipeline_msg)
                    add_to_history(chat_history, "assistant", exit_appt_pipeline_msg)
                    log_turn(call.id, "assistant", exit_appt_pipeline_msg)
                    # reset global variables
                    temp_appt_date = ap.new_temp_appt_date()
                    appt_state = None
                    availability_state = None
                    reschedule_state = None
                    refill_state = None
                    continue

# --------------------- USER ASKED REASON FOR APPOINTMENT ONCE CONFIRMED ---------------------
            
            # ask reason for appt once date/time is confirmed
            if not ap.missing_info_check(temp_appt_date) and appt_state == "appt_confirmed":
                appt_reason_msg = "Perfect! And what is the reason for your appointment?"
                tts.speak_and_wait(appt_reason_msg)
                add_to_history(chat_history, "assistant", appt_reason_msg)
                log_turn(call.id, "assistant", appt_reason_msg)
                # update appt_state
                appt_state = "appt_reason"
                continue

# --------------------- UPDATE THE DATABASE WITH NEW APPOINTMENT AFTER REASON IS GIVEN ---------------------
                
            # update db with all appt info once appt reason is given
            if appt_state == "appt_reason":
                # store reason for appt in variable
                appt_reason = user_input
                appt_confirmation_msg = "Got it! Your appointment has been registered into our system. If you'd like to make another appointment or request, just ask! If you'd like to end the call now, say stop."
                tts.speak_and_wait(appt_confirmation_msg)
                add_to_history(chat_history, "assistant", appt_confirmation_msg)
                log_turn(call.id, "assistant", appt_confirmation_msg)
                
                # AI summary of reasoning
                appt_reason_summary = query_ollama(appt_reason, [{"role": "system", "content": reason_system_prompt}], model="llama3.1:8b")
                
                # update db
                db_timestamp_format = ap.parts_to_local_dt(temp_appt_date) # convert dict to timestamp format for db
                ap.book_appointment(call.patient_id, call.id, db_timestamp_format, duration_min=30, reason=appt_reason_summary)
                # reset globals
                # reset appt date holder after appt has been made
                temp_appt_date = ap.new_temp_appt_date()
                # reset appt_state back to None
                appt_state = None
                # reset avaialbility_state back to None
                availability_state = None
                # reset reschedule_state back to None
                reschedule_state = None
                continue
            
# --------------------- RUN PROMPT THROUGH REGEX DATE/TIME EXTRACTOR ---------------------            
            
            # extract date/time from prompt and update placeholder appt variable
            formatted_input = ap.format_prompt_time(user_input) # format time within e.g. "9:00am"
            results = ap.extract_schedule_json(formatted_input) # regex date/time extractor
                
            if results:
                # Allow time availability check when new date is given
                if results[0]['date'] != temp_appt_date['date']:
                        availability_state = "check_availability"
                    
                # update global placeholder dict for appt date using first captured appt date (results[-1])
                temp_appt_date = ap.update_results(results[-1], temp_appt_date)
                temp_appt_date = ap.ampm_mislabel_fix(temp_appt_date) # fix potentially mislabeled am/pm
                print(temp_appt_date)

# --------------------- FIX FOR EDGE CASE (Extractor always extracts 01:00pm from the word "one") ---------------------
            
            # reset temp_appt_date if 01:00 is extracted without user taking any appointment actions
            if (temp_appt_date['time'] == "01:00" and 
            intent != "APPT_NEW" and 
            intent != "APPT_CANCEL" and 
            intent != "APPT_RESCHEDULE" and
            appt_state not in ["scheduling_appt", "pending_confirmation", "appt_confirmed", 
                               "appt_reason", "cancelling_appt", "confirm_cancellation", "awaiting_cancellation_dates"]):
                
                temp_appt_date = ap.new_temp_appt_date() # reset temp_appt_date back to default
        
# --------------------- USER WANTS TO RESCHEDULE AN APPOINTMENT ---------------------
            
            # 3. check if intent is to reschedule an appt
            if intent == "APPT_RESCHEDULE":
                reschedule_confirm_message = f"Okay, let's reschedule for you!"
                tts.speak_and_wait(reschedule_confirm_message)
                add_to_history(chat_history, "assistant", reschedule_confirm_message)
                log_turn(call.id, "assistant", reschedule_confirm_message)
                    
                reschedule_state = "cancel_for_rescheduling" # change reschedule_state
                appt_state = "cancelling_appt" # put user through appt cancellation process first, then scheduling process

# --------------------- USER WANTS TO SCHEDULE A NEW APPOINTMENT ---------------------
            
            # 4. Check for new appointment intent
            if intent == "APPT_NEW" or appt_state == "scheduling_appt":
                appt_state = "scheduling_appt"
                
                # check if time/date fits business hours
                check_appt_timestamp = ap.check_time(temp_appt_date)
                if check_appt_timestamp: # time/date conflict if true
                    tts.speak_and_wait(check_appt_timestamp)
                    add_to_history(chat_history, "assistant", check_appt_timestamp)
                    log_turn(call.id, "assistant", check_appt_timestamp)
                    continue
                
                # return a list of any missing info
                blanks = ap.missing_info_check(temp_appt_date)
                
                # format date to be read by voice using first date captured
                if temp_appt_date['date']:
                    pretty_date = ap.prettify_date(temp_appt_date['date'])
                    
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
                
                # if date is missing but time isn't
                elif not temp_appt_date['date']:
                    missing_date_msg = f"Please say the date that you would like to schedule your appointment for at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}."
                    tts.speak_and_wait(missing_date_msg)
                    add_to_history(chat_history, "assistant", missing_date_msg)
                    log_turn(call.id, "assistant", missing_date_msg)
                    continue
                
                # if time is missing but date isn't 
                # Provide available appt times for date
                elif not temp_appt_date['time']:
                    # give availabilities for day if not given yet
                    if availability_state == "check_availability":
                        availability_msg = f"Let me check our availability for {pretty_date}."
                        tts.speak_and_wait(availability_msg)
                        add_to_history(chat_history, "assistant", availability_msg)
                        log_turn(call.id, "assistant", availability_msg)
                        
                        # return all appt times available for day in a system prompt
                        day_appts_sys_prompt,available_appt_times = ap.check_appt_availability(temp_appt_date['date'], ap.TIME_SLOTS) # TIME_SLOTS = list of all possible time slots
                        # if whole day is completely booked
                        if not available_appt_times:
                            fully_booked_msg = f"Sorry, we are fully booked for {pretty_date}. Please try a different day."
                            tts.speak_and_wait(fully_booked_msg)
                            add_to_history(chat_history, "assistant", fully_booked_msg)
                            log_turn(call.id, "assistant", fully_booked_msg)
                            continue
                        
                        # if all time slots are available (prevents agent from reading all time slots)
                        elif day_appts_sys_prompt == "full_availability_weekday":
                            full_availability_weekday_msg = f"We have full availability on {pretty_date}. Please choose any appointment time you'd like from 8:00am to 4:30pm, on the hour or half hour."
                            tts.speak_and_wait(full_availability_weekday_msg)
                            add_to_history(chat_history, "assistant", full_availability_weekday_msg)
                            log_turn(call.id, "assistant", full_availability_weekday_msg)
                            # reset availability_state back to None 
                            availability_state = None
                            continue
                        # if all time slots are available on a friday (closes 1 hour earlier)
                        elif day_appts_sys_prompt == "full_availability_friday":
                            full_availability_friday_msg = f"We have full availability on {pretty_date}. Please choose any appointment time you'd like from 8:00am to 3:30pm, on the hour or half hour."
                            tts.speak_and_wait(full_availability_friday_msg)
                            add_to_history(chat_history, "assistant", full_availability_friday_msg)
                            log_turn(call.id, "assistant", full_availability_friday_msg)
                            # reset availability_state back to None
                            availability_state = None
                            continue
                        
                        else:
                            # add to chat_history as system prompt to be interpreted by agent
                            add_to_history(chat_history, "system", day_appts_sys_prompt)
                            # prompt llm specifically for the available times
                            prompt_for_availability = f"Please give me the available times for {temp_appt_date['date']}"
                            availabilities_response = query_ollama(prompt_for_availability, chat_history, llm_model)
                        
                            # agent informs user on available times
                            tts.speak_and_wait(availabilities_response)
                            log_turn(call.id, "assistant", availabilities_response)
                            print(day_appts_sys_prompt)

                            # if only one slot is available
                            if len(available_appt_times) == 1:
                                # put user through different line of logic for confirming last appt slot
                                availability_state = "confirm_last_slot"
                                last_available_time = available_appt_times[0]
                                print(f"LAST_AVAILABLE_TIME: {last_available_time}")
                                continue
                            
                            # reset availability_state back to None when times have been given to user
                            availability_state = None
                            continue
                
                # ask for confirmation once appt info is complete
                elif not blanks:
                    # double check time and date
                    incorrect_time = ap.check_time(temp_appt_date)
                    if incorrect_time:
                        incorrect_time_msg = incorrect_time
                        tts.speak_and_wait(incorrect_time_msg)
                        add_to_history(chat_history, "assistant", incorrect_time_msg)
                        log_turn(call.id, "assistant", incorrect_time_msg)
                        continue
                    
                    # run if time/date checks out    
                    if not incorrect_time:
                        # check if specific day & time are available for appointments
                        _,available_appt_times = ap.check_appt_availability(temp_appt_date['date'], ap.TIME_SLOTS)
                        
                        # if there are no available times on that day
                        if not available_appt_times:
                            fully_booked_msg = f"Sorry, we are fully booked for {pretty_date}. Please try a different day."
                            tts.speak_and_wait(fully_booked_msg)
                            add_to_history(chat_history, "assistant", fully_booked_msg)
                            log_turn(call.id, "assistant", fully_booked_msg)
                            
                            # reset temp_appt_date
                            temp_appt_date = ap.new_temp_appt_date()
                            continue
                        
                        if temp_appt_date['time'] not in available_appt_times:
                            booked_time_msg = f"Sorry, {temp_appt_date['time']} is already booked for {pretty_date}."
                            tts.speak_and_wait(booked_time_msg)
                            add_to_history(chat_history, "assistant", booked_time_msg)
                            log_turn(call.id, "assistant", booked_time_msg)
                            # recommend closest appointment times
                            nearest_slots = ap.nearest_available_slots(ap.TIME_SLOTS, available_appt_times, temp_appt_date['time'])
                            
                            # if only one slot is available
                            if type(nearest_slots) == tuple: # returns message and only available time
                                last_available_time = nearest_slots[1]
                                availability_state = "confirm_last_slot" # change availability_state

                                tts.speak_and_wait(nearest_slots[0])
                                add_to_history(chat_history, "assistant", nearest_slots[0])
                                log_turn(call.id, "assistant", nearest_slots[0])
                                continue 
                            
                            else: # returns only recommended other times
                                tts.speak_and_wait(nearest_slots)
                                add_to_history(chat_history, "assistant", nearest_slots)
                                log_turn(call.id, "assistant", nearest_slots)
                                continue
                            
                        confirm_appt_msg = f"To confirm, you'd like to schedule your appointment for {pretty_date} at {ap.format_appt_time(temp_appt_date['time'])}{temp_appt_date['ampm']}, is that correct?"
                        appt_state = "pending_confirmation"
                        tts.speak_and_wait(confirm_appt_msg)
                        add_to_history(chat_history, "assistant", confirm_appt_msg)
                        log_turn(call.id, "assistant", confirm_appt_msg)
                        continue

# --------------------- USER WANTS TO CANCEL AN APPOINTMENT ---------------------
            
            # 5. check for appt cancellation
            if intent == "APPT_CANCEL" or appt_state == "cancelling_appt":
                appt_state = "cancelling_appt"
                patient_appts, patient_appt_dicts = ap.patient_existing_appts(patient.id)
                cancel_appt_id = None
                
                # if patient doesn't have any appts scheduled
                if not patient_appts:
                    no_patient_appts_msg = "Our database is showing that you do not have any scheduled appointments at this time. If you would like to make a new one, just ask!"
                    tts.speak_and_wait(no_patient_appts_msg)
                    add_to_history(chat_history, "assistant", no_patient_appts_msg)
                    log_turn(call.id, "assistant", no_patient_appts_msg)
                    appt_state = None
                    continue
                
                # if patient names date and time of appt to cancel
                elif temp_appt_date['date'] and temp_appt_date['time']:
                    pretty_cancel_date = f"{ap.prettify_date(temp_appt_date['date'])} at {temp_appt_date['time']}" # prettify date for synthesizer
                    # if date and time patient mentions matches appt in the system
                    for appt in patient_appt_dicts:
                        if temp_appt_date['date'] == appt['date'] and temp_appt_date['time'] == appt['time']:
                            ask_appt_cancellation_msg = f"To confirm, you would like to cancel your appointment for {pretty_cancel_date}{appt['ampm']}"
                            tts.speak_and_wait(ask_appt_cancellation_msg)
                            add_to_history(chat_history, "assistant", ask_appt_cancellation_msg)
                            log_turn(call.id, "assistant", ask_appt_cancellation_msg)
                            appt_state = "confirm_cancellation"
                            cancel_appt_id = appt['id'] # assign appt id to variable for db update later
                            break
                    # if given date and time does not match appts in the system
                    if not cancel_appt_id:
                        cancel_appt_mismatch_msg = f"{pretty_cancel_date} does not match up with any existing appointments in our system. Please try repeating the date and time of the appointment you would like to cancel."
                        tts.speak_and_wait(cancel_appt_mismatch_msg)
                        add_to_history(chat_history, "assistant", cancel_appt_mismatch_msg)
                        log_turn(call.id, "assistant", cancel_appt_mismatch_msg)
                        appt_state = "awaiting_cancellation_dates"
                    continue
                
                # if date for cancellation is mentioned but not time
                elif temp_appt_date['date'] and not temp_appt_date['time']:
                    # if date patient mentions matches appt in the system
                    appts_for_day = [] # initiate list to append all appts for that day
                    for appt in patient_appt_dicts:
                        if temp_appt_date['date'] == appt['date']:
                            appts_for_day.append(appt['time'])
                    
                    # if user has no appts on specified day
                    if not appts_for_day:
                        no_patient_appts_msg = f"Our database is showing that you do not have any scheduled appointments for {ap.prettify_date(temp_appt_date['date'])}. Please try a different date."
                        tts.speak_and_wait(no_patient_appts_msg)
                        add_to_history(chat_history, "assistant", no_patient_appts_msg)
                        log_turn(call.id, "assistant", no_patient_appts_msg)
                        appt_state = "awaiting_cancellation_date"
                        continue
                    
                    # if user has one appt time for specified day
                    if len(appts_for_day) == 1:
                        pretty_cancel_date = f"{ap.prettify_date(temp_appt_date['date'])} at {appts_for_day[0]}" # prettify date for synthesizer
                        ask_appt_cancellation_msg = f"You have one appointment for {pretty_cancel_date}{appt['ampm']}, would you like to cancel that?"
                        tts.speak_and_wait(ask_appt_cancellation_msg)
                        add_to_history(chat_history, "assistant", ask_appt_cancellation_msg)
                        log_turn(call.id, "assistant", ask_appt_cancellation_msg)
                        appt_state = "confirm_cancellation"
                        cancel_appt_id = appt['id'] # assign appt id to variable for db update later
                        continue
                    
                    # if user has multiple appt times for specified day
                    if len(appts_for_day) > 1:
                        ask_appt_cancel_time_msg = f"You have multiple appointment times for {ap.prettify_date(temp_appt_date['date'])}. Which one would you like to cancel, {appts_for_day[0:-1]} or {appts_for_day[-1]}?"
                        tts.speak_and_wait(ask_appt_cancel_time_msg)
                        add_to_history(chat_history, "assistant", ask_appt_cancel_time_msg)
                        log_turn(call.id, "assistant", ask_appt_cancel_time_msg)
                        appt_state = "awaiting_cancellation_date" # set to awaiting_cancellation_date to avoid conflict with appt scheduler when date is mentioned
                        continue
                        
                elif len(patient_appt_dicts) == 1: # if they have 1 appt scheduled
                    pretty_cancel_date = f"{ap.prettify_date(patient_appt_dicts[0]['date'])} at {patient_appt_dicts[0]['time']}" # prettify date for synthesizer
                    tts.speak_and_wait(patient_appts)
                    add_to_history(chat_history, "assistant", patient_appts)
                    log_turn(call.id, "assistant", patient_appts)
                    appt_state = "confirm_cancellation"
                    cancel_appt_id = patient_appt_dicts[0]['id']
                    continue
                
                else: # if patient has more than 1 appt scheduled
                    tts.speak_and_wait(patient_appts)
                    add_to_history(chat_history, "assistant", patient_appts)
                    log_turn(call.id, "assistant", patient_appts)
                    appt_state = "awaiting_cancellation_date"
                    continue

# --------------------- USER WANTS RX REFILL ---------------------
            if intent == "RX_REFILL" and refill_state != "drug_name":
                rx_refill_msg = "Please exclusively name the medication you would like to refill."
                tts.speak_and_wait(rx_refill_msg)
                add_to_history(chat_history, "assistant", rx_refill_msg)
                log_turn(call.id, "assistant", rx_refill_msg)
                refill_state = "drug_name"
                continue
            
            # use fuzzy match on input and ask to confirm drug match
            # drug list for demo inlcudes: omeprazole, lisinopril, atorvastatin, metformin and amoxicillin
            if refill_state == "drug_name":
                med = match_medication(user_input)
                # if drug name match not found, ask to repeat
                if not med:
                    no_drug_match_msg = "I'm sorry, I didn't catch the name of the medication. Could you repeat?"
                    tts.speak_and_wait(no_drug_match_msg)
                    add_to_history(chat_history, "assistant", no_drug_match_msg)
                    log_turn(call.id, "assistant", no_drug_match_msg)
                    continue
                else:
                    confirm_med_msg = f"To confirm, you would like a refill for {med}?"
                    tts.speak_and_wait(confirm_med_msg)
                    add_to_history(chat_history, "assistant", confirm_med_msg)
                    log_turn(call.id, "assistant", confirm_med_msg)
                    refill_state = "confirm_drug_name"
                    continue
                
# --------------------- USER INTENT UNCLEAR, LLM TRIES TO REPLY HELPFULLY ---------------------
                
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
        end_call(call.id, resolved=resolved, escalated=False, notes=call_notes(chat_history, llm_model))
        
if __name__ == "__main__":
    main_edge()