import json
from pathlib import Path
from datetime import datetime, date
import random
import calendar
from typing import Dict, List, Tuple

import streamlit as st

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "journal_entries.json"

DISCLAIMER = (
    "Disclaimer: This tool isS is observational only and does NOT provide diagnoses, "
    "medical advice, medication advice, or emergency services."
)

# Heuristic keyword lists (observational only).
HIGH_ENERGY = [
    "energized", "productive", "excited", "motivated", "great", "amazing", "happy", "confident",
    "focused", "uplifted", "optimistic", "restless", "wired", "invincible", "talkative",
    "racing thoughts", "euphoric", "impulsive"
]
LOW_ENERGY = [
    "tired", "exhausted", "down", "sad", "low", "unmotivated", "stressed", "anxious",
    "overwhelmed", "hopeless", "burnt", "burned", "drained", "numb", "empty", "isolated",
    "worthless", "no energy", "can't get out of bed"
]

# Expanded pools to reduce repetition.
FOLLOWUPS = {
    "high energy": [
        "What helped you feel energized today?",
        "What did you do that you'd like to repeat tomorrow?",
        "Were there any moments that felt especially meaningful?",
        "What was your sleep like recently, and did it affect your energy today?",
        "Did your energy feel steady or spiky today? What do you think influenced that?",
        "What boundaries or pacing might help you keep this energy sustainable?",
        "What did you say 'yes' to today that you want to keep saying yes to?",
        "What did you say 'no' to today that protected your time or wellbeing?",
        "If you could channel this energy into one small priority tomorrow, what would it be?",
        "What support (people, routines, environment) helped you feel this way?"
    ],
    "low energy": [
        "What felt hardest today, and what felt even slightly easier?",
        "Did anything help your mood or energy, even a little?",
        "What kind of support or rest would feel helpful right now?",
        "Were there specific triggers or stressors that stood out today?",
        "What did your body seem to need today (sleep, food, movement, quiet)?",
        "If you could do one gentle thing for yourself tomorrow, what would it be?",
        "Who (or what) helped you feel even slightly less alone today?",
        "What thoughts kept showing up today, and how did you respond to them?",
        "What would you want a close friend to say to you about today?",
        "What is one small task you could simplify or postpone to reduce pressure?"
    ],
    "neutral": [
        "What stood out to you today?",
        "If today had a theme, what would it be?",
        "What do you want to pay attention to tomorrow?",
        "What did you do today that supported your wellbeing (even in a small way)?",
        "What drained you today, and what restored you?",
        "What emotion showed up the most today, even if it was subtle?",
        "What's one thing you're grateful for from today (big or small)?",
        "What's one thing you wish had gone differently today?",
        "What did you learn about yourself today?",
        "What would make tomorrow feel 10% better?"
    ],
}

MOOD_CODES = {"high energy": "H", "low energy": "L", "neutral": "N"}


