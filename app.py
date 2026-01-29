import json
import random
from pathlib import Path
from datetime import datetime, date, timedelta

import streamlit as st

APP_DIR = Path(__file__).parent
DATA_FILE = APP_DIR / "journal_entries.json"

DISCLAIMER = (
    "Disclaimer: This tool is observational only and does NOT provide diagnoses, "
    "medical advice, medication advice, or emergency services. Any labels such as "
    "'elevated' or 'low' are simple, non-diagnostic descriptions meant to help organize "
    "self-reported entries and share patterns with a clinician."
)

# Keyword-based (very lightweight) classifier for the text notes
HIGH_ENERGY = [
    "energized", "productive", "excited", "motivated", "great", "amazing", "happy", "confident",
    "focused", "uplifted", "optimistic"
]
LOW_ENERGY = [
    "tired", "exhausted", "down", "sad", "low", "unmotivated", "stressed", "anxious",
    "overwhelmed", "hopeless", "burnt", "burned", "drained", "depressed"
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

# "Cycle" tracking is based on a self-reported mood score.
# You can tune these thresholds to match your use case.
ELEVATED_THRESHOLD = 3
LOW_THRESHOLD = -3
MIN_EPISODE_DAYS = 2  # consecutive days above/below threshold to count as a "period"


def load_entries():
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_entries(entries):
    DATA_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def parse_dt(s: str) -> datetime:
    # Expected: "YYYY-MM-DD HH:MM:SS"
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.min


def get_recorded_at(e) -> datetime:
    # New entries use "recorded_at"; older entries used "timestamp"
    if e.get("recorded_at"):
        return parse_dt(e["recorded_at"])
    if e.get("timestamp"):
        return parse_dt(e["timestamp"])
    return datetime.min


def get_entry_date(e) -> date:
    # New entries store an explicit entry_date; older entries can derive from timestamp
    if e.get("entry_date"):
        try:
            return date.fromisoformat(e["entry_date"])
        except Exception:
            pass
    ts = e.get("recorded_at") or e.get("timestamp")
    if ts and len(ts) >= 10:
        try:
            return date.fromisoformat(ts[:10])
        except Exception:
            pass
    return date.today()


def classify_mood(text: str) -> str:
    t = (text or "").lower()
    high = sum(1 for w in HIGH_ENERGY if w in t)
    low = sum(1 for w in LOW_ENERGY if w in t)
    if high > low and high > 0:
        return "high energy"
    if low > high and low > 0:
        return "low energy"
    return "neutral"


def state_from_score(score: int) -> str:
    if score >= ELEVATED_THRESHOLD:
        return "elevated"
    if score <= LOW_THRESHOLD:
        return "low"
    return "stable"


def choose_followup(bucket: str, entries, avoid_last_n: int = 3) -> str:
    """
    Ensures the follow-up prompt changes (won't repeat the most recent prompt,
    and tries not to repeat prompts from the last N entries).
    """
    recent = [e.get("followup") for e in entries if e.get("followup")]
    recent = [q for q in recent if isinstance(q, str) and q.strip()]
    recent = recent[-avoid_last_n:]  # last N prompts

    candidates = [q for q in FOLLOWUPS[bucket] if q not in recent]

    # If we excluded everything, at least avoid the most recent one.
    if not candidates and recent:
        candidates = [q for q in FOLLOWUPS[bucket] if q != recent[-1]]

    # If still empty (shouldn't happen with 3+ prompts), fall back.
    if not candidates:
        candidates = list(FOLLOWUPS[bucket])

    return random.choice(candidates)


def build_daily_series(entries):
    """
    Collapse entries into 1 record per day for cycle tracking.
    If multiple entries exist for a day, we take the latest recorded.
    """
    by_day = {}
    for e in entries:
        d = get_entry_date(e)
        recorded = get_recorded_at(e)
        if d not in by_day or recorded > get_recorded_at(by_day[d]):
            by_day[d] = e

    daily = []
    for d in sorted(by_day.keys()):
        e = by_day[d]
        score = safe_int(e.get("mood_score"), 0)
        daily.append(
            {
                "date": d.isoformat(),
                "mood_score": score,
                "cycle_state": state_from_score(score),
                "keyword_mood": e.get("mood", "neutral"),
            }
        )
    return daily


def compute_periods(daily_rows):
    """
    Find consecutive-day runs of elevated or low states based on mood_score thresholds.
    """
    if not daily_rows:
        return []

    rows = []
    for r in daily_rows:
        try:
            d = date.fromisoformat(r["date"])
        except Exception:
            continue
        score = safe_int(r.get("mood_score"), 0)
        stt = state_from_score(score)
        rows.append((d, score, stt))

    rows.sort(key=lambda x: x[0])
    if not rows:
        return []

    periods = []
    start_d, state, scores = rows[0][0], rows[0][2], [rows[0][1]]
    prev_d = rows[0][0]

    def finalize(seg_start, seg_end, seg_state, seg_scores):
        length = (seg_end - seg_start).days + 1
        if seg_state in ("elevated", "low") and length >= MIN_EPISODE_DAYS:
            periods.append(
                {
                    "state": seg_state,
                    "start": seg_start.isoformat(),
                    "end": seg_end.isoformat(),
                    "days": length,
                    "avg_score": round(sum(seg_scores) / len(seg_scores), 2),
                }
            )

    for d, score, stt in rows[1:]:
        consecutive = (d == prev_d + timedelta(days=1))
        if consecutive and stt == state:
            scores.append(score)
            prev_d = d
        else:
            finalize(start_d, prev_d, state, scores)
            start_d, state, scores = d, stt, [score]
            prev_d = d

    finalize(start_d, prev_d, state, scores)
    return periods


def make_report(entries):
    lines = []
    lines.append("OBSERVATIONAL JOURNAL SUMMARY (NON-DIAGNOSTIC)")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    if not entries:
        lines.append("No entries found.")
        return "\n".join(lines)

    # Date range
    dates = sorted({get_entry_date(e) for e in entries})
    lines.append(f"Entry date range: {dates[0].isoformat()} to {dates[-1].isoformat()}")
    lines.append(f"Total entries: {len(entries)}")
    lines.append("")

    # Keyword mood distribution
    counts = {"high energy": 0, "low energy": 0, "neutral": 0}
    for e in entries:
        m = e.get("mood", "neutral")
        if m not in counts:
            m = "neutral"
        counts[m] += 1

    lines.append("Keyword-based mood distribution (from notes):")
    for k, v in counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    # Cycle tracking summary from mood_score
    daily = build_daily_series(entries)
    periods = compute_periods(daily)

    scores = [safe_int(e.get("mood_score"), 0) for e in entries]
    lines.append("Self-reported mood score summary (e.g., -5 to +5):")
    lines.append(f"- Average score: {round(sum(scores) / max(len(scores), 1), 2)}")
    lines.append(f"- Min/Max score: {min(scores)} / {max(scores)}")
    lines.append("")

    if daily:
        day_counts = {"elevated": 0, "low": 0, "stable": 0}
        for r in daily:
            day_counts[r["cycle_state"]] = day_counts.get(r["cycle_state"], 0) + 1

        lines.append("Day-level cycle states (based on mood score thresholds):")
        for k, v in day_counts.items():
            lines.append(f"- {k}: {v} days")
        lines.append("")

    if periods:
        lines.append(f"Detected elevated/low periods (>= {MIN_EPISODE_DAYS} consecutive days):")
        for p in periods:
            lines.append(f"- {p['state'].upper()}: {p['start']} to {p['end']} ({p['days']} days), avg score {p['avg_score']}")
        lines.append("")
    else:
        lines.append("Detected elevated/low periods: none (insufficient consecutive days above/below thresholds).")
        lines.append("")

    # Recent entries
    lines.append("Most recent entries (latest 10):")
    # Sort by entry_date then recorded_at
    entries_sorted = sorted(entries, key=lambda e: (get_entry_date(e), get_recorded_at(e)), reverse=True)
    for e in entries_sorted[:10]:
        ed = get_entry_date(e).isoformat()
        rec = (e.get("recorded_at") or e.get("timestamp") or "").strip()
        mood = e.get("mood", "neutral")
        score = safe_int(e.get("mood_score"), 0)
        cycle = state_from_score(score)
        followup = e.get("followup", "")
        text = (e.get("text") or "").strip()

        lines.append("")
        lines.append(f"[Entry date: {ed}] recorded_at={rec} | keyword_mood={mood} | mood_score={score} ({cycle})")
        if text:
            lines.append(text)
        else:
            lines.append("(No notes)")
        if followup:
            lines.append(f"Follow-up prompt: {followup}")

    return "\n".join(lines)


# --- UI ---
st.set_page_config(page_title="BPD Support Journal", layout="centered")
st.title("BPD Support Journal (Prototype)")
st.caption(DISCLAIMER)

entries = load_entries()

st.subheader("New entry")

entry_date = st.date_input(
    "Date for this entry",
    value=date.today(),
    max_value=date.today(),
    help="You can backfill by selecting a past date.",
)

mood_score = st.slider(
    "Mood rating (self-report)",
    min_value=-5,
    max_value=5,
    value=0,
    step=1,
    help="Example scale: -5 very low, 0 stable, +5 very elevated/activated. This is not a diagnosis.",
)

text = st.text_area("Notes (optional)", height=140, placeholder="Optional details about your day, sleep, stressors, etc.")

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
    keyword_mood = classify_mood(text)
    cycle_state = state_from_score(int(mood_score))

    # Use mood_score state to pick a prompt bucket (more aligned with cycling),
    # falling back to keyword mood when stable.
    if cycle_state == "elevated":
        bucket = "high energy"
    elif cycle_state == "low":
        bucket = "low energy"
    else:
        bucket = keyword_mood

    followup = choose_followup(bucket, entries)

    entry = {
        # Back-compatible fields
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mood": keyword_mood,

        # New fields
        "entry_date": entry_date.isoformat(),
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "text": (text or "").strip(),
        "mood_score": int(mood_score),
        "cycle_state": cycle_state,
        "followup": followup,
    }

    entries.append(entry)
    save_entries(entries)

    st.success(f"Saved. Keyword mood: {keyword_mood} | Mood score: {mood_score} ({cycle_state})")
    st.info(f"Follow-up question: {followup}")

st.divider()

st.subheader("Cycle tracker (observational)")
daily = build_daily_series(entries)
periods = compute_periods(daily)

if not daily:
    st.write("No entries yet.")
else:
    # Summary
    elevated_days = sum(1 for r in daily if r["cycle_state"] == "elevated")
    low_days = sum(1 for r in daily if r["cycle_state"] == "low")
    stable_days = sum(1 for r in daily if r["cycle_state"] == "stable")

    c1, c2, c3 = st.columns(3)
    c1.metric("Elevated days", elevated_days)
    c2.metric("Low days", low_days)
    c3.metric("Stable days", stable_days)

    if periods:
        st.write(f"Detected elevated/low periods (>= {MIN_EPISODE_DAYS} consecutive days):")
        st.dataframe(periods, use_container_width=True)
    else:
        st.write("No elevated/low periods detected yet (need consecutive days above/below thresholds).")

    st.write("Daily series (latest):")
    st.dataframe(list(reversed(daily[-60:])), use_container_width=True)

st.divider()

st.subheader("History")
if not entries:
    st.write("No saved entries yet.")
else:
    entries_sorted = sorted(entries, key=lambda e: (get_entry_date(e), get_recorded_at(e)), reverse=True)
    for e in entries_sorted[:50]:
        ed = get_entry_date(e).isoformat()
        mood = e.get("mood", "neutral")
        score = safe_int(e.get("mood_score"), 0)
        cycle = state_from_score(score)
        header = f"{ed} | score={score} ({cycle}) | keywords={mood}"
        with st.expander(header):
            st.write((e.get("text") or "").strip() or "(No notes)")
            if e.get("followup"):
                st.caption(f"Follow-up prompt: {e['followup']}")

st.subheader("Therapist report")
report_text = make_report(entries)
st.download_button(
    label="Download report (.txt)",
    data=report_text,
    file_name=f"journal_report_{date.today().isoformat()}.txt",
    mime="text/plain",
)
