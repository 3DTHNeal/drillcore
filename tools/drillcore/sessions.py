"""The prompts a person typed in an AI assistant's sessions, read from the assistant's own records of them: Claude
Code's transcripts, one JSON Lines file per session, as it keeps them in a folder for each project. `proof`'s `records`
check holds a log of AI use to them, and the record compiled from that log, when `[[proof.record_logs]]` names the
folder under `sessions`.

A prompt is the text of a message the person sent: a user message of the main conversation (not a sub-agent's), or a
message typed while the assistant was busy, which the transcript keeps as a queued command and may never show as a
message of its own. Left out is what the app or the assistant put into the conversation rather than the person: a block
in angle brackets (a reminder, a task's notice, the context of a page that was open), taken off the front of a message
the person typed after it; a summary written when a session's context was compacted; and the note an interruption
leaves. A prompt one session wrote to start another is kept, since it's what that session was asked, and a log quotes it
too.

A file that can't be read as JSON Lines, and any line of one that isn't a record, is passed over: these are records kept
by another program, and a format it changes shouldn't stop a proof.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

# A block the app or the assistant wrote, at the front of a message: "<context ...>...</context>".
LEADING_BLOCK = re.compile(r"^\s*<(?P<tag>[A-Za-z][\w-]*)\b[^>]*>.*?</(?P=tag)>\s*", re.S)
# A reminder the app appended, wherever it stands.
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
NOT_TYPED = ("[Request interrupted", "Caveat: The messages below were generated")


@dataclass(frozen=True)
class Prompt:
    session: str    # the transcript's file name, without .jsonl
    at: str         # when it was sent, as the transcript gives it (UTC)
    text: str


def typed(text: str) -> str:
    """What the person typed in a message: the blocks in front of it and the reminders in it taken off. Blank when
    there's nothing else, or when what's left is a block the app wrote."""
    text = REMINDER.sub("", text)
    while block := LEADING_BLOCK.match(text):
        text = text[block.end():]
    text = text.strip()
    if text.startswith("<") or text.startswith(NOT_TYPED):
        return ""
    return text


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content
                         if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str))
    return ""


def prompts_of(path: Path) -> list[Prompt]:
    """The prompts of one session's transcript, in the order sent, each once."""
    found: list[Prompt] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("isSidechain") or record.get("isMeta") or record.get("isCompactSummary"):
            continue
        attachment = record.get("attachment")
        if record.get("type") == "attachment" and isinstance(attachment, dict) and attachment.get("type") == "queued_command":
            text = _text(attachment.get("prompt"))
        elif record.get("type") == "user" and isinstance(record.get("message"), dict):
            text = _text(record["message"].get("content"))
        else:
            continue
        text = typed(text)
        key = " ".join(text.split())
        if text and key not in seen:
            seen.add(key)
            found.append(Prompt(path.stem, str(record.get("timestamp", "")), text))
    return found


def read(folder: Path) -> list[Prompt]:
    """Every prompt of the sessions whose transcripts are in a folder, session by session, in the order of the
    sessions' first prompts. A session forked or resumed from another copies its messages, sent at the same moments:
    each is kept once, in the session it was first sent in."""
    sessions = [prompts for path in sorted(folder.glob("*.jsonl")) if (prompts := prompts_of(path))]
    seen: set[tuple[str, str]] = set()
    found = []
    for prompts in sorted(sessions, key=lambda found: found[0].at):
        for prompt in prompts:
            key = (" ".join(prompt.text.split()), prompt.at)
            if key not in seen:
                seen.add(key)
                found.append(prompt)
    return found
