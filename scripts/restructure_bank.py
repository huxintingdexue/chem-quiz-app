#!/usr/bin/env python3
"""Turn the raw extracted bank into a practice-friendly one.

Two transformations happen here:

* Judgement items are re-derived from the answer half of the PDF so every
  equation or statement becomes its own question instead of being bundled
  behind a row of brackets.
* Fill-in questions that really ask for numbered options become multiple-choice
  questions whose options are relabelled A/B/C.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pymupdf


ROOT = Path(__file__).resolve().parents[1]
BANK_PATH = ROOT / "public" / "question-bank" / "bank.json"
DEFAULT_PDF = Path(
    "/Users/zhaoguang/.codex/multi-agent-console/attachments/"
    "OQ7qZBMakm9-0faQ94vR-Tgy/三轮复习_基础知识回归_含答案_.pdf"
)

# The answer half of the workbook starts 39 sheets after the question half.
ANSWER_PAGE_OFFSET = 39

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CIRCLED_ORDER = {char: index + 1 for index, char in enumerate(CIRCLED)}
LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
JUDGE_ANSWERS = {"√", "×"}

BLANK_SPAN_RE = re.compile(r'<span class="answer-slot" data-blank-id="[^"]+"></span>')
BLANK_ID_RE = re.compile(r'data-blank-id="([^"]+)"')
JUDGE_MARK_RE = re.compile(r"[（(]\s*([√×])\s*[）)]")
ANY_BRACKET_RE = re.compile(r"[（(]\s*([√×]?)\s*[）)]")
ITEM_START_RE = re.compile(r"(?:[（(]\s*\d{1,2}\s*[）)]|\d{1,2}\s*[．.、])")
JUDGE_CUE_RE = re.compile(r"判断(?:正误|下列[^。；\u221a]{0,60}|：|:)")
LATIN_OPTION_RE = re.compile(r"(?<![A-Za-z])([a-jA-J])\s*[.．、]")

# Pages where the raw fill question only carried the judgement brackets; the
# re-derived questions replace them completely.
BRACKET_ONLY_PAGES = {1, 2}

# Hand-reviewed repairs: the coordinate pass glued the option list into the
# answer text of these questions.
ANSWER_OVERRIDES: dict[str, list[str]] = {
    "p01-q007": ["①②③④⑤⑥⑦⑧", "⑨⑩⑪⑫"],
    "p26-q002": ["含弱离子的盐", "②④⑦⑧", "③⑥", "①⑤"],
}

# Questions whose blank layout itself needed rebuilding.
STEM_OVERRIDES: dict[str, str] = {
    "p01-q007": "6.难溶于水的物质{0}、微溶于水的物质{1}",
}

# Option lists that the coordinate pass dropped together with the stem.
OPTION_OVERRIDES: dict[str, list[str]] = {
    "p01-q007": [
        "BaSO3",
        "CaSO3",
        "BaCO3",
        "CaCO3",
        "AgCl",
        "BaSO4",
        "PbSO4",
        "CuS",
        "CaSO4",
        "Ag2SO4",
        "MgCO3",
        "Ca(OH)2",
    ],
    "p08-q007": ["稀盐酸", "稀硫酸", "浓硫酸", "稀硝酸", "浓硝酸"],
    "p18-q002": ["SO32-", "ClO4-", "NO2-", "ClO3-"],
}


def normalize(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text).lower()


def similar(left: str, right: str) -> bool:
    first, second = normalize(left), normalize(right)
    if not first or not second:
        return False
    if first == second:
        return True
    if min(len(first), len(second)) >= 8 and (first in second or second in first):
        return True
    return SequenceMatcher(None, first, second).ratio() >= 0.86


def blank_span(slot_id: str) -> str:
    return f'<span class="answer-slot" data-blank-id="{slot_id}"></span>'


def plain_from_prompt(markup: str) -> str:
    text = BLANK_SPAN_RE.sub("{{blank}}", markup)
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def answer_letter(answer: str, option_count: int) -> str | None:
    """Map numbered answers such as the circled digits onto A/B/C letters."""
    text = answer.strip()
    if not text:
        return None
    upper = text.upper()
    if text.isalpha() and all(char in LATIN[:option_count] for char in upper):
        letters = sorted(set(upper))
        return "".join(letters) if len(letters) == len(text) else None
    if all(char in CIRCLED_ORDER for char in text):
        indexes = [CIRCLED_ORDER[char] for char in text]
    elif text.isdigit():
        indexes = [int(char) for char in text]
    else:
        return None
    if any(index < 1 or index > option_count for index in indexes):
        return None
    return "".join(LATIN[index - 1] for index in sorted(set(indexes)))


def circled_items(text: str) -> tuple[int, list[str]] | None:
    """Split a trailing numbered option list into its item texts."""
    positions = [(index, char) for index, char in enumerate(text) if char in CIRCLED_ORDER]
    if len(positions) < 2:
        return None
    numbers = [CIRCLED_ORDER[char] for _, char in positions]
    if numbers != list(range(1, len(numbers) + 1)):
        return None
    items: list[str] = []
    for index, (position, _) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        body = text[position + 1 : end].strip().strip("、,，;；。 ")
        items.append(body)
    if any(not body for body in items):
        return None
    return positions[0][0], items


def latin_items(text: str) -> tuple[int, list[str]] | None:
    matches = list(LATIN_OPTION_RE.finditer(text))
    if len(matches) < 2:
        return None
    labels = [match.group(1).lower() for match in matches]
    expected = [chr(ord("a") + offset) for offset in range(len(labels))]
    if labels != expected:
        return None
    items: list[str] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip().strip("、,，;；。 ")
        items.append(body)
    if any(not body for body in items):
        return None
    return matches[0].start(), items


MARKER_TAIL_RE = re.compile(r"(?:[①-⑳]|[A-Za-z]\s*[.．、])\s*$")


def marker_start(text: str, body: str, fallback: int) -> int:
    """Find where the marker of the first option begins inside the stem."""
    index = text.find(body)
    if index <= 0:
        return fallback
    marker = MARKER_TAIL_RE.search(text[:index])
    if marker:
        return marker.start()
    return index


def option_list_start(text: str, items: list[str], kind: str, fallback: int) -> int:
    if kind == "circled":
        head = next(
            (char for char in text if char in CIRCLED_ORDER),
            "",
        )
        index = text.find(head) if head else -1
        return index if index >= 0 else fallback
    return marker_start(text, items[0], fallback)


def clean_statement(raw: str) -> tuple[str, str]:
    """Return cue and statement for text that precedes a judgement bracket."""
    cue = None
    cues = list(JUDGE_CUE_RE.finditer(raw))
    if cues:
        cue = cues[-1]
    offset = cue.end() if cue else 0
    tail = raw[offset:]
    markers = list(ITEM_START_RE.finditer(tail))
    if markers:
        marker = markers[-1]
        context = raw[offset : offset + marker.start()].strip() if cue else ""
        body = tail[marker.start() :]
    else:
        context = tail.strip() if cue else ""
        body = tail
    statement = tidy_statement(body)
    # Section headers live on their own line in the workbook, so the last line
    # is usually a cleaner statement whenever it is long enough to stand alone.
    lines = raw.split("\n")
    last_line = tidy_statement(lines[-1])
    previous = lines[-2] if len(lines) > 1 else ""
    if not continues_from(previous):
        if len(normalize(last_line)) >= 6 and len(normalize(last_line)) <= len(
            normalize(statement)
        ):
            statement = last_line
    context = re.sub(r"[，,]?\s*正确(?:打|的)?[√×]?\s*$", "", context).strip()
    if len(normalize(statement)) > 30 and "；" in statement:
        tail = statement.rsplit("；", 1)[-1]
        if len(normalize(tail)) >= 8:
            statement = tail
    statement = statement.replace("\n", "").strip()
    return context, statement


def tidy_statement(text: str) -> str:
    value = ITEM_START_RE.sub("", text, count=1).strip()
    value = value.lstrip("）) ").strip()
    value = value.rstrip("（( ").strip()
    return value.strip("；;、 ")


def continues_from(line: str) -> bool:
    """True when the next line is a continuation of a formula or equation."""
    stripped = line.strip()
    if not stripped:
        return True
    return bool(re.search(r"[A-Za-z0-9\)\]\}）】↑↓＋－+\-=⇌→＝]$", stripped))


def derive_judge_items(document: pymupdf.Document) -> dict[int, list[dict[str, Any]]]:
    """Read every judgement bracket out of the answer half, page by page."""
    derived: dict[int, list[dict[str, Any]]] = {}
    for print_page in range(1, 40):
        page = document[print_page + ANSWER_PAGE_OFFSET]
        lines = [line for line in page.get_text("text").splitlines() if line.strip()]
        flat = "\n".join(lines)
        question_text = "".join(
            line
            for line in document[print_page].get_text("text").splitlines()
            if line.strip()
        )
        mark_only = "打√" not in question_text and "正确打" not in question_text
        pattern = JUDGE_MARK_RE if mark_only else ANY_BRACKET_RE
        items: list[dict[str, Any]] = []
        cursor = 0
        for match in pattern.finditer(flat):
            context, statement = clean_statement(flat[cursor : match.start()])
            cursor = match.end()
            answer = match.group(1) or "×"
            if len(normalize(statement)) < 6:
                continue
            if re.fullmatch(r"[【\[].*[】\]]", statement):
                continue
            items.append(
                {
                    "statement": statement,
                    "answer": answer,
                    "context": context,
                    "derived": True,
                }
            )
        if items:
            derived[print_page] = items
    return derived


def split_judge_question(question: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a bundled judgement question into one item per bracket."""
    parts = BLANK_SPAN_RE.split(question["promptHtml"])
    texts = parts[0::2]
    items: list[dict[str, Any]] = []
    for index, slot in enumerate(question["slots"]):
        if slot["answer"].strip() not in JUDGE_ANSWERS:
            continue
        raw = texts[index] if index < len(texts) else ""
        if index == 0:
            context, statement = clean_statement(raw)
        else:
            context = ""
            statement = raw.strip().lstrip("）) ").rstrip("（( ").strip()
        if not normalize(statement):
            continue
        items.append(
            {
                "statement": statement,
                "answer": slot["answer"].strip(),
                "context": context,
                "derived": False,
            }
        )
    return items


