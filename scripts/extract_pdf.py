#!/usr/bin/env python3
"""Extract the chemistry workbook into an interactive page-based bank.

The source PDF has two mirrored halves: blank question pages followed by answer
pages. Answers are typeset over underlines, so the answer page is the canonical
text source and the underline geometry identifies each answer slot.
"""

from __future__ import annotations

import html
import json
import math
import re
import statistics
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

import pymupdf
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = Path(
    "/Users/zhaoguang/.codex/multi-agent-console/attachments/"
    "OQ7qZBMakm9-0faQ94vR-Tgy/三轮复习_基础知识回归_含答案_.pdf"
)
OUT_DIR = ROOT / "public" / "question-bank"
PAGE_DIR = OUT_DIR / "pages"
PRINT_PAGE_COUNT = 39


CHAPTER_RE = re.compile(
    r"^\s*(一|二|三|四|五|六|七|八|九|十|十一|十二|十三|十四|十五|十六|"
    r"十七|十八|十九|二十|二十一|二十二|二十三|二十四|二十五|二十六|二十七)"
    r"、\s*(.+?)\s*$"
)
SECTION_RE = re.compile(r"^\s*【(.+?)】")
ITEM_RE = re.compile(
    r"^\s*(?:[（(]\s*\d{1,2}\s*[）)]|\d{1,2}\s*[）).．、])"
)
CONTINUATION_RE = re.compile(r"^\s*[＋+－\-−＝=→⇌△]")
BLANK_TOKEN = "{{blank}}"


@dataclass
class CharBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    origin_y: float


@dataclass
class TextLine:
    chars: list[CharBox]
    bbox: tuple[float, float, float, float]

    @property
    def text(self) -> str:
        chars = sorted(self.chars, key=lambda char: (char.x0, char.y0))
        return "".join(char.text for char in chars)


def load_pages(document: pymupdf.Document, start: int, end: int) -> list[pymupdf.Page]:
    return [document[index] for index in range(start - 1, end)]


def raw_lines(page: pymupdf.Page) -> list[TextLine]:
    data = page.get_text("rawdict")
    lines: list[TextLine] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            chars: list[CharBox] = []
            for span in line.get("spans", []):
                for char in span.get("chars", []):
                    text = safe_text(char.get("c", ""))
                    bbox = char.get("bbox")
                    if not text or bbox is None:
                        continue
                    chars.append(
                        CharBox(
                            text=text,
                            x0=float(bbox[0]),
                            y0=float(bbox[1]),
                            x1=float(bbox[2]),
                            y1=float(bbox[3]),
                            size=float(span.get("size", 10.0)),
                            origin_y=float(char.get("origin", (0, bbox[3]))[1]),
                        )
                    )
            if not chars:
                continue
            xs0 = min(char.x0 for char in chars)
            ys0 = min(char.y0 for char in chars)
            xs1 = max(char.x1 for char in chars)
            ys1 = max(char.y1 for char in chars)
            lines.append(TextLine(chars=chars, bbox=(xs0, ys0, xs1, ys1)))
    return lines


def merge_visual_rows(lines: list[TextLine]) -> list[TextLine]:
    """Merge spans that belong to the same visual row, including sub/superscripts."""
    ordered = sorted(
        lines,
        key=lambda line: (
            statistics.median(char.origin_y for char in line.chars),
            line.bbox[0],
        ),
    )
    groups: list[list[TextLine]] = []
    for line in ordered:
        line_baseline = statistics.median(char.origin_y for char in line.chars)
        line_height = line.bbox[3] - line.bbox[1]
        placed = False
        for group in groups:
            group_x0, group_y0, group_x1, group_y1 = group_bbox(group)
            group_baseline = statistics.median(char.origin_y for item in group for char in item.chars)
            group_height = group_y1 - group_y0
            gap = max(0.0, max(group_x0, line.bbox[0]) - min(group_x1, line.bbox[2]))
            if group_y1 < line.bbox[1] - 2:
                continue
            baseline_delta = abs(group_baseline - line_baseline)
            height_limit = max(3.8, min(7.0, min(group_height, line_height) * 0.55))
            if baseline_delta <= height_limit and gap <= max(90.0, min(group_height, line_height) * 1.5):
                group.append(line)
                placed = True
                break
        if not placed:
            groups.append([line])

    merged: list[TextLine] = []
    for group in groups:
        chars = [char for line in group for char in line.chars]
        chars.sort(key=lambda char: (round(char.x0, 2), char.origin_y))
        bbox = (
            min(char.x0 for char in chars),
            min(char.y0 for char in chars),
            max(char.x1 for char in chars),
            max(char.y1 for char in chars),
        )
        merged.append(TextLine(chars=chars, bbox=bbox))
    return sorted(merged, key=lambda line: (line.bbox[1], line.bbox[0]))


