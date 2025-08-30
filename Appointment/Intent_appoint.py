import re
import dateparser
from datetime import datetime, timedelta

# --- helper sets for fast checks ---
_STOPWORDS = {
    "today", "tomorrow", "tonight", "on", "at", "this", "next", "coming",
    "morning", "evening", "afternoon", "noon", "midday", "midnight"
}
_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
_MONTHS = {
    "january","february","march","april","may","june","july","august",
    "september","october","november","december"
}

_TIME_ANYWHERE = re.compile(
    r"\b(?:at\s*)?(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm))\b",
    re.IGNORECASE
)
_TIME_24H = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")  # e.g. 14:30

def _looks_like_date_or_time_token(tok: str) -> bool:
    """Return True if token is a day/time keyword or month/weekday."""
    t = tok.strip(".,!?").lower()
    return (
        t in _STOPWORDS
        or t in _WEEKDAYS
        or t in _MONTHS
        or bool(re.fullmatch(r"\d{1,2}(st|nd|rd|th)?", t))  # 25, 25th
    )

def parse_booking_command(text: str):
    """
    I extract:
      - doctor: strictly the name (e.g., 'Dr John', 'Dr John Wick', 'Dr Van Damme')
      - date: ISO YYYY-MM-DD (today/tomorrow or explicit like '25 August')
      - time: 'HH:MM AM/PM' (from '8pm', '8:00PM', '20:00', etc.)

    Key fix:
      I build the doctor name token-by-token and STOP as soon as the next token
      looks like a date/time keyword (today, tomorrow, at, on, weekdays, months, etc.)
    """
    # -------- Doctor extraction (two-stage) --------
    # 1) Find 'with|to see' + Dr + first name (case-insensitive)
    base = re.search(r"(?:with|for|to see)\s+(Dr\.?)\s+([A-Za-z]+)", text, re.IGNORECASE)
    doctor = None
    if base:
        dr_prefix = base.group(1).replace(".", "")  # normalize 'Dr.'
        first = base.group(2)
        doctor_parts = [dr_prefix, first]

        # 2) Walk forward token-by-token; stop on date/time words
        tail = text[base.end():]
        for m in re.finditer(r"[A-Za-z]+", tail):
            tok = m.group(0)
            if _looks_like_date_or_time_token(tok):
                break
            # Keep adding name tokens (e.g., 'Wick', 'Van', 'Damme')
            doctor_parts.append(tok)

        doctor = " ".join(doctor_parts)

    # -------- Date extraction --------
    date_iso = None
    today = datetime.today().date()
    low = text.lower()

    if "today" in low:
        date_iso = today.strftime("%Y-%m-%d")
    elif "tomorrow" in low:
        date_iso = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        # Try friendly explicit forms: "25 August", "August 25", "Aug 25", etc.
        # I let dateparser do the heavy lifting on the FIRST plausible date phrase.
        # Grab short windows around "on " too, if present.
        # Fallback: search for a month+day or day+month pair.
        date_phrase = None

        # Common explicit patterns
        m = re.search(r"\b(\d{1,2}\s+[A-Za-z]+|[A-Za-z]{3,}\s+\d{1,2})\b", text, re.IGNORECASE)
        if m:
            date_phrase = m.group(1)

        if not date_phrase:
            # e.g., "on 25 Aug", "on Aug 25"
            m = re.search(r"\bon\s+([A-Za-z]{3,}\s+\d{1,2}|\d{1,2}\s+[A-Za-z]{3,})\b", text, re.IGNORECASE)
            if m:
                date_phrase = m.group(1)

        if date_phrase:
            parsed_date = dateparser.parse(date_phrase)
            if parsed_date:
                date_iso = parsed_date.date().strftime("%Y-%m-%d")

    # -------- Time extraction --------
    time_str = None
    m = _TIME_ANYWHERE.search(text)
    if not m:
        # Also support 24h like "20:00"
        m24 = _TIME_24H.search(text)
        if m24:
            raw = f"{m24.group(1)}:{m24.group(2)}"
            parsed_time = dateparser.parse(raw)
            if parsed_time:
                time_str = parsed_time.strftime("%I:%M %p")
    else:
        raw = m.group(1).replace(".", "").lower()
        parsed_time = dateparser.parse(raw)
        if parsed_time:
            time_str = parsed_time.strftime("%I:%M %p")

    return {
        "doctor": doctor,
        "date": date_iso,
        "time": time_str,
    }


def detect_intent(user_message):
    """
    Detects user intent in a flexible way using keywords.
    Handles booking, cancellation, viewing appointments, greetings.
    Not case-sensitive.
    """
    msg_lower = user_message.lower()

    # ---------- View Appointments ----------
    view_keywords = [
        "view", "show", "see", "my appointments", "already booked", "appointments list",
        "check appointment", "current appointment"
    ]
    if any(word in msg_lower for word in view_keywords):
        if "appointment" in msg_lower or "appointments" in msg_lower:
            return "view_appointment"
    
    # ---------- Booking Intent ----------
    booking_keywords = [
        "book", "appointment", "slot", "schedule", "reserve", "meeting", "consultation"
    ]
    if any(word in msg_lower for word in booking_keywords):
        return "booking"

    # ---------- Cancellation Intent ----------
    cancellation_keywords = [
        "cancel", "remove", "delete", "rescind", "abort", "stop appointment"
    ]
    if any(word in msg_lower for word in cancellation_keywords):
        return "cancellation"


    # ---------- Greeting ----------
    greeting_keywords = [
        "hi", "hello", "hey", "good morning", "good evening", "greetings"
    ]
    if any(word in msg_lower for word in greeting_keywords):
        return "greeting"

    # ---------- Fallback ----------
    return "fallback"
