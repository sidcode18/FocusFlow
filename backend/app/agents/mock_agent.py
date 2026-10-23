"""Mock agent: deterministic rule-based NLU used when AWS credentials are absent.

This is NOT AI. Responses produced in mock mode are always labeled mode='mock'
by the API layer so the UI can display a MOCK badge and never pass this output
off as real Bedrock reasoning.
"""
import re
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings
from app.agents.tools import execute_tool

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
            "saturday": 5, "sunday": 6}

CREATE_VERBS = r"^(?:please\s+)?(?:can you\s+)?(?:add|create|make|new task[:\s]|remind me to|i need to|i have to|schedule|put)\s+"
TITLE_TRIM = r"\s*(?:by|before|due|at|on|around)\s+.*$"


def _parse_timephrase(text: str) -> tuple[Optional[datetime], str]:
    """Extract a deadline from text. Returns (deadline_or_None, cleaned_text)."""
    now = datetime.now().replace(second=0, microsecond=0)
    low = text.lower()

    m = re.search(r"in\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?)", low)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = timedelta(minutes=n) if unit.startswith(("m", "h") and unit[0] == "m") else (
            timedelta(hours=n) if unit[0] == "h" else timedelta(days=n))
        return now + delta, re.sub(r"in\s+\d+\s*(minutes?|mins?|hours?|hrs?|days?)", "", text, flags=re.I)

    day = None
    if re.search(r"\btoday\b|\btonight\b", low):
        day = now
    elif re.search(r"\btomorrow\b", low):
        day = now + timedelta(days=1)
    else:
        m = re.search(r"\b(?:next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", low)
        if m:
            target = WEEKDAYS[m.group(1)]
            delta = (target - now.weekday()) % 7
            if delta == 0:
                delta = 7
            day = now + timedelta(days=delta)

    hour = None
    minute = 0
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
    else:
        m = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\b", low)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)

    if day is None and hour is None:
        return None, text
    if day is None:
        day = now
    if hour is None:
        hour, minute = settings.work_end, 0
    deadline = day.replace(hour=hour, minute=minute)
    if deadline < now:
        deadline += timedelta(days=1)

    cleaned = re.sub(
        r"\b(?:by|before|due|at|on|around)\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*)?"
        r"(?:today|tonight|tomorrow|next\s+)?"
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?"
        r"(?:at\s+\d{1,2}(?::\d{2})?)?",
        "", text, flags=re.I,
    )
    cleaned = re.sub(r"\s*(?:\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*$", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
    return deadline, cleaned


def _find_task(title_fragment: str) -> Optional[dict]:
    from app.services.tasks import list_tasks
    frag = title_fragment.strip().lower().strip("'\"")
    if not frag:
        return None
    candidates = [t for t in list_tasks() if frag in t["title"].lower()]
    if not candidates:
        # token overlap fallback
        toks = set(frag.split())
        best, best_score = None, 0
        for t in list_tasks():
            score = len(toks & set(t["title"].lower().split()))
            if score > best_score:
                best, best_score = t, score
        return best if best_score >= max(1, len(toks) - 1) else None
    candidates.sort(key=lambda t: (t["status"] == "done", -len(t["title"])))
    return candidates[0]


def _duration_hint(text: str) -> int:
    m = re.search(r"(\d+)\s*(?:minutes?|mins?)\b", text.lower())
    if m:
        return max(5, min(600, int(m.group(1))))
    m = re.search(r"(\d+)\s*hours?\b", text.lower())
    if m:
        return max(5, min(600, int(m.group(1)) * 60))
    return 30


def _handle_clause(clause: str, actions: list[dict], notes: list[str]) -> None:
    clause = clause.strip(" ,.;")
    if not clause:
        return
    low = clause.lower()

    # Replan / missed
    if re.search(r"\b(replan|re-plan|reschedule my (day|missed|tasks)|i (missed|didn't finish|did not finish)|fell behind)\b", low):
        r = execute_tool("replan_missed", {})
        actions.append(r)
        notes.append(r.get("summary", ""))
        return

    # Progress
    if re.search(r"\b(how am i doing|progress|status update|stats|summary of my (day|tasks))\b", low):
        r = execute_tool("get_progress", {})
        actions.append(r)
        notes.append(r.get("summary", ""))
        return

    # Generate schedule
    if re.search(r"\b(plan my (day|week)|generate (a )?schedule|build (a )?schedule|schedule (my|these) (day|tasks))\b", low):
        r = execute_tool("generate_schedule", {})
        actions.append(r)
        notes.append(r.get("summary", ""))
        return

    # Complete
    m = re.search(r"^(?:i\s+)?(?:'ve\s+)?(?:finished|completed|done with|done)\s+(?:the\s+|my\s+)?(.+)$", low) or \
        re.search(r"^(?:complete|mark)\s+(?:the\s+|my\s+)?(.+?)\s*(?:as\s+done)?$", low)
    if m:
        task = _find_task(m.group(1))
        if task:
            r = execute_tool("complete_task", {"task_id": task["id"]})
            actions.append(r)
            notes.append(r.get("summary") or r.get("error", ""))
        else:
            notes.append(f"I couldn't find a task matching '{m.group(1)}'.")
        return

    # Delete
    m = re.search(r"^(?:delete|remove|cancel|drop)\s+(?:the\s+|my\s+)?(?:task\s+)?(.+)$", low)
    if m:
        task = _find_task(m.group(1))
        if task:
            r = execute_tool("delete_task", {"task_id": task["id"]})
            actions.append(r)
            notes.append(r.get("summary") or r.get("error", ""))
        else:
            notes.append(f"I couldn't find a task matching '{m.group(1)}' to delete.")
        return

    # Reschedule explicit
    m = re.search(r"^(?:reschedule|move|push)\s+(?:the\s+|my\s+)?(.+?)\s+to\s+(.+)$", low)
    if m:
        task = _find_task(m.group(1))
        if task:
            new_deadline, cleaned = _parse_timephrase(m.group(2))
            args: dict = {"task_id": task["id"]}
            if new_deadline:
                args["new_deadline"] = new_deadline.isoformat(timespec="seconds")
            else:
                args["new_start"] = (datetime.now() + timedelta(hours=1)).replace(
                    second=0, microsecond=0).isoformat(timespec="seconds")
            r = execute_tool("reschedule_task", args)
            actions.append(r)
            notes.append(r.get("summary") or r.get("error", ""))
        else:
            notes.append(f"I couldn't find a task matching '{m.group(1)}' to reschedule.")
        return

    # Create (default). Strip leading verbs and time phrases from the title.
    title = re.sub(CREATE_VERBS, "", clause, flags=re.I).strip()
    title = re.sub(r"^(?:task|to)\s+", "", title, flags=re.I)
    deadline, cleaned = _parse_timephrase(title)
    title = re.sub(TITLE_TRIM, "", cleaned or title).strip() or cleaned
    if not title:
        notes.append("I couldn't work out a task title from that.")
        return
    args = {"title": title[:200], "duration_minutes": _duration_hint(clause)}
    if deadline:
        args["deadline"] = deadline.isoformat(timespec="seconds")
    r = execute_tool("create_task", args)
    actions.append(r)
    if r.get("ok"):
        notes.append(f"Created '{title}'"
                     + (f" (due {deadline.strftime('%a %b %d %H:%M')})" if deadline else "")
                     + f", {args['duration_minutes']} min.")
    else:
        notes.append(r.get("error", "Create failed."))


def run_mock_agent(message: str) -> dict:
    actions: list[dict] = []
    notes: list[str] = []

    clauses = re.split(r"\s+(?:and then|then|also|and)\s+|;\s*", message, flags=re.I)
    created_any = False
    for clause in clauses:
        before = len([a for a in actions if a.get("ok") and "Created" in (a.get("summary") or "")])
        _handle_clause(clause, actions, notes)
        after = len([a for a in actions if a.get("ok") and "Created" in (a.get("summary") or "")])
        if after > before:
            created_any = True

    # Auto-schedule after new creations (deterministic mock behavior)
    if created_any:
        r = execute_tool("generate_schedule", {})
        actions.append(r)
        notes.append(r.get("summary", ""))

    reply = " ".join(n for n in notes if n).strip()
    if not reply:
        reply = ("I'm running in mock mode (no AWS credentials), so I only understand simple "
                 "requests like: 'add finish deck by friday 5pm', 'done review PR', "
                 "'reschedule expense report to tomorrow 10am', 'replan my day', "
                 "'how am I doing'.")
    return {"reply": reply, "actions": actions, "error": None}