def normalize_entries(entries: List[dict]) -> List[dict]:
    """Backwards-compatible normalization for older saved entries."""
    out: List[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue

        created_at = e.get("created_at") or e.get("timestamp")
        if not created_at:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        e["created_at"] = created_at

        entry_date = e.get("entry_date")
        if not entry_date:
            if isinstance(created_at, str) and len(created_at) >= 10:
                entry_date = created_at[:10]
            else:
                entry_date = date.today().isoformat()
        e["entry_date"] = entry_date

        if "mood" not in e:
            e["mood"] = "neutral"
        if "text" not in e:
            e["text"] = ""

        out.append(e)
    return out


def load_entries() -> List[dict]:
    if DATA_FILE.exists():
        try:
            entries = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                return normalize_entries(entries)
        except Exception:
            return []
    return []


def save_entries(entries: List[dict]) -> None:
    DATA_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def classify_mood(text: str) -> str:
    t = text.lower()
    high = sum(1 for w in HIGH_ENERGY if w in t)
    low = sum(1 for w in LOW_ENERGY if w in t)
    if high > low and high > 0:
        return "high energy"
    if low > high and low > 0:
        return "low energy"
    return "neutral"


def pick_followup(mood: str, entries: List[dict]) -> str:
    """
    Ensures a new prompt each save by:
    - preferring prompts not used before for that mood
    - avoiding repeating the immediately previous prompt globally
    """
    pool = FOLLOWUPS[mood]
    used_for_mood = [e.get("followup") for e in entries if e.get("mood") == mood and e.get("followup")]

    candidates = [q for q in pool if q not in used_for_mood]
    if not candidates:
        candidates = pool[:]  # reset after exhausting the pool

    last = st.session_state.get("last_followup")
    if last in candidates and len(candidates) > 1:
        candidates = [q for q in candidates if q != last]

    q = random.choice(candidates)
    st.session_state["last_followup"] = q
    return q


def daily_moods(entries: List[dict]) -> Dict[str, str]:
    """Map YYYY-MM-DD -> mood using the most recently saved entry for that date."""
    best: Dict[str, Tuple[str, str]] = {}
    for e in entries:
        d = e.get("entry_date")
        if not d:
            continue
        created_at = e.get("created_at", "")
        mood = e.get("mood", "neutral")
        if d not in best or created_at >= best[d][0]:
            best[d] = (created_at, mood)
    return {d: mood for d, (_, mood) in best.items()}


def month_calendar_block(year: int, month: int, day_to_mood: Dict[str, str]) -> str:
    cal = calendar.Calendar(firstweekday=0)  # Monday
    lines: List[str] = []
    lines.append(f"{calendar.month_name[month]} {year}")
    lines.append("Mo Tu We Th Fr Sa Su")

    for week in cal.monthdayscalendar(year, month):
        cells: List[str] = []
        for day in week:
            if day == 0:
                cells.append("   ")
            else:
                dstr = f"{year:04d}-{month:02d}-{day:02d}"
                mood = day_to_mood.get(dstr)
                code = MOOD_CODES.get(mood, " ") if mood else " "
                cells.append(f"{day:02d}{code}")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def calendar_blocks(day_to_mood: Dict[str, str]) -> str:
    if not day_to_mood:
        return "No dated entries yet."

    months = sorted({(int(d[:4]), int(d[5:7])) for d in day_to_mood.keys()})
    blocks: List[str] = []
    blocks.append("Mood calendar (H=high energy, L=low energy, N=neutral; blank=no entry)")
    blocks.append("")
    for (y, m) in months:
        blocks.append(month_calendar_block(y, m, day_to_mood))
        blocks.append("")
    return "\n".join(blocks).rstrip()


def compute_streaks(day_to_mood: Dict[str, str]) -> List[Tuple[str, str, str, int]]:
    """Return streaks (start_date, end_date, mood, length) for consecutive days with entries."""
    if not day_to_mood:
        return []
    days = sorted(date.fromisoformat(d) for d in day_to_mood.keys())
    streaks: List[Tuple[str, str, str, int]] = []

    start = days[0]
    prev = days[0]
    current_mood = day_to_mood[start.isoformat()]
    length = 1

    for d in days[1:]:
        mood = day_to_mood[d.isoformat()]
        if (d - prev).days == 1 and mood == current_mood:
            length += 1
        else:
            streaks.append((start.isoformat(), prev.isoformat(), current_mood, length))
            start = d
            current_mood = mood
            length = 1
        prev = d

    streaks.append((start.isoformat(), prev.isoformat(), current_mood, length))
    return streaks


def make_report(entries: List[dict]) -> str:
    day_to_mood = daily_moods(entries)
    streaks = compute_streaks(day_to_mood)

    lines: List[str] = []
    lines.append("OBSERVATIONAL JOURNAL SUMMARY (NON-DIAGNOSTIC)")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    lines.append("Note: 'high energy' / 'low energy' labels are heuristic keyword matches and are NOT a")
    lines.append("diagnosis of manic, hypomanic, or depressive episodes. Please interpret with a clinician.")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    counts_by_day = {"high energy": 0, "low energy": 0, "neutral": 0}
    for mood in day_to_mood.values():
        counts_by_day[mood] = counts_by_day.get(mood, 0) + 1

    lines.append("Mood distribution (by day):")
    for k, v in counts_by_day.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    if streaks:
        longest = sorted(streaks, key=lambda x: x[3], reverse=True)[:10]
        lines.append("Mood streaks (consecutive days with the same mood label):")
        for s, e, mood, n in longest:
            span = s if s == e else f"{s} to {e}"
            lines.append(f"- {span}: {mood} ({n} day{'s' if n != 1 else ''})")
        lines.append("")
    else:
        lines.append("Mood streaks: none yet (no dated entries).")
        lines.append("")

    lines.append(calendar_blocks(day_to_mood))
    lines.append("")

    lines.append("Most recent entries:")
    for e in entries[-10:]:
        lines.append("")
        lines.append(
            f"[entry_date={e.get('entry_date','')} | saved_at={e.get('created_at','')}] mood={e.get('mood','')}"
        )
        lines.append(e.get("text", ""))

    return "\n".join(lines)


# --- UI ---
st.set_page_config(page_title="BPD Support Journal", layout="centered")
st.title("BPD Support Journal (Prototype)")
st.caption(DISCLAIMER)

entries = load_entries()

st.subheader("New entry")

entry_day = st.date_input(
    "Entry date (required)",
    value=date.today(),
    max_value=date.today(),
    help="Pick the day this entry is ABOUT. You can backdate to add entries for past days.",
)

text = st.text_area("Write your journal entry", height=160, placeholder="Type here...")

col1, col2 = st.columns([1, 1])
with col1:
    submitted = st.button("Save entry", type="primary")
with col2:
    clear = st.button("Clear all saved entries")

if clear:
    save_entries([])
    st.success("Cleared saved entries.")
    st.rerun()

if submitted:
    if not text.strip():
        st.warning("Please write something before saving.")
    else:
        mood = classify_mood(text)
        followup = pick_followup(mood, entries)

        entry = {
            "entry_date": entry_day.isoformat(),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": text.strip(),
            "mood": mood,
            "followup": followup,
        }
        entries.append(entry)
        save_entries(entries)

        st.success(f"Saved. Mood (observational): {mood} for {entry_day.isoformat()}")
        st.info(f"Follow-up question: {followup}")

st.divider()

st.subheader("Mood calendar")
day_to_mood = daily_moods(entries)
st.code(calendar_blocks(day_to_mood), language="text")

st.subheader("History")
if not entries:
    st.write("No saved entries yet.")
else:
    # Most recent first by save-time
    entries_sorted = sorted(entries, key=lambda e: (e.get("created_at", ""), e.get("entry_date", "")))
    for e in reversed(entries_sorted[-50:]):
        title = f"{e.get('entry_date','')}  |  {e.get('mood','')}  |  saved {e.get('created_at','')}"
        with st.expander(title):
            st.write(e.get("text", ""))
            if e.get("followup"):
                st.caption(f"Follow-up shown: {e.get('followup')}")

st.subheader("Therapist report")
report_text = make_report(entries)
st.download_button(
    label="Download report (.txt)",
    data=report_text,
    file_name="journal_report.txt",
    mime="text/plain",
)
