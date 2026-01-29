import json
from pathlib import Path
from datetime import datetime
import random

import streamlit as st

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "journal_entries.json"

DISCLAIMER = (
    "Disclaimer: This tool is observational only and does NOT provide diagnoses, "
    "medical advice, medication advice, or emergency services."
)

HIGH_ENERGY = [
    "energized", "productive", "excited", "motivated", "great", "amazing", "happy", "confident",
    "focused", "uplifted", "optimistic"
]
LOW_ENERGY = [
    "tired", "exhausted", "down", "sad", "low", "unmotivated", "stressed", "anxious",
    "overwhelmed", "hopeless", "burnt", "burned", "drained"
]

FOLLOWUPS = {
    "high energy": [
        "What helped you feel energized today?",
        "What did you do that you’d like to repeat tomorrow?",
        "Were there any moments that felt especially meaningful?"
    ],
    "low energy": [
        "What felt hardest today, and what felt even slightly easier?",
        "Did anything help your mood or energy, even a little?",
        "What kind of support or rest would feel helpful right now?"
    ],
    "neutral": [
        "What stood out to you today?",
        "If today had a theme, what would it be?",
        "What do you want to pay attention to tomorrow?"
    ],
}

def load_entries():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_entries(entries):
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

def make_report(entries):
    lines = []
    lines.append("OBSERVATIONAL JOURNAL SUMMARY (NON-DIAGNOSTIC)")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Basic counts
    counts = {"high energy": 0, "low energy": 0, "neutral": 0}
    for e in entries:
        counts[e.get("mood", "neutral")] = counts.get(e.get("mood", "neutral"), 0) + 1

    lines.append("Mood distribution:")
    for k, v in counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    # Recent entries
    lines.append("Most recent entries:")
    for e in entries[-10:]:
        lines.append("")
        lines.append(f"[{e.get('timestamp','')}] mood={e.get('mood','')}")
        lines.append(e.get("text", ""))

    return "\n".join(lines)

# --- UI ---
st.set_page_config(page_title="BPD Support Journal", layout="centered")
st.title("BPD Support Journal (Prototype)")
st.caption(DISCLAIMER)

entries = load_entries()

st.subheader("New entry")
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
        followup = random.choice(FOLLOWUPS[mood])

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "text": text.strip(),
            "mood": mood,
        }
        entries.append(entry)
        save_entries(entries)

        st.success(f"Saved. Mood (observational): {mood}")
        st.info(f"Follow-up question: {followup}")

st.divider()

st.subheader("History")
if not entries:
    st.write("No saved entries yet.")
else:
    for e in reversed(entries[-25:]):
        with st.expander(f"{e['timestamp']}  |  {e['mood']}"):
            st.write(e["text"])

st.subheader("Therapist report")
report_text = make_report(entries)
st.download_button(
    label="Download report (.txt)",
    data=report_text,
    file_name="journal_report.txt",
    mime="text/plain",
)