def collect_bank_judge_items(bank: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    collected: dict[int, list[dict[str, Any]]] = {}
    for chapter in bank["chapters"]:
        for page in chapter["pages"]:
            items: list[dict[str, Any]] = []
            for question in page["questions"]:
                if question["type"] == "judge":
                    items.extend(split_judge_question(question))
            if items:
                collected[page["printPage"]] = items
    return collected


def merge_judge_items(
    derived: list[dict[str, Any]], existing: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = [dict(item) for item in derived]
    for item in existing:
        if any(similar(item["statement"], kept["statement"]) for kept in merged):
            continue
        merged.append(dict(item))
    return merged


def build_judge_question(
    item: dict[str, Any], section: str, print_page: int, index: int
) -> dict[str, Any]:
    question_id = f"p{print_page:02d}-j{index:03d}"
    statement = item["statement"]
    rendered = html.escape(statement, quote=False) if item["derived"] else statement
    slot_id = f"{question_id}-b1"
    context = item.get("context") or ""
    context_html = ""
    if context:
        rendered_context = html.escape(context, quote=False) if item["derived"] else context
        context_html = f"<p>{rendered_context}</p>"
    return {
        "id": question_id,
        "type": "judge",
        "contextHtml": context_html,
        "promptHtml": f"{rendered}{blank_span(slot_id)}",
        "plain": f"{statement}{{{{blank}}}}",
        "section": section,
        "slots": [
            {
                "id": slot_id,
                "answer": item["answer"],
                "x0": 0.0,
                "x1": 30.0,
                "width": 30.0,
                "kind": "judge",
            }
        ],
    }


def strip_judge_slots(question: dict[str, Any]) -> dict[str, Any] | None:
    """Drop judgement brackets that leaked into a fill question."""
    kept_slots = []
    removed_ids = set()
    for slot in question["slots"]:
        if slot["answer"].strip() in JUDGE_ANSWERS:
            removed_ids.add(slot["id"])
        else:
            kept_slots.append(slot)
    if not removed_ids:
        return question
    if not kept_slots:
        return None
    prompt = question["promptHtml"]
    for slot_id in removed_ids:
        span = blank_span(slot_id)
        position = prompt.find(span)
        if position < 0:
            prompt = prompt.replace(span, "")
            continue
        # The bracket usually closes a trailing clause such as
        # "；固体SiO2 一定是晶体（ ）", so drop that whole clause too.
        head = prompt[:position]
        head_plain = plain_from_prompt(head)
        cut = max(head_plain.rfind("；"), head_plain.rfind(";"), head_plain.rfind("。"))
        kept = head[: html_cut(head, cut + 1)] if cut >= 0 else head
        prompt = kept + prompt[position + len(span) :]
        prompt = re.sub(r"[（(]\s*[）)]\s*$", "", prompt)
        prompt = re.sub(r"[）)]\s*$", "", prompt)
    updated = dict(question)
    updated["slots"] = kept_slots
    updated["promptHtml"] = prompt
    updated["plain"] = plain_from_prompt(prompt)
    return updated


def apply_stem_override(question: dict[str, Any]) -> None:
    template = STEM_OVERRIDES[question["id"]]
    answers = ANSWER_OVERRIDES[question["id"]]
    pieces = re.split(r"\{\d*\}", template)
    prompt_parts: list[str] = []
    plain_parts: list[str] = []
    slots: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces):
        prompt_parts.append(piece)
        plain_parts.append(piece)
        if index >= len(answers):
            continue
        slot_id = f"{question['id']}-s{index + 1}"
        prompt_parts.append(blank_span(slot_id))
        plain_parts.append("{{blank}}")
        slots.append(
            {
                "id": slot_id,
                "answer": answers[index],
                "x0": 0.0,
                "x1": 60.0,
                "width": 60.0,
                "kind": "fill",
            }
        )
    question["slots"] = slots
    question["promptHtml"] = "".join(prompt_parts)
    question["plain"] = "".join(plain_parts)


def html_cut(markup: str, plain_index: int) -> int:
    """Map a plain-text offset onto the HTML string that renders it."""
    seen = 0
    index = 0
    while index < len(markup) and seen < plain_index:
        if markup.startswith('<span class="answer-slot"', index):
            end = markup.find("</span>", index)
            index = len(markup) if end == -1 else end + len("</span>")
            seen += len("{{blank}}")
            continue
        if re.match(r"<br\s*/?>", markup[index:index + 6]):
            end = markup.find(">", index)
            index = len(markup) if end == -1 else end + 1
            seen += 1
            continue
        entity = re.match(r"&(?:[a-zA-Z]{1,8}|#\d{1,6});", markup[index:])
        if entity:
            index += entity.end()
            seen += 1
            continue
        if markup[index] == "<":
            end = markup.find(">", index)
            index = len(markup) if end == -1 else end + 1
            continue
        seen += 1
        index += 1
    return index


def convert_options(question: dict[str, Any]) -> bool:
    """Turn numbered or lettered option lists into A/B/C multi-choice."""
    if question["type"] not in {"fill", "choice"}:
        return False
    if question.get("options"):
        return False
    overridden = ANSWER_OVERRIDES.get(question["id"])
    text = question["plain"]
    preset = OPTION_OVERRIDES.get(question["id"])
    kind = "circled"
    found = circled_items(text)
    if not found:
        found = latin_items(text)
        kind = "latin"
    if preset:
        found = (len(text), preset)
    if not found:
        return False
    start, items = found
    # Inline option lists that sit before more blanks belong to a mixed
    # question; leave those alone instead of cutting the stem in half.
    if "{{blank}}" in text[start:]:
        return False
    start = option_list_start(text, items, kind, start)
    letters: list[str | None] = []
    for index, slot in enumerate(question["slots"]):
        raw = slot["answer"]
        if overridden and index < len(overridden):
            raw = overridden[index]
        letters.append(answer_letter(raw, len(items)))
    if not letters or any(letter is None for letter in letters):
        return False
    question["options"] = [
        {"label": LATIN[index], "text": body} for index, body in enumerate(items)
    ]
    question["plain"] = text[:start].rstrip()
    stem = question["promptHtml"][: html_cut(question["promptHtml"], start)]
    question["promptHtml"] = re.sub(r"(?:<br\s*/?>|\s)+$", "", stem)
    for index, slot in enumerate(question["slots"]):
        letter = letters[index] or ""
        slot["answer"] = letter
        slot["kind"] = "choice"
        slot["multi"] = len(letter) > 1
    question["type"] = "choice"
    question["multi"] = any(len(slot["answer"]) > 1 for slot in question["slots"])
    return True


def restructure(bank: dict[str, Any], document: pymupdf.Document) -> dict[str, Any]:
    derived = derive_judge_items(document)
    existing = collect_bank_judge_items(bank)
    for chapter in bank["chapters"]:
        for page in chapter["pages"]:
            print_page = page["printPage"]
            section = ""
            rebuilt: list[dict[str, Any]] = []
            insert_at: int | None = None
            for question in page["questions"]:
                section = section or question["section"]
                if not section and question["section"]:
                    section = question["section"]
                if question["id"] in STEM_OVERRIDES:
                    apply_stem_override(question)
                if question["type"] == "judge":
                    if insert_at is None:
                        insert_at = len(rebuilt)
                    continue
                has_bracket = any(
                    slot["answer"].strip() in JUDGE_ANSWERS for slot in question["slots"]
                )
                if has_bracket:
                    if print_page in BRACKET_ONLY_PAGES:
                        if insert_at is None:
                            insert_at = len(rebuilt)
                        continue
                    stripped = strip_judge_slots(question)
                    if stripped is None:
                        if insert_at is None:
                            insert_at = len(rebuilt)
                        continue
                    question = stripped
                convert_options(question)
                rebuilt.append(question)
            items = merge_judge_items(
                derived.get(print_page, []), existing.get(print_page, [])
            )
            questions = [
                build_judge_question(item, section, print_page, index + 1)
                for index, item in enumerate(items)
            ]
            if questions:
                position = insert_at if insert_at is not None else len(rebuilt)
                rebuilt[position:position] = questions
            page["questions"] = rebuilt
    return bank


def summarize(bank: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chapter in bank["chapters"]:
        for page in chapter["pages"]:
            for question in page["questions"]:
                counts[question["type"]] = counts.get(question["type"], 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", default=str(DEFAULT_PDF))
    parser.add_argument("--bank", default=str(BANK_PATH))
    args = parser.parse_args()

    bank_path = Path(args.bank).expanduser()
    bank = json.loads(bank_path.read_text(encoding="utf-8"))
    document = pymupdf.open(Path(args.pdf).expanduser())
    bank = restructure(bank, document)
    bank_path.write_text(
        json.dumps(bank, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print("Restructured:", summarize(bank))


if __name__ == "__main__":
    main()
