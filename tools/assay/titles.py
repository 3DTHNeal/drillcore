"""Titles and credentials put together from real words. A text can join words its evidence uses into a title the
evidence never gives: "Senior Principal Firmware Engineer" from a senior engineer and a principal one, or "Director of
Product Engineering" from a director of engineering and a product manager. Every word is real, so a check that reads
words one at a time passes it.

So a title in the text judged has to be one title of the evidence, read whole. It may leave words of that title out, as
"Senior Engineer" does of "Senior Software Engineer", but never a word that makes the title less than it sounds
without it ("Assistant", "Deputy", "Vice", "Acting" and the like), and it may never take words from two titles.

In the text judged, a title is a run of capitalized words that ends in a word for a role (Engineer, Director, Officer
and so on), with what follows "of" or "for" after it, as in "Director of Engineering". A credential is a run that opens
with Certified, Chartered, Licensed, Registered or Accredited, and has to appear in the evidence word for word. One word
alone counts only away from the start of a sentence, where its capital marks it as a title: "promoted to Director".
The first word of a sentence is capitalized anyway, so one that no title uses, such as "Led", is read as not part of
the title. In the evidence, titles are read in any case, since a source may write "promoted to senior engineer".
"""
import re
from dataclasses import dataclass

from .findings import Finding

# Words that name a role, in the singular. A title ends in one.
ROLES = frozenset({
    "accountant", "administrator", "adviser", "advisor", "agent", "analyst", "architect", "attorney", "auditor", "author",
    "chair", "chairman", "chairperson", "chairwoman", "chancellor", "chemist", "clerk", "coach", "commissioner",
    "comptroller", "consultant", "controller", "coordinator", "counsel", "counselor", "designer", "developer", "director",
    "economist", "editor", "engineer", "executive", "fellow", "founder", "governor", "head", "instructor", "investigator",
    "lawyer", "lead", "lecturer", "librarian", "manager", "master", "member", "minister", "nurse", "officer", "operator",
    "owner", "partner", "pharmacist", "physician", "physicist", "planner", "president", "producer", "professional",
    "professor", "programmer", "psychologist", "recruiter", "representative", "researcher", "scientist", "secretary",
    "specialist", "steward", "strategist", "superintendent", "supervisor", "surgeon", "technician", "technologist",
    "tester", "trainer", "treasurer", "trustee", "writer",
})
# Words that make a title less than it sounds without them. A text may not leave one out of the title it gives.
LESSER = frozenset({
    "acting", "adjunct", "apprentice", "aspiring", "assistant", "associate", "candidate", "co", "deputy", "honorary",
    "intern", "interim", "junior", "provisional", "sub", "trainee", "under", "vice",
})
# Words that rank a title, so a sentence that opens with one opens with its title: "Senior Engineer at Acme".
RANKS = frozenset({"chief", "distinguished", "executive", "general", "head", "lead", "managing", "master", "principal",
                   "senior", "staff"})
# What opens a credential.
OPENERS = frozenset({"accredited", "certified", "chartered", "licensed", "registered"})
# Short forms, read as the words they stand for.
SHORT = {"sr": ("senior",), "snr": ("senior",), "jr": ("junior",), "asst": ("assistant",), "assoc": ("associate",),
         "mgr": ("manager",), "vp": ("vice", "president"), "svp": ("senior", "vice", "president"),
         "evp": ("executive", "vice", "president"), "avp": ("assistant", "vice", "president")}
# Words that join the parts of one title: "Director of Sales and Marketing", "Head of the Platform Team".
CONNECTORS = frozenset({"of", "for", "and", "&", "the"})
TAIL = frozenset({"of", "for"})
# In the evidence, where the words before a role stop being part of its title.
STOP = frozenset({
    "a", "an", "the", "as", "at", "to", "of", "for", "in", "on", "and", "or", "but", "nor", "was", "is", "were", "are",
    "be", "been", "being", "became", "become", "becomes", "named", "promoted", "appointed", "hired", "joined", "served",
    "serves", "serving", "worked", "works", "working", "work", "led", "leads", "leading", "her", "his", "their", "our",
    "my", "its", "your", "from", "with", "by", "who", "whom", "which", "that", "this", "these", "those", "then", "now",
    "after", "before", "into", "while", "when", "where", "she", "he", "they", "i", "we", "you", "it", "new", "also", "not",
})
TAIL_STOP = STOP - {"and", "the"}
REACH = 6

