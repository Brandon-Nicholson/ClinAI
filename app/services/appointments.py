# app/services/appointments.py

from __future__ import annotations
from typing import Iterable, Optional, List
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, date, time
from apscheduler.schedulers.background import BackgroundScheduler
import re

from app.db.session import get_session
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, text

from app.db.models import Appointment

# creates temporary appt date holder
def new_temp_appt_date():
    return {'date': None, 'time': None, 'ampm': None}

# list all possible time slots
TIME_SLOTS = [
"08:00", "08:30", "09:00", "09:30",
"10:00", "10:30", "11:00", "11:30",
"12:00", "12:30", "01:00", "01:30",
"02:00", "02:30", "03:00", "03:30",
"04:00", "04:30"
]

WEEKDAYS = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
WDX = {w:i for i,w in enumerate(WEEKDAYS)}
DEFAULT_TZ = ZoneInfo("America/Los_Angeles")

OPEN_HOUR = 8   # 8am
CLOSE_HOUR = 17 # 5pm

# Patterns
# this/next weekday
weekday_pattern = re.compile(
    r"\b(?P<kw>this|next)\s+(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    flags=re.IGNORECASE
)

# bare weekday
bare_weekday_pattern = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    flags=re.IGNORECASE
)

# e.g., "830", "1030", "945", "1730"
compact_time_pattern = re.compile(r"\b(?P<h>\d{1,2})(?P<m>\d{2})\b")

# month name -> day [ordinal] [, year]
month_names = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
month_day_pattern = re.compile(
    rf"\b(?P<month>{month_names})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(?P<year>\d{{4}}))?\b",
    flags=re.IGNORECASE
)

# e.g., "17th of June", "17 June", "on the 17th June, 2026"
day_first_month_pattern = re.compile(
    rf"\b(?:on\s+)?(?:the\s+)?(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s+(?P<month>{month_names})(?:,?\s*(?P<year>\d{{4}}))?\b",
    flags=re.IGNORECASE
)

# numeric dates: 6/9, 06-09-2026, 6.9.26
numeric_date_pattern = re.compile(
    r"\b(?P<m>\d{1,2})[\/\-\._](?P<d>\d{1,2})(?:[\/\-\._](?P<y>\d{2,4}))?\b"
)

# ordinal-only day: "on the 9th", "for the 21st"
ordinal_day_pattern = re.compile(
    r"\b(?:on|for)?\s*(?:the\s+)?(?P<day>\d{1,2})(?:st|nd|rd|th)\b",
    flags=re.IGNORECASE
)

# times:
# - 5, 5pm, 5 pm, 5 p.m., 5:30, 17:30
# - "noon", "midnight"
# - "in the morning/afternoon/evening/night"
time_pattern = re.compile(
    r"\b(?:(?P<noon>noon)|(?P<midnight>midnight)|(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>a\.?m?\.?|p\.?m?\.?)?)"
    r"(?:\s*(?:in\s+the\s+)?(?P<daypart>morning|afternoon|evening|night))?\b",
    flags=re.IGNORECASE
)

# for prompts asking about "today" and "tomorrow"
today_pattern = re.compile(r"\btoday\b", flags=re.IGNORECASE)
tomorrow_pattern = re.compile(r"\btomorrow\b", flags=re.IGNORECASE)

# simple sentence terminator to limit the “nearby time” window
sentence_end = re.compile(r"[.!?]")

# word -> time normalizer
WORD_NUM_MAP = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12
}

# maps minute words we care about
_MIN_WORD = {
    "thirty": 30, "fifteen": 15, "forty five": 45, "forty-five": 45,
    "o'clock": 0, "oclock": 0
}