def group_bbox(group: list[TextLine]) -> tuple[float, float, float, float]:
    return (
        min(line.bbox[0] for line in group),
        min(line.bbox[1] for line in group),
        max(line.bbox[2] for line in group),
        max(line.bbox[3] for line in group),
    )


def horizontal_segments(page: pymupdf.Page) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for drawing in page.get_drawings():
        rect = drawing["rect"]
        if abs(rect.y0 - rect.y1) > 0.35:
            continue
        width = float(rect.x1 - rect.x0)
        if width < 7:
            continue
        segments.append(
            {
                "x0": float(rect.x0),
                "x1": float(rect.x1),
                "y": float((rect.y0 + rect.y1) / 2),
                "red": drawing.get("color") == (1.0, 0.0, 0.0),
                "width": float(drawing.get("width") or 0.48),
            }
        )
    return segments


def chars_in_region(
    line: TextLine,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> list[CharBox]:
    found = []
    for char in line.chars:
        center_x = (char.x0 + char.x1) / 2
        if x0 - 0.8 <= center_x <= x1 + 0.8 and char.y1 >= y0 and char.y0 <= y1:
            if not char.text.isspace():
                found.append(char)
    return sorted(found, key=lambda char: (char.x0, char.y0))


def line_for_segment(
    lines: Iterable[TextLine], segment: dict[str, Any]
) -> tuple[TextLine | None, float]:
    best: tuple[TextLine | None, float] = (None, math.inf)
    for line in lines:
        line_x0, _, line_x1, line_y1 = line.bbox
        if segment["x1"] < line_x0 - 4 or segment["x0"] > line_x1 + 4:
            continue
        distance = abs(segment["y"] - line_y1)
        if distance < best[1]:
            best = (line, distance)
    return best


def merge_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: (round(item["y"], 1), item["x0"]))
    merged: list[dict[str, Any]] = []
    for segment in ordered:
        if not merged:
            merged.append(dict(segment))
            continue
        previous = merged[-1]
        overlaps = segment["x0"] <= previous["x1"] + 2
        nearby = abs(segment["y"] - previous["y"]) <= 1.4
        if overlaps and nearby:
            previous["x0"] = min(previous["x0"], segment["x0"])
            previous["x1"] = max(previous["x1"], segment["x1"])
            previous["red"] = previous["red"] or segment["red"]
            previous["width"] = max(previous["width"], segment["width"])
        else:
            merged.append(dict(segment))
    return merged


def compact_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def safe_text(value: str) -> str:
    """Drop malformed surrogate characters emitted by some embedded fonts."""
    return value.encode("utf-8", "replace").decode("utf-8")


def is_meaningful_answer(value: str) -> bool:
    text = compact_text(value)
    if not text:
        return False
    if text in {"_", "—", "-", "()", "（）", "。", "；", "，", ",", ";"}:
        return False
    return len(text) >= 1


def answer_kind(answer: str, full_text: str, blank_count: int) -> str:
    compact = compact_text(answer).lower()
    if compact in {"√", "×", "对", "错", "正确", "错误", "是", "否"}:
        return "judge"
    if re.fullmatch(r"[a-d]+", compact) and re.search(r"[A-D][.．、]", full_text):
        return "choice_multi" if len(compact) > 1 else "choice"
    if blank_count == 1 and compact in {"偏大", "偏小", "无影响", "变大", "变小", "不变"}:
        return "choice"
    return "fill"


def chars_to_html(chars: list[CharBox], median_size: float) -> str:
    if not chars:
        return ""
    baseline = statistics.median(char.origin_y for char in chars)
    output: list[str] = []
    current_kind: str | None = None
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        text = html.escape("".join(current))
        if current_kind == "sub":
            output.append(f"<sub>{text}</sub>")
        elif current_kind == "sup":
            output.append(f"<sup>{text}</sup>")
        else:
            output.append(text)
        current.clear()

    previous_x1: float | None = None
    for char in sorted(chars, key=lambda item: (item.x0, item.y0)):
        if previous_x1 is not None and char.x0 - previous_x1 > max(2.0, char.size * 0.45):
            if not current or current[-1] != " ":
                current.append(" ")
        previous_x1 = char.x1
        kind: str | None = None
        if char.size < median_size * 0.82 and char.origin_y > baseline + 0.6:
            kind = "sub"
        elif char.size < median_size * 0.82 and char.origin_y < baseline - 0.6:
            kind = "sup"
        if kind != current_kind:
            flush()
            current_kind = kind
        current.append(char.text)
    flush()
    return "".join(output)