# A word, or an ampersand on its own. Letters joined by an ampersand with no space are one word, as R&D and M&A are.
WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#'’]*(?:&[A-Za-z][A-Za-z0-9]*)*|&")
# What a role word describes when a degree or a course follows it, as "Executive" does in "Executive MBA" or "Executive
# Education": no one holds that as a title.
DEGREES = frozenset({"mba", "emba", "msc", "ms", "ma", "mfa", "mpa", "mph", "phd", "dba", "degree", "diploma", "certificate",
                     "program", "programme", "programs", "programmes", "course", "courses", "education", "master's",
                     "masters", "doctorate", "school", "class", "cohort"})
# What may stand between two words of one title: spaces, or a hyphen, as in Co-Founder. A dash with spaces around it
# sets a title apart from what follows: "Senior Engineer - Acme".
JOINED = re.compile(r"[^\S\n]+|[-‐‑]")
# What ends a sentence, or a cell of a table, before a word.
BREAK = re.compile(r"[.!?:;|•]")


@dataclass(frozen=True)
class Title:
    """A title as the check compares it: the words before its role, the role in the singular, and what follows "of"
    or "for" after it, all in lowercase."""
    words: tuple[str, ...]
    role: str
    tail: tuple[str, ...] = ()

    def named(self) -> str:
        return " ".join((*self.words, self.role, *(("of", *self.tail) if self.tail else ())))


@dataclass(frozen=True)
class Held:
    """The titles an evidence text gives, read once so that many texts can be judged against it."""
    titles: tuple[Title, ...]
    # Every word of the evidence in lowercase, one space apart, with a space at each end, for a credential's words.
    words: str
    # Every word that stands before a role in some title of the evidence.
    title_words: frozenset[str]


@dataclass(frozen=True)
class _Word:
    word: str       # in lowercase, a short form read as its first word
    start: int
    end: int
    capital: bool   # written with a capital
    joined: bool    # joined to the word before it as words of one title are
    opens: bool     # first in its sentence, line or table cell


def _words(text: str) -> list[_Word]:
    """Every word of a text, short forms written out."""
    found: list[_Word] = []
    last = 0
    previous = ""
    for match in WORD.finditer(text):
        gap = text[last:match.start()]
        raw = match.group(0)
        word = raw.lower().strip("'’")
        word = word[:-2] if word.endswith(("'s", "’s")) else word
        abbreviated = previous in SHORT and gap.startswith(".") and JOINED.fullmatch(gap[1:]) is not None
        joined = bool(found) and "\n" not in gap and (JOINED.fullmatch(gap) is not None or abbreviated)
        opens = not found or "\n" in gap or (BREAK.search(gap) is not None and not abbreviated)
        for at, part in enumerate(SHORT.get(word, (word,))):
            found.append(_Word(part, match.start(), match.end(), raw[0].isupper() or raw == "&", joined or at > 0,
                               opens and at == 0))
        previous = word
        last = match.end()
    return found


def _role(word: str) -> str:
    """A word's role in the singular, or "" when it names none."""
    if word in ROLES:
        return word
    if word.endswith("ies") and word[:-3] + "y" in ROLES:
        return word[:-3] + "y"
    if word.endswith("s") and word[:-1] in ROLES:
        return word[:-1]
    return ""


def held_titles(evidence: str) -> Held:
    """The titles an evidence text gives, in any case. Before each role, the words that run back to it with nothing
    but a space or hyphen between are its title, up to a word that can't be part of one, such as "the" or "was"."""
    words = _words(evidence)
    titles: list[Title] = []
    for at, word in enumerate(words):
        role = _role(word.word)
        if not role:
            continue
        before: list[str] = []
        back = at
        while back > 0 and words[back].joined and len(before) < REACH and words[back - 1].word not in STOP:
            back -= 1
            before.insert(0, words[back].word)
        tail: list[str] = []
        ahead = at + 1
        if ahead < len(words) and words[ahead].joined and words[ahead].word in TAIL:
            ahead += 1
            while (ahead < len(words) and words[ahead].joined and words[ahead].word not in TAIL_STOP
                   and len(tail) < REACH):
                if words[ahead].word not in CONNECTORS:
                    tail.append(words[ahead].word)
                ahead += 1
        titles.append(Title(tuple(before), role, tuple(tail)))
    return Held(tuple(dict.fromkeys(titles)), " " + " ".join(word.word for word in words) + " ",
                frozenset(word for title in titles for word in title.words))