# e.g. "five", "seven thirty", "eleven o'clock", optional "pm" and/or daypart text
_word_time_norm_pattern = re.compile(
    r"\b(?P<hour>one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    r"(?:\s+(?P<min>thirty|fifteen|forty(?:\s|-)?five|o['’]?clock|oclock))?"
    r"(?:\s*(?P<ampm>a\.?m?\.?|p\.?m?\.?))?"
    r"(?:\s*(?:in\s+the\s+)?(?P<daypart>morning|afternoon|evening|night))?"
    r"\b",
    flags=re.IGNORECASE
)

def _normalize_word_times_in_text(text: str) -> str:
    """
    Convert word-based times (one..twelve) into numeric forms the existing extractor already supports.
    Examples:
      "How about three?"            -> "How about 3?"
      "at seven thirty in the evening" -> "at 7:30 pm"
      "eleven o'clock"              -> "11"
      "five pm"                     -> "5 pm"
    We DO NOT guess AM/PM if we can't—your existing logic will infer where appropriate.
    """
    def _repl(m: re.Match) -> str:
        hour_word = m.group("hour").lower()
        hour = WORD_NUM_MAP[hour_word]

        # minutes
        minute_word = m.group("min")
        minute = 0
        if minute_word:
            mw = minute_word.lower().replace("’", "'")
            # normalize "o'clock"
            if mw in ("o'clock", "oclock"):
                minute = 0
            elif mw in ("thirty", "fifteen"):
                minute = _MIN_WORD[mw]
            elif mw.startswith("forty"):
                minute = 45

        # am/pm or daypart (if given, we keep it)
        ampm = (m.group("ampm") or "").lower().replace(".", "")
        daypart = (m.group("daypart") or "").lower()

        # compose numeric time
        if minute:
            core = f"{hour}:{minute:02d}"
        else:
            core = f"{hour}"

        # keep explicit am/pm if present
        if ampm in ("am", "pm"):
            return f"{core} {ampm}"

        # otherwise keep daypart as am/pm if it implies PM
        if daypart in ("afternoon", "evening", "night"):
            return f"{core} pm"
        if daypart == "morning":
            return f"{core} am"

        # no qualifier -> leave as bare time; downstream inference will handle it
        return core

    return _word_time_norm_pattern.sub(_repl, text)


# Helpers
def _week_start(d): return d - timedelta(days=d.weekday())

def _date_this_week_or_next(today, target_idx):
    week_start = _week_start(today)
    candidate = week_start + timedelta(days=target_idx)
    if candidate < today:
        candidate += timedelta(days=7)
    return candidate

def _date_next_week(today, target_idx):
    week_start = _week_start(today)
    return week_start + timedelta(days=7 + target_idx)

def _month_str_to_int(s: str) -> int:
    s = s.lower()[:3]
    return ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"].index(s) + 1

def _apply_year_rollover(today, month, day, year=None):
    if year is None:
        year = today.year
        try_date = datetime(year, month, day).date()
        if try_date < today:
            year += 1
    return datetime(year, month, day).date()

def _infer_month_for_ordinal(today, day):
    """Pick the next calendar month (including this month) where that day exists and is >= today."""
    # Try this month
    m = today.month
    y = today.year
    def _valid(y, m, d):
        try:
            return datetime(y, m, d).date()
        except ValueError:
            return None
    cand = _valid(y, m, day)
    if cand and cand >= today:
        return cand
    # Try future months up to 12 months out
    for i in range(1, 13):
        mm = ((m - 1 + i) % 12) + 1
        yy = y + ((m - 1 + i) // 12)
        cand = _valid(yy, mm, day)
        if cand and cand >= today:
            return cand
    return None  # extremely rare (invalid day like 31 from Feb onward)

def _format_12h(hour24: int, minute: int):
    period = "am" if hour24 < 12 else "pm"
    hour12 = hour24 % 12 or 12
    return f"{hour12:02d}:{minute:02d}", period

def _normalize_time_match(m):
    """Return (hour24, minute) from a time regex match, handling noon/midnight and dayparts."""
    if m.group("noon"):
        return 12, 0
    if m.group("midnight"):
        return 0, 0

    hour = int(m.group("h"))
    minute = int(m.group("m") or 0)
    ampm = m.group("ampm")
    daypart = (m.group("daypart") or "").lower()

    # Normalize AM/PM text like 'p', 'p.m.', 'pm'
    if ampm:
        a = ampm.lower().replace(".", "")
        if a.startswith("p") and hour != 12:
            hour += 12
        elif a.startswith("a") and hour == 12:
            hour = 0
    else:
        # Use daypart hints if no explicit am/pm
        if 1 <= hour <= 11:
            if daypart in ("evening","night","afternoon"):
                # push to PM; 12 is a special case (handled below)
                hour = hour + 12 if hour != 12 else 12
        # If 24h format like 17:30, nothing to do.

    # Clamp 12 edge cases: if someone wrote "12am" -> 0 handled above; "12pm" stays 12.
    return hour, minute

def _is_unqualified_hour_only(m) -> bool:
    """True if the match is just a bare hour (1-12) with no minutes, no am/pm, no daypart."""
    if m.group("noon") or m.group("midnight"):
        return False
    if m.group("m"):              # has minutes like 5:30
        return False
    if m.group("ampm"):           # has am/pm
        return False
    if m.group("daypart"):        # has 'morning/afternoon/evening/night'
        return False
    if m.group("h"):
        h = int(m.group("h"))
        # Allow 24h-style 13..23 as valid even without am/pm
        if 13 <= h <= 23:
            return False
        # Bare 1..12 with no qualifiers → unqualified, ignore
        if 1 <= h <= 12:
            return True
    return False

def _infer_ampm_from_hours(hour12: int, open_hour=OPEN_HOUR, close_hour=CLOSE_HOUR):
    """
    Given a bare 1..12 hour, infer (hour24, 'am'/'pm') using clinic hours.
    Rules:
      - 8..11  -> AM
      - 12     -> PM (noon)
      - 1..6   -> PM (map to 13..18) if within closing time
      - else   -> None (don’t guess)
    """
    if 8 <= hour12 <= 11:
        return hour12, "am"
    if hour12 == 12:
        return 12, "pm"
    if 1 <= hour12 <= 6 and (hour12 + 12) <= close_hour:
        return hour12 + 12, "pm"
    return None

def _find_nearby_time(text, anchor_start, window=120):
    window_end = min(len(text), anchor_start + window)
    slice_text = text[anchor_start:window_end]
    cut = sentence_end.search(slice_text)
    if cut:
        slice_text = slice_text[:cut.start()]

    def _try_accept_unqualified(match, haystack: str):
        htxt = match.group("h")
        if not htxt:
            return None
        pre_start = max(0, match.start() - 6)
        prefix = haystack[pre_start:match.start()].lower()
        if not re.search(r"\bat\s*$", prefix):
            return None
        hour12 = int(htxt)
        infer = _infer_ampm_from_hours(hour12)
        if infer:
            h24, ap = infer
            t12, period = _format_12h(h24, 0)
            return t12, period
        return None

    # 1) Normal time patterns (your existing rules)
    for tm in time_pattern.finditer(slice_text):
        if not _is_unqualified_hour_only(tm):
            h24, mi = _normalize_time_match(tm)
            t12, period = _format_12h(h24, mi)
            return t12, period
        else:
            maybe = _try_accept_unqualified(tm, slice_text)
            if maybe:
                return maybe

    # 2) Compact times like "at 830"
    def _try_compact(haystack: str):
        for cm in compact_time_pattern.finditer(haystack):
            # require "at " right before the number
            pre_start = max(0, cm.start() - 6)
            prefix = haystack[pre_start:cm.start()].lower()
            if not re.search(r"\bat\s*$", prefix):
                continue

            h = int(cm.group("h")); m = int(cm.group("m"))
            if not (0 <= m < 60):
                continue

            # look for immediate am/pm after the number (rare with STT, but cheap to check)
            suffix = haystack[cm.end(): cm.end()+6].lower()
            ap = "am" if re.match(r"^\s*a\.?m?\.?", suffix) else ("pm" if re.match(r"^\s*p\.?m?\.?", suffix) else None)

            # daypart nearby?
            dp = None
            dp_match = re.search(r"\b(morning|afternoon|evening|night)\b", haystack[cm.end(): cm.end()+20], re.IGNORECASE)
            if dp_match:
                dp = dp_match.group(1).lower()

            # Decide hour24
            if 13 <= h <= 23:
                hour24 = h  # 24h style like 1730
            elif ap:
                hour24 = (h % 12) + (12 if ap.startswith("p") else 0)
            elif dp in ("afternoon","evening","night"):
                hour24 = (h % 12) + (12 if h != 12 else 0)
            else:
                inferred = _infer_ampm_from_hours(h)
                if not inferred:
                    continue
                hour24, _ = inferred

            t12, period = _format_12h(hour24, m)
            return t12, period
        return None

    maybe = _try_compact(slice_text)
    if maybe:
        return maybe

    # also check a little to the left (e.g., "at 830 on Friday")
    left_start = max(0, anchor_start - 40)
    left_slice = text[left_start:anchor_start]

    for tm in time_pattern.finditer(left_slice):
        if not _is_unqualified_hour_only(tm):
            h24, mi = _normalize_time_match(tm)
            t12, period = _format_12h(h24, mi)
            return t12, period
        else:
            maybe = _try_accept_unqualified(tm, left_slice)
            if maybe:
                return maybe

    maybe = _try_compact(left_slice)
    if maybe:
        return maybe

    return None, None


# Main

def extract_schedule_json(text: str, now=None, tz: ZoneInfo = DEFAULT_TZ):
    # normalize any word-times
    text = _normalize_word_times_in_text(text)
    
    if now is None:
        now = datetime.now(tz)
    else:
        now = now.replace(tzinfo=tz) if now.tzinfo is None else now.astimezone(tz)

    today = now.date()
    results = []
    covered_spans = []

    def add_result(date_obj, anchor_start, anchor_span):
        t, ap = _find_nearby_time(text, anchor_start)
        results.append({"date": date_obj.isoformat() if date_obj else None, "time": t, "ampm": ap})
        covered_spans.append(anchor_span)

    # appt for "today"
    for m in today_pattern.finditer(text):
        ms, me = m.span()
        dt_date = today
        add_result(dt_date, ms, (ms, me))
        
    # appt for "tomorrow"
    for m in tomorrow_pattern.finditer(text):
        ms, me = m.span()
        dt_date = today + timedelta(days=1)
        add_result(dt_date, ms, (ms, me))

    # Pass A: Month-name absolute dates first (e.g., "June 9th, 2026")
    for m in month_day_pattern.finditer(text):
        ms, me = m.span()
        month = _month_str_to_int(m.group("month"))
        day = int(m.group("day"))
        year = m.group("year")
        year = int(year) if year else None
        try:
            dt_date = _apply_year_rollover(today, month, day, year)
        except ValueError:
            continue  # invalid date like Feb 30
        add_result(dt_date, ms, (ms, me))
    
     # Pass A2: Day-first month (e.g., "17th of June", "17 June, 2026")
    for m in day_first_month_pattern.finditer(text):
        ms, me = m.span()
        # avoid overlap with earlier captures
        if any(not (me <= s or ms >= e) for (s, e) in covered_spans):
            continue
        month = _month_str_to_int(m.group("month"))
        day = int(m.group("day"))
        year = m.group("year")
        year = int(year) if year else None
        try:
            dt_date = _apply_year_rollover(today, month, day, year)
        except ValueError:
            continue
        add_result(dt_date, ms, (ms, me))
    
    # Pass B: Numeric dates
    for m in numeric_date_pattern.finditer(text):
        ms, me = m.span()
        # avoid overlapping with month-name we already captured
        if any(not (me <= s or ms >= e) for (s, e) in covered_spans):
            continue
        mth = int(m.group("m"))
        day = int(m.group("d"))
        y = m.group("y")
        year = None
        if y:
            year = int(y)
            if year < 100:  # 2-digit year → assume 2000s
                year += 2000
        try:
            dt_date = _apply_year_rollover(today, mth, day, year)
        except ValueError:
            continue
        add_result(dt_date, ms, (ms, me))

    # Pass C: Ordinal day (“on the 9th”) → infer next valid month
    for m in ordinal_day_pattern.finditer(text):
        ms, me = m.span()
        if any(not (me <= s or ms >= e) for (s, e) in covered_spans):
            continue
        day = int(m.group("day"))
        dt_date = _infer_month_for_ordinal(today, day)
        if not dt_date:
            continue
        add_result(dt_date, ms, (ms, me))

    # Pass D: explicit "this/next <weekday>"
    for m in weekday_pattern.finditer(text):
        ms, me = m.span()
        if any(not (me <= s or ms >= e) for (s, e) in covered_spans):
            continue
        kw = m.group("kw").lower()
        day = m.group("day").lower()
        target_idx = WDX[day]
        dt_date = _date_this_week_or_next(today, target_idx) if kw == "this" else _date_next_week(today, target_idx)
        add_result(dt_date, ms, (ms, me))

    # Pass E: bare "<weekday>" → treat as "this <weekday>"
    for m in bare_weekday_pattern.finditer(text):
        ms, me = m.span()
        if any(not (me <= s or ms >= e) for (s, e) in covered_spans):
            continue
        day = m.group(0).lower()
        target_idx = WDX[day]
        dt_date = _date_this_week_or_next(today, target_idx)
        add_result(dt_date, ms, (ms, me))

    # Pass F: time-only with explicit or inferable am/pm
    if not results:
        tm = time_pattern.search(text)
        if tm:
            h24, mi = _normalize_time_match(tm)
            t12, period = _format_12h(h24, mi)
            results.append({"date": None, "time": t12, "ampm": period})

    return results


# check for missing info in appt date
def missing_info_check(temp_appt_date):
    blanks = []
    if temp_appt_date['date'] is None and temp_appt_date['time'] is None:
        blanks.append(None)
    else:
        for k, v in temp_appt_date.items():
            if v is None and k != "ampm":
                blanks.append(k)
            
    return blanks

# check for duplicates in results
def len_deduped_results(results):
    try:
        str_appts = [' '.join(appt.values()) for appt in results]
        deduped_appts = set(str_appts)
    except:
        return 0
    
    return len(deduped_appts)
    
# check that times are compatible with hours of operation and scheduling structure
def check_time(temp_appt_date: dict, open_time = 8, close_time = 17) -> bool:
    
    """
    Hours of Operation:
    "Mon": "8:00am–5:00pm",
    "Tue": "8:00am–5:00pm",
    "Wed": "8:00am–5:00pm",
    "Thu": "8:00am–5:00pm",
    "Fri": "8:00am–4:00pm",
    "Sat": "Closed",
    "Sun": "Closed"
    """
    time = temp_appt_date['time']
    ampm = temp_appt_date['ampm']
    appt_date = temp_appt_date['date']
    
    # map up to 7 because clinic is closed 6-7 both am/pm
    tf_hour_map = {1:13, 2:14, 3:15, 4:16, 5:17}
    
    if time:
        # remove formatting/separate hour and minute
        hour_min_split = time.split(':')
        hour = int(hour_min_split[0])
        minute = int(hour_min_split[1])
        
        # make constant copy of original
        RAW_HOUR = hour
        
        # get correct 24 hour time for certain hours
        if hour >= 1 and hour <= 5:
            hour = tf_hour_map[hour]
            
    if appt_date:
        # convert day to numerical representation of week day (Mon-Sun = 0-6)
        d = date.fromisoformat(appt_date)
        weekday = d.weekday()
    
    if time and not appt_date:
        # check that appointment starts on the hour or half-hour
        if minute not in [0,30]:
            return f"Sorry, we only schedule appointments on the hour or half hour. For example, {RAW_HOUR} or {RAW_HOUR}:30."
        elif RAW_HOUR in [6,7,8,9,10,11] and ampm == "pm":
            return "Sorry, we're only open from 8am to 5pm Monday through Thursday and 8am to 4pm on Friday."
        elif RAW_HOUR in [12,1,2,3,4,5,6,7] and ampm == "am":
            return "Sorry, we're only open from 8am to 5pm Monday through Thursday and 8am to 4pm on Friday."
        
    elif appt_date and not time:
        # handle incorrect times with specific messages
        if weekday > 4:
            return "Sorry, we are closed on weekends."
     
    elif appt_date and time: 
        # handle incorrect times with specific messages
        if weekday == 4 and hour >= 16:
            return "Sorry, we're only open from 8am to 4pm on Fridays. The last appointment is at 3:30pm."
        elif weekday > 4:
            return "Sorry, we are closed on weekends."
        elif weekday < 4 and hour >= 17:
            return "Sorry, we're only open from 8am to 5pm Monday through Thursday and 8am to 4pm on Friday. The last appointment is 30 minutes before closing."
        elif RAW_HOUR in [5,6,7,8,9,10,11] and ampm == "pm":
            return "Sorry, we're only open from 8am to 5pm Monday through Thursday and 8am to 4pm on Friday. The last appointment is 30 minutes before closing."
        elif RAW_HOUR in [12,1,2,3,4,5,6,7] and ampm == "am":
            return "Sorry, we're only open from 8am to 5pm Monday through Thursday and 8am to 4pm on Friday. The last appointment is 30 minutes before closing."
        
        # check that appointment starts on the hour or half-hour
        if minute not in [0,30]:
            return f"Sorry, we only schedule appointments on the hour or half hour. For example, {RAW_HOUR} or {RAW_HOUR}:30."

    return None


# ----Formatting-----

# fix improperly transcribed times within prompt
def format_prompt_time(prompt):
    # extract time from prompt
    split_prompt = prompt.split()
    for index, string in enumerate(split_prompt):
        if string[0].isdigit():
            # remove non-alphanumeric characters
            time = re.sub(r'[^0-9]', '', string)
            time_len = len(time)
            
            # insert colon at correct index & replace original time
            if time_len == 3:
                time = f"{time[0]}:{time[1:]}"
            elif time_len == 4:
                time = f"{time[:2]}:{time[2:]}"
            else:
                continue
                    
            split_prompt[index] = time
            
            return ' '.join(split_prompt)
    return prompt

# update existing appt info with new info
def update_results(result: dict, appt_date_made: dict) -> dict:
    updated_dict = appt_date_made
    
    for key, value in result.items():
        if value:
            updated_dict[key] = value
    

    return updated_dict

# format date -> more human-readable
def ordinal(n: int) -> str:
    return f"{n}{'th' if 11<=n%100<=13 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"

# quick format to make appt times more readable by voice
def format_appt_time(time: str):
    if time[0] == '0':
        return time[1:]
    else:
        return time
    
# fix incorrect labeling of am/pm
def ampm_mislabel_fix(temp_appt_date: dict) -> dict:
    time = temp_appt_date['time']
    ampm = temp_appt_date['ampm']
    
    # return original dict if no time is captured yet
    if not time:
        return temp_appt_date
    
    # extract the hour
    hour = int(time.split(":")[0])
    # assume pm for hours 1-5
    if hour in [1,2,3,4,5] and ampm == "am":
        temp_appt_date['ampm'] = 'pm'
        return temp_appt_date
    # assume am for hours 8-11
    elif hour in [8,9,10,11] and ampm == "pm":
        temp_appt_date['ampm'] = 'am'
        return temp_appt_date
    else:
        return temp_appt_date

# converts dictionary format to DB timestamp format
def parts_to_local_dt(parts: dict, tz: ZoneInfo = DEFAULT_TZ) -> datetime:
    
    if not parts or not parts.get("date") or not parts.get("time"):
        raise ValueError("Missing date or time parts")

    yyyy, mm, dd = map(int, parts["date"].split("-"))
    hh12, mi = map(int, parts["time"].split(":"))
    ap = (parts.get("ampm") or "").lower()

    # Infer am/pm if missing
    if not ap:
        inferred = _infer_ampm_from_hours(hh12)
        if inferred:
            hh24, ap = inferred
        else:
            ap = "pm" if 1 <= hh12 <= 6 else "am"  # fallback if outside clinic hours
            hh24 = (hh12 % 12) + (12 if ap == "pm" else 0)
    else:
        # Convert 12h -> 24h manually if am/pm provided
        if ap == "pm" and hh12 != 12:
            hh24 = hh12 + 12
        elif ap == "am" and hh12 == 12:
            hh24 = 0
        else:
            hh24 = hh12

    return datetime(yyyy, mm, dd, hh24, mi, tzinfo=tz)

# converts DB timestamp format to dictionary format
def appt_local_parts(appt: Appointment):
    """Return (YYYY-MM-DD, HH:MM (12h, zero-padded), am|pm) in clinic time."""
    tz = ZoneInfo(appt.clinic_tz or DEFAULT_TZ)
    local_dt = appt.starts_at.astimezone(tz)
    date_str = local_dt.date().isoformat()
    hour24, minute = local_dt.hour, local_dt.minute
    ampm = "am" if hour24 < 12 else "pm"
    hour12 = (hour24 % 12) or 12
    time_str = f"{hour12:02d}:{minute:02d}"
    return date_str, time_str, ampm

# finds time slots close to unavailable time for recommendation from agent
def nearest_available_slots(time_slots, available_slots, time_pick):
    
    # return None if no available slots for that day
    if not available_slots:
        return None

    # grab slots nearest to patient's desired time
    after_slots = time_slots[time_slots.index(time_pick)+1:] # slots to the right
    before_slots = time_slots[time_slots.index(time_pick)-1::-1] # slots to the left

    ordered_slots = zip(after_slots,before_slots)

    ordered_slots_list = []

    for a,b in ordered_slots:
        ordered_slots_list.append(a)
        ordered_slots_list.append(b)

    recommend_slots = [] # max length = 2
    counter = 0
    for slot in ordered_slots_list:
        if slot in available_slots:
            if counter > 2:
                break
            else:
                recommend_slots.append(slot)
    
    # if only one other slot is available
    if len(recommend_slots) == 1:
        return f"We only have {recommend_slots[0]} available for that day. Would you like to do that instead?", recommend_slots[0]
                    
    return f"Would you like to try {recommend_slots[0]} or {recommend_slots[1]} instead?"


# -----Checking Availabilities-----

ACTIVE_STATUSES = ("scheduled", "rescheduled", "completed")  # exclude 'canceled','no_show'

# return all available times on a certain day
def check_appt_availability(date_str: str, time_slots: list, tz_str: str = "America/Los_Angeles") -> list[str]:

    # convert day to numerical representation of week day (Mon-Sun = 0-6)
    d = date.fromisoformat(date_str)
    weekday = d.weekday()

    
    # knock off time slots if friday (closes 1hr earlier)
    if weekday == 4:
        while time_slots[-1] != "03:30":
            time_slots.pop()
            
    tz = ZoneInfo(tz_str)
    day = datetime.fromisoformat(date_str).date()

    # local start/end of day
    local_start = datetime.combine(day, time.min, tzinfo=tz)
    local_end = local_start + timedelta(days=1)

    # convert to UTC for timestamptz comparison
    start_utc = local_start.astimezone(ZoneInfo("UTC"))
    end_utc = local_end.astimezone(ZoneInfo("UTC"))
    
    # query for all scheduled appts that haven't been cancelled
    with get_session() as session:
        q = (
            select(Appointment.starts_at)
            .where(and_(
                Appointment.starts_at >= start_utc,
                Appointment.starts_at < end_utc,
                Appointment.status == "scheduled"
            ))
            .order_by(Appointment.starts_at)
        )
        results = session.execute(q).scalars().all()
            
    # convert to local time strings
    scheduled_appts = [dt.astimezone(tz).strftime("%I:%M") for dt in results]
    # filter out unavailable slots
    available_slots = [slot for slot in time_slots if slot not in scheduled_appts]
    
    # return None& empty list if no available slots
    if not available_slots:
        return None, None
    
    # format to be interpreted by agent
    converted_times = [] 
    for t in available_slots: 
        # everything from 8:00–12:30 is AM, 1:00–5:00 is PM
        hour = int(t.split(':')[0])
        meridiem = 'am' if hour < 12 and hour != 0 else 'pm'
        # if its 1–5, force pm
        if 1 <= hour <= 5:
            meridiem = 'pm'
        # remove leading zero
        converted_times.append(f"{hour}:{t.split(':')[1]}{meridiem}")
    
    # create system prompt with formatted times
    sys_prompt = f"""
    Below, you will be shown all the appointment times the clinic has available. Your job is to ONLY tell the user which appointment times are available.
    Make sure to say ALL of these available appointment times when asked.
    Listing appointment times that aren't in the list is very damaging to the patient and clinic.
    Available Appointment Times for {date_str}: 
    {converted_times}
    """
    # return sys_prompt for llm and available_slots
    return sys_prompt, available_slots

# -----Booking & Cancelling-----

# update db with appt info
def book_appointment(
    patient_id : int,
    call_id: int,
    starts_at: datetime,
    duration_min: int = 30,
    reason: Optional[str] = None,
    clinic_tz: str = "America/Los_Angeles",
) -> Appointment:

    appt = Appointment(
        patient_id=patient_id,
        call_id=call_id,
        starts_at=starts_at,
        duration_min=duration_min,
        clinic_tz=clinic_tz,
        reason=reason
    )
    with get_session() as session:
        session.add(appt)
        session.commit()
        session.refresh(appt)
    return appt

# cancel an appointment by changing the status
def cancel_appointment(appt_id: int) -> bool:
    with get_session() as s:
        appt = s.get(Appointment, appt_id, with_for_update="read")  # lock row
        if not appt or appt.status != "scheduled":
            return False  # already cancelled/completed or not found
        appt.status = "cancelled"
        s.commit()
        return True
    
# update status for appts that already happened
def sweep_completed():
    sql = text("""
        UPDATE appointments
           SET status = 'completed'
         WHERE status = 'scheduled'
           AND now() >= starts_at + make_interval(mins => duration_min)
    """)
    with get_session() as s:
        s.execute(sql)
        s.commit()

def start_scheduler():
    sch = BackgroundScheduler(timezone="UTC", daemon=True)
    sch.add_job(sweep_completed, "interval", minutes=1, id="appt_sweeper")
    sch.start()
    return sch