def char_segments_html(
    line: TextLine,
    blanks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    chars = sorted(line.chars, key=lambda item: (item.x0, item.y0))
    median_size = statistics.median(char.size for char in chars)
    segments: list[dict[str, Any]] = []
    text_buffer: list[CharBox] = []
    current_blank_index = 0

    def append_text() -> None:
        if not text_buffer:
            return
        html_text = chars_to_html(text_buffer, median_size)
        if segments and segments[-1]["type"] == "text":
            segments[-1]["html"] += html_text
        else:
            segments.append({"type": "text", "html": html_text})
        text_buffer.clear()

    for char in chars:
        center_x = (char.x0 + char.x1) / 2
        matched = None
        for index in range(current_blank_index, len(blanks)):
            blank = blanks[index]
            if blank["x0"] - 1 <= center_x <= blank["x1"] + 1:
                matched = index
                break
            if blank["x1"] < center_x - 1:
                current_blank_index = index + 1
        if matched is None:
            text_buffer.append(char)
            continue
        append_text()
        blank = blanks[matched]
        blank_id = blank["id"]
        if not segments or segments[-1].get("id") != blank_id:
            segments.append(
                {
                    "type": "blank",
                    "id": blank_id,
                    "answer": blank["answer"],
                    "kind": blank["kind"],
                    "width": blank["width"],
                }
            )
        current_blank_index = matched

    append_text()
    plain_parts: list[str] = []
    for segment in segments:
        if segment["type"] == "text":
            plain_parts.append(re.sub(r"<[^>]+>", "", segment["html"]))
        else:
            plain_parts.append(BLANK_TOKEN)
    return segments, "".join(plain_parts).strip()


def char_text(chars: Iterable[CharBox]) -> str:
    return "".join(char.text for char in sorted(chars, key=lambda item: (item.x0, item.y0)))


def blank_html_segments(
    line: TextLine,
    blanks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Render a question row while replacing each answer region with a slot."""
    chars = sorted(line.chars, key=lambda item: (item.x0, item.y0))
    if not chars:
        return [], ""

    ordered_blanks = sorted(blanks, key=lambda item: item["x0"])
    median_size = statistics.median(char.size for char in chars)
    segments: list[dict[str, Any]] = []
    text_buffer: list[CharBox] = []
    blank_index = 0
    inserted: set[str] = set()

    def append_text() -> None:
        if not text_buffer:
            return
        html_text = chars_to_html(text_buffer, median_size)
        if segments and segments[-1]["type"] == "text":
            segments[-1]["html"] += html_text
        else:
            segments.append({"type": "text", "html": html_text})
        text_buffer.clear()

    def append_blank(blank: dict[str, Any]) -> None:
        append_text()
        if blank["id"] in inserted:
            return
        inserted.add(blank["id"])
        segments.append(
            {
                "type": "blank",
                "id": blank["id"],
                "answer": blank["answer"],
                "kind": blank["kind"],
                "width": blank["width"],
            }
        )

    for char in chars:
        center_x = (char.x0 + char.x1) / 2
        while blank_index < len(ordered_blanks) and center_x > ordered_blanks[blank_index]["x1"] + 1:
            append_blank(ordered_blanks[blank_index])
            blank_index += 1

        if blank_index < len(ordered_blanks):
            current = ordered_blanks[blank_index]
            if current["x0"] - 1 <= center_x <= current["x1"] + 1:
                append_blank(current)
                continue
        text_buffer.append(char)

    while blank_index < len(ordered_blanks):
        append_blank(ordered_blanks[blank_index])
        blank_index += 1
    append_text()

    plain_parts: list[str] = []
    for segment in segments:
        if segment["type"] == "text":
            plain_parts.append(re.sub(r"<[^>]+>", "", segment["html"]))
        else:
            plain_parts.append(BLANK_TOKEN)
    return segments, "".join(plain_parts).strip()


def answer_from_diff(
    question_line: TextLine,
    answer_line: TextLine,
    blank: dict[str, Any],
) -> str:
    """Infer an answer by aligning the text inserted at a blank's x-position."""
    qchars = [
        char
        for char in sorted(question_line.chars, key=lambda item: (item.x0, item.y0))
        if not char.text.isspace() and char.text not in {"_", "＿"}
    ]
    achars = [
        char
        for char in sorted(answer_line.chars, key=lambda item: (item.x0, item.y0))
        if not char.text.isspace()
    ]
    qtext = "".join(char.text for char in qchars)
    atext = "".join(char.text for char in achars)
    if not qtext or not atext:
        return ""

    prefix_index = sum(
        1
        for char in qchars
        if (char.x0 + char.x1) / 2 < blank["x0"] - 0.5
    )
    after_index = sum(
        1
        for char in qchars
        if (char.x0 + char.x1) / 2 <= blank["x1"] + 0.5
    )
    matcher = SequenceMatcher(None, qtext, atext, autojunk=False)
    pieces: list[str] = []
    for tag, q0, q1, a0, a1 in matcher.get_opcodes():
        if tag == "equal":
            continue
        insertion_at_blank = q0 == q1 and prefix_index - 1 <= q0 <= after_index + 1
        overlap_at_blank = q0 < after_index + 1 and q1 > prefix_index - 1
        if not insertion_at_blank and not overlap_at_blank:
            continue
        piece = atext[a0:a1]
        if piece:
            pieces.append(piece)
    candidate = "".join(pieces)
    candidate = candidate.replace("_", "").replace("＿", "").strip()
    return compact_text(candidate)


def answer_from_coordinates(
    answer_line: TextLine,
    blank: dict[str, Any],
) -> str:
    answer_chars = chars_in_region(
        answer_line,
        blank["x0"] - 3,
        blank["x1"] + 10,
        answer_line.bbox[1] - 3,
        answer_line.bbox[3] + 3,
    )
    candidate = "".join(char.text for char in answer_chars)
    candidate = candidate.replace("_", "").replace("＿", "").strip()
    return compact_text(candidate)


def compact_char_stream(line: TextLine) -> tuple[str, list[CharBox]]:
    chars = [char for char in sorted(line.chars, key=lambda item: (item.x0, item.y0)) if not char.text.isspace()]
    return "".join(char.text for char in chars), chars


def nearest_anchor_index(
    stream_text: str,
    stream_chars: list[CharBox],
    anchor: str,
    approx_x: float,
    *,
    before: bool,
) -> tuple[int, int] | None:
    if not anchor:
        return None
    positions: list[int] = []
    cursor = 0
    while True:
        index = stream_text.find(anchor, cursor)
        if index < 0:
            break
        positions.append(index)
        cursor = index + 1
    if not positions:
        return None

    def distance(index: int) -> float:
        if index >= len(stream_chars):
            return math.inf
        center = (stream_chars[index].x0 + stream_chars[min(index + len(anchor) - 1, len(stream_chars) - 1)].x1) / 2
        return abs(center - approx_x)

    start = min(positions, key=distance)
    return start, start + len(anchor)


def answer_from_anchors(
    question_line: TextLine,
    answer_line: TextLine,
    blank: dict[str, Any],
) -> str:
    """Trim inserted text using the unchanged text immediately before and after a blank."""
    qchars = sorted(question_line.chars, key=lambda item: (item.x0, item.y0))
    qtext, qcompact = compact_char_stream(question_line)
    atext, acompact = compact_char_stream(answer_line)

    before_chars: list[CharBox] = []
    after_chars: list[CharBox] = []
    for char in qchars:
        center = (char.x0 + char.x1) / 2
        if char.text.isspace() or char.text in {"_", "＿"}:
            continue
        if center < blank["x0"] - 0.5:
            before_chars.append(char)
        elif center > blank["x1"] + 0.5:
            after_chars.append(char)
            if len(after_chars) >= 6:
                break

    before_anchor = "".join(char.text for char in before_chars[-6:])
    after_anchor = "".join(char.text for char in after_chars[:6])
    before_match = nearest_anchor_index(
        atext,
        acompact,
        before_anchor,
        blank["x0"],
        before=True,
    )
    after_match = nearest_anchor_index(
        atext,
        acompact,
        after_anchor,
        blank["x1"],
        before=False,
    )

    del qtext, qcompact
    start_char = 0
    if before_match is not None:
        start_char = min(before_match[1], len(acompact))
    else:
        start_char = next(
            (index for index, char in enumerate(acompact) if (char.x0 + char.x1) / 2 >= blank["x0"] - 2),
            len(acompact),
        )

    end_char = len(acompact)
    if after_match is not None and after_match[0] >= start_char:
        end_char = after_match[0]

    candidate = "".join(char.text for char in acompact[start_char:end_char])
    candidate = candidate.replace("_", "").replace("＿", "").strip()
    if before_anchor:
        for length in range(min(6, len(before_anchor)), 0, -1):
            prefix = before_anchor[-length:]
            offset = candidate.rfind(prefix)
            if offset >= 0 and offset + len(prefix) < len(candidate):
                candidate = candidate[offset + len(prefix) :]
                break
    if after_anchor:
        for length in range(min(6, len(after_anchor)), 0, -1):
            suffix = after_anchor[:length]
            offset = candidate.find(suffix)
            if offset > 0:
                candidate = candidate[:offset]
                break
    return compact_text(candidate.strip("。；，,;"))


def parenthetical_blanks(question_line: TextLine) -> list[dict[str, Any]]:
    chars = sorted(question_line.chars, key=lambda item: (item.x0, item.y0))
    blanks: list[dict[str, Any]] = []
    for index, char in enumerate(chars):
        if char.text not in {"(", "（"}:
            continue
        expected_close = ")" if char.text == "(" else "）"
        for close_index in range(index + 1, min(index + 7, len(chars))):
            close = chars[close_index]
            if close.text != expected_close:
                continue
            between = chars[index + 1 : close_index]
            if all(item.text.isspace() for item in between):
                blanks.append(
                    {
                        "x0": char.x1 + 0.2,
                        "x1": max(char.x1 + 0.2, close.x0 - 0.2),
                        "source": "parentheses",
                    }
                )
            break
    return blanks


def underscore_blanks(question_line: TextLine) -> list[dict[str, Any]]:
    chars = sorted(question_line.chars, key=lambda item: (item.x0, item.y0))
    blanks: list[dict[str, Any]] = []
    current: list[CharBox] = []
    for char in chars:
        if char.text in {"_", "＿"}:
            current.append(char)
            continue
        if len(current) >= 2:
            blanks.append(
                {
                    "x0": min(item.x0 for item in current),
                    "x1": max(item.x1 for item in current),
                    "source": "underscore",
                }
            )
        current = []
    if len(current) >= 2:
        blanks.append(
            {
                "x0": min(item.x0 for item in current),
                "x1": max(item.x1 for item in current),
                "source": "underscore",
            }
        )
    return blanks


def drawing_blanks(
    question_line: TextLine,
    question_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    _, line_y0, _, line_y1 = question_line.bbox
    blanks: list[dict[str, Any]] = []
    for segment in question_segments:
        if not (line_y0 - 2 <= segment["y"] <= line_y1 + 5):
            continue
        width = segment["x1"] - segment["x0"]
        if width < 8 or width > 260:
            continue
        chars_in_slot = chars_in_region(
            question_line,
            segment["x0"],
            segment["x1"],
            line_y0 - 2,
            segment["y"] + 1,
        )
        if chars_in_slot and any(char.text not in {"_", "＿"} and not char.text.isspace() for char in chars_in_slot):
            continue
        blanks.append(
            {
                "x0": segment["x0"],
                "x1": segment["x1"],
                "source": "drawing",
            }
        )
    return blanks


def extract_line_slots(
    question_line: TextLine,
    answer_line: TextLine | None,
    question_segments: list[dict[str, Any]],
    line_index: int,
    page_number: int,
) -> list[dict[str, Any]]:
    candidates = (
        drawing_blanks(question_line, question_segments)
        + underscore_blanks(question_line)
        + parenthetical_blanks(question_line)
    )
    candidates.sort(key=lambda item: (item["x0"], item["x1"]))

    # Prefer a long drawing underline over the underscore glyphs that sit on it.
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        duplicate = next(
            (
                existing
                for existing in filtered
                if max(existing["x0"], candidate["x0"]) <= min(existing["x1"], candidate["x1"]) + 3
            ),
            None,
        )
        if duplicate is None:
            filtered.append(candidate)
            continue
        if candidate["source"] == "drawing" and candidate["x1"] - candidate["x0"] > duplicate["x1"] - duplicate["x0"]:
            filtered[filtered.index(duplicate)] = candidate
        elif candidate["source"] == "underscore" and duplicate["source"] != "drawing":
            filtered[filtered.index(duplicate)] = candidate

    slots: list[dict[str, Any]] = []
    for candidate in filtered:
        if answer_line is None:
            answer = ""
        else:
            answer = answer_from_diff(question_line, answer_line, candidate)
            if not answer:
                answer = answer_from_anchors(question_line, answer_line, candidate)
            if not answer:
                answer = answer_from_coordinates(answer_line, candidate)
        if not is_meaningful_answer(answer):
            continue
        width = max(30.0, min(180.0, candidate["x1"] - candidate["x0"] + 8))
        slots.append(
            {
                "id": f"p{page_number:02d}-l{line_index:03d}-b{len(slots) + 1:02d}",
                "answer": answer,
                "x0": candidate["x0"],
                "x1": candidate["x1"],
                "width": round(width, 1),
            }
        )
    return slots


def classify_question(question_text: str, slots: list[dict[str, Any]]) -> str:
    answers = [compact_text(slot["answer"]).lower() for slot in slots]
    if answers and all(answer in {"√", "×", "对", "错", "正确", "错误", "是", "否"} for answer in answers):
        return "judge"
    if answers and all(re.fullmatch(r"[a-d]+", answer) for answer in answers):
        if re.search(r"[A-D][.．、]", question_text):
            return "choice"
    return "fill"


def append_question_text(question: dict[str, Any], text: str) -> None:
    """Append a wrapped line without creating a separate fragment question."""
    text = text.strip()
    if not text:
        return
    question["promptHtml"] += f"<br>{html.escape(text)}"
    question["plain"] += f" {text}"


def append_question_line(
    question: dict[str, Any],
    segments: list[dict[str, Any]],
    plain_text: str,
) -> None:
    """Merge another visual row into an existing logical question."""
    html_parts = [
        segment["html"]
        if segment["type"] == "text"
        else f'<span class="answer-slot" data-blank-id="{segment["id"]}"></span>'
        for segment in segments
    ]
    question["promptHtml"] += f'<br>{"".join(html_parts)}'
    question["plain"] += f" {plain_text}"
    question["slots"].extend(
        segment
        for segment in segments
        if segment["type"] == "blank"
    )


def starts_new_item(text: str) -> bool:
    stripped = text.strip()
    if ITEM_RE.match(stripped):
        return True
    # Short uppercase-numbered prompts also start distinct sub-questions.
    return bool(re.match(r"^\s*[A-D][.．、]", stripped))


def detect_line_blanks(
    answer_line: TextLine,
    answer_segments: list[dict[str, Any]],
    question_line: TextLine | None,
    line_index: int,
    page_number: int,
) -> list[dict[str, Any]]:
    answer_x0, answer_y0, answer_x1, answer_y1 = answer_line.bbox
    question_chars = question_line.chars if question_line else []
    blanks: list[dict[str, Any]] = []

    for segment in answer_segments:
        if not (
            answer_y1 - 3.2 <= segment["y"] <= answer_y1 + 7.5
            and segment["x0"] >= answer_x0 - 4
            and segment["x1"] <= answer_x1 + 4
        ):
            continue

        answer_chars = chars_in_region(
            answer_line,
            segment["x0"],
            segment["x1"],
            answer_y0 - 3.2,
            segment["y"] + 0.8,
        )
        answer_text = "".join(char.text for char in answer_chars)
        if not is_meaningful_answer(answer_text):
            continue

        question_text = ""
        if question_chars:
            question_chars_found = [
                char
                for char in question_chars
                if segment["x0"] - 0.8
                <= (char.x0 + char.x1) / 2
                <= segment["x1"] + 0.8
                and char.y1 >= answer_y0 - 5
                and char.y0 <= segment["y"] + 2
                and not char.text.isspace()
            ]
            question_text = "".join(char.text for char in question_chars_found)

        # Black underlines are used for some answers. Keep a black underline only
        # when the mirrored question page did not contain text in the same slot.
        if not segment["red"] and question_text:
            continue

        # Ignore the long horizontal borders used by tables and flow diagrams.
        if segment["width"] >= 2.8 and segment["x1"] - segment["x0"] > 330:
            continue

        width = max(30.0, min(150.0, segment["x1"] - segment["x0"] + 4))
        blanks.append(
            {
                "id": f"p{page_number:02d}-l{line_index:03d}-b{len(blanks) + 1:02d}",
                "answer": answer_text.strip(),
                "x0": segment["x0"],
                "x1": segment["x1"],
                "width": round(width, 1),
            }
        )

    # Remove overlapping duplicate underlines while retaining the longest slot.
    filtered: list[dict[str, Any]] = []
    for blank in sorted(blanks, key=lambda item: (item["x0"], -(item["x1"] - item["x0"]))):
        if filtered and blank["x0"] <= filtered[-1]["x1"] + 2:
            previous = filtered[-1]
            if len(blank["answer"]) > len(previous["answer"]):
                filtered[-1] = blank
            continue
        filtered.append(blank)
    return filtered


def nearest_question_line(
    answer_line: TextLine, question_lines: list[TextLine]
) -> TextLine | None:
    _, ay0, _, ay1 = answer_line.bbox
    answer_center = (ay0 + ay1) / 2
    best: TextLine | None = None
    best_distance = math.inf
    for line in question_lines:
        _, qy0, _, qy1 = line.bbox
        distance = abs((qy0 + qy1) / 2 - answer_center)
        if distance < best_distance:
            best = line
            best_distance = distance
    return best if best_distance <= 11 else None


def classify_page_line(
    text: str,
    segments: list[dict[str, Any]],
    blanks: list[dict[str, Any]],
    full_answer_text: str,
) -> str:
    stripped = text.strip()
    if not stripped:
        return "material"
    if CHAPTER_RE.match(stripped):
        return "chapter"
    if SECTION_RE.match(stripped):
        return "section"
    if not blanks:
        return "material"
    answer_compact = compact_text(full_answer_text).lower()
    if all(
        compact_text(blank["answer"]).lower() in {"√", "×", "对", "错", "正确", "错误"}
        for blank in blanks
    ):
        return "judge"
    if all(re.fullmatch(r"[a-d]+", compact_text(blank["answer"]).lower()) for blank in blanks):
        if re.search(r"[A-D][.．、]", stripped):
            return "choice"
    if len(blanks) == 1 and answer_compact in {
        "偏大",
        "偏小",
        "无影响",
        "变大",
        "变小",
        "不变",
    }:
        return "choice"
    return "fill"


def render_page_images(document: pymupdf.Document) -> None:
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    scale = 1.75
    matrix = pymupdf.Matrix(scale, scale)
    for print_page in range(1, PRINT_PAGE_COUNT + 1):
        for kind, physical_page in (
            ("q", print_page + 1),
            ("a", print_page + PRINT_PAGE_COUNT + 1),
        ):
            page = document[physical_page - 1]
            pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=pymupdf.csRGB)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            target = PAGE_DIR / f"{kind}-{print_page:02d}.webp"
            image.save(target, "WEBP", quality=78, method=6)


def extract_bank(document: pymupdf.Document) -> dict[str, Any]:
    chapters: list[dict[str, Any]] = []
    current_chapter: dict[str, Any] | None = None
    current_section = "本章内容"

    for print_page in range(1, PRINT_PAGE_COUNT + 1):
        answer_page = document[print_page + PRINT_PAGE_COUNT]
        question_page = document[print_page]
        answer_lines = merge_visual_rows(raw_lines(answer_page))
        question_lines = merge_visual_rows(raw_lines(question_page))
        question_segments = merge_segments(horizontal_segments(question_page))

        page_data: dict[str, Any] = {
            "id": f"page-{print_page:02d}",
            "printPage": print_page,
            "questionImage": f"question-bank/pages/q-{print_page:02d}.webp",
            "answerImage": f"question-bank/pages/a-{print_page:02d}.webp",
            "questions": [],
        }

        if print_page == 39:
            page_data["questions"].append(
                {
                    "id": "p39-visual",
                    "type": "visual",
                    "contextHtml": "",
                    "promptHtml": "本页以实验装置图和操作判断题为主，请对照原图逐项完成。",
                    "plain": "本页以实验装置图和操作判断题为主，请对照原图逐项完成。",
                    "section": current_section,
                    "slots": [],
                }
            )
            current_chapter["pages"].append(page_data)
            continue

        # The chapter title is printed in the page header. Detect it before the
        # normal body cutoff so continuation pages stay attached to the right
        # chapter and internal numbered headings cannot create false chapters.
        chapter_heading: str | None = None
        header_lines = [
            line
            for line in raw_lines(question_page) + raw_lines(answer_page)
            if line.bbox[1] < 72
        ]
        for line in sorted(header_lines, key=lambda item: (item.bbox[1], item.bbox[0])):
            match = CHAPTER_RE.match(line.text.strip())
            if match:
                chapter_heading = f"{match.group(1)}、{match.group(2).strip()}"
                break
        if chapter_heading:
            current_chapter = {
                "id": f"chapter-{len(chapters) + 1:02d}",
                "index": len(chapters) + 1,
                "title": chapter_heading,
                "pages": [],
            }
            chapters.append(current_chapter)
            current_section = "本章内容"

        if current_chapter is None:
            current_chapter = {
                "id": "chapter-01",
                "index": 1,
                "title": "一、物质性质与分类",
                "pages": [],
            }
            chapters.append(current_chapter)

        pending_lines: list[TextLine] = []
        current_question: dict[str, Any] | None = None
        line_index = 0
        while line_index < len(question_lines):
            question_line = question_lines[line_index]
            if question_line.bbox[1] < 62 or question_line.bbox[1] > 792:
                line_index += 1
                continue

            line_text = question_line.text.strip()
            if not line_text:
                line_index += 1
                continue

            if CHAPTER_RE.match(line_text):
                line_index += 1
                continue

            section_match = SECTION_RE.match(line_text)
            if section_match and len(line_text) < 60:
                current_question = None
                current_section = section_match.group(1).strip()
                pending_lines.append(question_line)
                line_index += 1
                continue

            answer_line = nearest_question_line(question_line, answer_lines)
            slots = extract_line_slots(
                question_line,
                answer_line,
                question_segments,
                line_index,
                print_page,
            )

            if not slots:
                if starts_new_item(line_text):
                    current_question = None
                    pending_lines.append(question_line)
                elif current_question is not None:
                    append_question_text(current_question, line_text)
                else:
                    pending_lines.append(question_line)
                line_index += 1
                continue

            for slot in slots:
                slot["kind"] = answer_kind(slot["answer"], line_text, len(slots))

            segments, plain_text = blank_html_segments(question_line, slots)
            question_type = classify_question(line_text, slots)
            merge_into_current = (
                current_question is not None
                and current_question["section"] == current_section
                and current_question["type"] == question_type
                and not starts_new_item(line_text)
            )
            if merge_into_current:
                append_question_line(current_question, segments, plain_text)
                line_index += 1
                continue

            context_html = "".join(
                f"<p>{html.escape(line.text.strip())}</p>"
                for line in pending_lines
                if line.text.strip()
            )
            question = {
                "id": f"p{print_page:02d}-q{len(page_data['questions']) + 1:03d}",
                "type": question_type,
                "contextHtml": context_html,
                "promptHtml": "".join(
                    segment["html"]
                    if segment["type"] == "text"
                    else f'<span class="answer-slot" data-blank-id="{segment["id"]}"></span>'
                    for segment in segments
                ),
                "plain": plain_text,
                "section": current_section,
                "slots": slots,
            }
            page_data["questions"].append(question)
            current_question = question
            pending_lines = []

            # Choice options usually occupy the following text row. Keep them
            # with the question rather than losing them in the page-only view.
            if question_type == "choice":
                lookahead = line_index + 1
                option_lines: list[str] = []
                while lookahead < len(question_lines):
                    next_line = question_lines[lookahead]
                    if next_line.bbox[1] < 62 or next_line.bbox[1] > 792:
                        break
                    next_text = next_line.text.strip()
                    if re.search(r"[A-D][.．、]", next_text):
                        option_lines.append(next_text)
                        lookahead += 1
                        continue
                    if option_lines and len(option_lines) >= 1:
                        break
                    break
                if option_lines:
                    question["contextHtml"] += "".join(
                        f"<p class=\"choice-option\">{html.escape(text)}</p>"
                        for text in option_lines
                    )
                    line_index = lookahead - 1

            line_index += 1

        current_question = None

        if not page_data["questions"]:
            page_data["questions"].append(
                {
                    "id": f"p{print_page:02d}-visual",
                    "type": "visual",
                    "contextHtml": "",
                    "promptHtml": "本页包含图片、装置或表格内容，请对照原题作答。",
                    "plain": "本页包含图片、装置或表格内容，请对照原题作答。",
                    "section": current_section,
                    "slots": [],
                }
            )

        current_chapter["pages"].append(page_data)

    # A mirrored blank page can occasionally leave a small unpaired fragment at
    # the end of the workbook. Remove empty chapters before validating output.
    chapters = [chapter for chapter in chapters if chapter["pages"]]

    return {
        "title": "高三化学三轮复习 · 基础知识回归",
        "source": "首都师范大学附属中学",
        "chapters": chapters,
    }


def main() -> None:
    pdf_path = Path(
        __import__("os").environ.get("CHEM_PDF_PATH", str(DEFAULT_PDF))
    ).expanduser()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    if len(document) != 79:
        raise SystemExit(f"Expected 79 pages, got {len(document)}")

    render_page_images(document)
    bank = extract_bank(document)
    (OUT_DIR / "bank.json").write_text(
        json.dumps(bank, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    question_count = sum(
        1
        for chapter in bank["chapters"]
        for page in chapter["pages"]
        for question in page["questions"]
        if question["type"] in {"fill", "judge", "choice"}
    )
    blank_count = sum(
        len(question.get("slots", []))
        for chapter in bank["chapters"]
        for page in chapter["pages"]
        for question in page["questions"]
    )
    page_numbers = sorted(
        page["printPage"]
        for chapter in bank["chapters"]
        for page in chapter["pages"]
    )
    if page_numbers != list(range(1, PRINT_PAGE_COUNT + 1)):
        raise SystemExit(f"Page coverage is incomplete: {page_numbers}")
    if len(bank["chapters"]) != 27:
        raise SystemExit(
            f"Expected 27 chapters, got {len(bank['chapters'])}: "
            f"{[chapter['title'] for chapter in bank['chapters']]}"
        )
    print(
        f"Extracted {len(bank['chapters'])} chapters, "
        f"{question_count} interactive questions, {blank_count} answer slots."
    )
    print(f"Wrote {OUT_DIR / 'bank.json'}")


if __name__ == "__main__":
    main()