def _subsequence(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    rest = iter(long)
    return all(word in rest for word in short)


def _holds(title: Title, held: Held) -> bool:
    for given in held.titles:
        if (given.role == title.role and _subsequence(title.words, given.words) and _subsequence(title.tail, given.tail)
                and all(word in title.words for word in given.words if word in LESSER)):
            return True
    return False


@dataclass(frozen=True)
class _Claimed:
    words: list[_Word]   # the title's words as the text writes them, from its first to the last of its tail
    core: int            # how many of them come before "of" or "for"
    credential: bool


def _runs(text: str) -> list[list[_Word]]:
    """Runs of capitalized words, with the words that join the parts of one title allowed between them."""
    runs: list[list[_Word]] = []
    run: list[_Word] = []
    for word in _words(text):
        joins = word.word in CONNECTORS and (word.word != "&" or bool(run))
        if run and word.joined and not word.opens and (word.capital or joins):
            run.append(word)
            continue
        if run:
            runs.append(run)
        run = [word] if word.capital and word.word not in CONNECTORS else []
    if run:
        runs.append(run)
    for at, found in enumerate(runs):
        while found and found[-1].word in CONNECTORS:
            found.pop()
        runs[at] = found
    return [found for found in runs if found]


def _claimed(text: str) -> list[_Claimed]:
    """The titles and credentials a text gives, as runs of capitalized words."""
    found: list[_Claimed] = []
    for run in _runs(text):
        start = 0
        while start < len(run):
            core = start
            while core < len(run) and run[core].word not in CONNECTORS:
                core += 1
            end = core
            if core < len(run) and run[core].word in TAIL:
                end = len(run)
            words = run[start:end]
            last = run[core - 1].word if core > start else ""
            # A title can run straight into a name: "Chief Financial Officer Jane Roe". Two words or more that end in a
            # role are read as the title, but one alone isn't, since "Head Office" names no one.
            named = next((at for at in range(core - 1, start, -1) if _role(run[at].word) and not (at + 1 < len(run) and run[at + 1].word in DEGREES)), None)
            if core > start and _role(last):
                found.append(_Claimed(words, core - start, False))
            elif core - start >= 2 and run[start].word in OPENERS:
                found.append(_Claimed(run[start:core], core - start, True))
            elif named is not None:
                found.append(_Claimed(run[start:named + 1], named + 1 - start, False))
            start = end + 1 if end < len(run) else end
            if end == core:  # A run that goes on after "and" or "the" starts again after it.
                start = core + 1
    return found


def _title(words: list[_Word], core: int) -> Title:
    return Title(tuple(word.word for word in words[:core - 1]), _role(words[core - 1].word),
                 tuple(word.word for word in words[core + 1:] if word.word not in CONNECTORS))


def title_findings(text: str, evidence: str | Held) -> list[Finding]:
    """Each title or credential in the text that isn't one the evidence gives, read whole, in the order they stand."""
    held = evidence if isinstance(evidence, Held) else held_titles(evidence)
    findings: list[Finding] = []
    for claimed in _claimed(text):
        words, core = claimed.words, claimed.core
        if claimed.credential:
            if f" {' '.join(word.word for word in words)} " in held.words:
                continue
            kind, named = "credential", " ".join(word.word for word in words)
        else:
            title = _title(words, core)
            # The first word of a sentence is capitalized anyway. One that no title uses is read as not part of it.
            first = words[0]
            loose = first.opens and core > 1 and first.word not in held.title_words | LESSER | RANKS | OPENERS
            if loose:
                words, core = words[1:], core - 1
                title = _title(words, core)
            if (core == 1 and not title.tail and words[0].opens) or _holds(title, held):
                continue
            kind, named = "title", title.named()
        findings.append(Finding("titles", kind, named, text[words[0].start:words[-1].end], words[0].start, words[-1].end))
    return findings


def title_errors(label: str, text: str, evidence: str | Held, where: str) -> list[str]:
    """The titles and credentials in the text that the evidence doesn't give. `where` ends the message, saying what
    they're missing from, such as "not in the sources"."""
    found = title_findings(text, evidence)
    if not found:
        return []
    named = ", ".join(dict.fromkeys(repr(finding.text) for finding in found))
    return [f"{label} gives titles {where}, put together from words that are: {named}. Use a title as the sources give it."]
