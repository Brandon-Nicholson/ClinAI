"""
main.py
"""

# Imports from modular voice pipeline
from app.ui.intake_form import run_intake_form
from app.services.call_service import start_call, end_call, set_intent, log_turn, was_resolved, call_notes
from app.voice.synthesizer import stop_speaking, EdgeTTSPlayer
from app.voice.transcriber import start_microphone, listen_and_transcribe_whisper
from app.voice.llm import query_ollama, add_to_history, main_system_prompt, info_system_prompt, human_system_prompt
from faster_whisper import WhisperModel
from classifiers.intent_model.intent_classifier import classify_intent
from classifiers.appt_context_model.appt_context_classifier import classify_appt_context
from classifiers.appt_confirmation_model.appt_confirmation_classifier import classify_appt_confirmation
from classifiers.appt_availability_model.appt_availability_classifier import classify_appt_availability
from datetime import date
import app.services.appointments as ap
import time
import re
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
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

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
    availability_state = None
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
            
            # skip empties
            if not user_input:
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
                add_to_history(chat_history, "assistant", goodbye_msg)
                log_turn(call.id, "assistant", goodbye_msg)
                break
            
            
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
                loop_convo = False
                continue
            # log user input -> db
            log_turn(call.id, "user", user_input)
            
            # classify user intent unless appt scheduling is in process
            intent = classify_intent(user_input, patient_intents)
            
            # avoid conflict bewteen scheduling and cancelling appointments
            if appt_state == "awaiting_cancellation_date":
                intent = "APPT_CANCEL"
                
            # perform next action based on intent
            print(f"Prompt Intent: {intent}")
            print(f"Appt State: {appt_state}")
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
            
            # if user is beign asked to confirm cancellation for booked appointment
            if appt_state == "confirm_cancellation":
                confirm_appt_cancellation = classify_appt_confirmation(user_input)
                if confirm_appt_cancellation == "CONFIRM":
                    # change status of appt to cancelled in db
                    cancel_appt = ap.cancel_appointment(cancel_appt_id)
                    
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
                    # set appt_state to still in_progress
                    appt_state = None
                    # reset availability_state
                    availability_state = None
                    continue
                
            # if user is being asked to confirm the last available appointment on their desired appt date
            if availability_state == "confirm_last_slot":
                confirm_last_appt_time = classify_appt_confirmation(user_input)
                
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
                    # set appt_state to still in_progress
                    appt_state = "in_progress"
                    # reset availability_state
                    availability_state = None
                    continue
                    
            # classifier detects if user wants to exit appointment scheduling pipeline
            if appt_state == "pending_confirmation" or appt_state == "in_progress" or appt_state == "appt_reason":
                exit_appt_scheduling = classify_appt_context(user_input)
                # if user intended to cancel an appt instead
                if intent == "APPT_CANCEL":
                    appt_state = "cancelling_appt"
                    pass
                # exit pipeline if user implies they no longer want to schedule appt
                if exit_appt_scheduling == "EXIT_APPT":
                    exit_appt_pipeline_msg = "Got it. If you'd like help with anything else, just ask! If you'd like to exit the call, say stop."
                    tts.speak_and_wait(exit_appt_pipeline_msg)
                    add_to_history(chat_history, "assistant", exit_appt_pipeline_msg)
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
                    add_to_history(chat_history, "assistant", appt_denied_msg)
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
                    add_to_history(chat_history, "assistant", unsure_msg)
                    log_turn(call.id, "assistant", unsure_msg)
                    continue
            
            # ask reason for appt once date/time is confirmed
            if not ap.missing_info_check(temp_appt_date) and appt_state == "appt_confirmed":
                appt_reason_msg = "Perfect! And what is the reason for your appointment?"
                tts.speak_and_wait(appt_reason_msg)
                add_to_history(chat_history, "assistant", appt_reason_msg)
                log_turn(call.id, "assistant", appt_reason_msg)
                # update appt_state
                appt_state = "appt_reason"
                continue
                
            # update db with all appt info once appt reason is given
            if appt_state == "appt_reason":
                # store reason for appt in variable
                appt_reason = user_input
                appt_confirmation_msg = "Got it! Your appointment has been registered into our system. If you'd like to make another appointment or request, just ask! If you'd like to end the call now, say stop."
                tts.speak_and_wait(appt_confirmation_msg)
                add_to_history(chat_history, "assistant", appt_confirmation_msg)
                log_turn(call.id, "assistant", appt_confirmation_msg)
                
                # update db
                db_timestamp_format = ap.parts_to_local_dt(temp_appt_date) # convert dict to timestamp format for db
                ap.book_appointment(call.patient_id, call.id, db_timestamp_format, duration_min=30, reason=appt_reason)
                
                # reset appt date holder after appt has been made
                temp_appt_date = ap.new_temp_appt_date()
                # reset appt_state back to None
                appt_state = None
                # reset avaialbility state back to None
                availability_state = None
                continue
            
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
            
            # 3. Check for new appointment intent
            if intent == "APPT_NEW" or appt_state == "in_progress":
                appt_state = "in_progress"
                
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
                
                        # add to chat_history as system prompt to be interpreted by agent
                        add_to_history(chat_history, "system", day_appts_sys_prompt)
                        # prompt llm specifically for the available times
                        prompt_for_availability = f"Please give me the available times for {temp_appt_date['date']}"
                        availabilities_response = query_ollama(prompt_for_availability, chat_history, llm_model)
                        
                        # agent informs user on available times
                        tts.speak_and_wait(availabilities_response)
                        add_to_history(chat_history, "assistant", availabilities_response)
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
                        
                        print(f"AVAILABLE APPT TIMES: {available_appt_times}")
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
                            
                            else: # recommend other times
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
            
            # check for appt cancellation
            if intent == "APPT_CANCEL":
                appt_state = "cancelling_appt"
                patient_appts, patient_appt_dicts = ap.patient_existing_appts(patient.id)
                cancel_appt_id = None
                
                # if patient doesn't have any appts scheduled
                if not patient_appts:
                    no_patient_appts_msg = "Our database is showing that you do not have any scheduled appointments at this time."
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
                            print(f"temp_appt_date: {temp_appt_date['date']}, appt_date: {appt['date']}")
                            print(f"temp_appt_date: {temp_appt_date['time']}, appt_date: {appt['time']}")
                            ask_appt_cancellation_msg = f"To confirm, you would like to cancel your appointment for {pretty_cancel_date}{appt['ampm']}"
                            tts.speak_and_wait(ask_appt_cancellation_msg)
                            add_to_history(chat_history, "assistant", ask_appt_cancellation_msg)
                            log_turn(call.id, "assistant", ask_appt_cancellation_msg)
                            appt_state = "confirm_cancellation"
                            cancel_appt_id = appt['id'] # assign appt id to variable for db update later
                            print(cancel_appt_id)
                            break
                    # if given date and time does not match appts in the system
                    if not cancel_appt_id:
                        cancel_appt_mismatch_msg = f"{pretty_cancel_date} does not match up with any existing appointments in our system. Please try repeating the date and time of the appointment you would like to cancel."
                        tts.speak_and_wait(cancel_appt_mismatch_msg)
                        add_to_history(chat_history, "assistant", cancel_appt_mismatch_msg)
                        log_turn(call.id, "assistant", cancel_appt_mismatch_msg)
                        appt_state = "cancelling_appt"
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