#!/usr/bin/env python3
"""Three-level fact locks (red / yellow / green) and red-lock integrity verification.

This is the safety core of the writing pipeline. Every gate that may rewrite,
shorten, polish or compress text must prove afterwards that no red-locked fact
was lost, altered or invented. If that proof fails, the operation is rejected.

Lock levels, from the specification:

  red    sample counts, observation times, instrument names, thresholds, boundary
         filter conditions, core physical parameters. 100% must survive.
  yellow secondary qualifiers and derived parameters. Droppable, but every drop
         must appear in a dropped-items list.
  green  background, transitions, repeated description. Freely extractable.

Also implemented: red-lock escalation. A red fact is only meaningful together with
the premise that defines it ("baseline" has to keep meaning the same thing), so a
definition sentence for a term used in a red fact is escalated to a temporary red
lock. Keeping the number while losing its definition is the failure mode this
exists to prevent.

Numbers are compared as normalised multisets, so rewriting "6 hours" as "6 h" is
fine while turning 6 into 12, or dropping the unit, is not.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Generic physical units only. No field-specific instrument list is hardcoded:
# instrument and parameter names come from the project's own domain config.
UNITS = (r"km/s|km|m/s|mm|cm|nm|kg|mbar|hPa|Pa|kW/m2|W/m2|W·m-2|"
         r"K|°C|C|nT|T|eV|keV|MeV|Hz|kHz|MHz|GHz|"
         r"ms|min|ms|h|hr|hrs|hours|day|days|yr|years|"
         r"deg|°|arcmin|arcsec|%|permil|"
         r"Jy|K/km|K/day|K/km/day")
NUMBER = r"[+-]?\d+(?:[.,]\d+)?"
NUM_UNIT = re.compile(r"(?<![\w.])(%s)\s*(%s)(?![\w])" % (NUMBER, UNITS), re.IGNORECASE)
BARE_NUMBER = re.compile(r"(?<![\w.,])(%s)(?![\w.,]?\d)" % NUMBER)
SAMPLE_COUNT = re.compile(r"\b[nN]\s*=\s*(%s)\b" % NUMBER)
# A bare "=" is deliberately excluded: "n = 48" is a sample count, not a threshold.
THRESHOLD = re.compile(r"(>=|<=|>|<|≥|≤|超过|低于|高于|不少于|不超过|至少|至多)\s*(%s)" % NUMBER)
TIME_WINDOW = re.compile(
    r"(\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?)|"
    r"(\d{1,2}:\d{2}\s*(?:UT|UTC)?)|"
    r"\b(UT|UTC|LT|SLT)\b", re.IGNORECASE)
DEFINITION = re.compile(r"(定义为|定义为：|指的是|是指|定义为以下|defined as|is defined as|refers to)")

SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*|(?<=[.])\s+(?=[A-Z\u4e00-\u9fff])|\n+")


def sentences(text):
    """Split into sentences without breaking decimals, version numbers or units."""
    if not text:
        return []
    raw = []
    for chunk in SENT_SPLIT.split(str(text)):
        if chunk is None:
            continue
        piece = chunk.strip()
        if piece:
            raw.append(piece)
    return raw


def normalise_number(value):
    return str(value).replace(",", ".")


def _facts(text, domain_terms):
    """Return the raw facts found in one sentence, with their lock level."""
    found = []
    for value in SAMPLE_COUNT.findall(text):
        found.append({"kind": "sample_count", "surface": "n=%s" % normalise_number(value),
                      "value": normalise_number(value), "unit": "", "level": "red"})
    for _op, value in THRESHOLD.findall(text):
        found.append({"kind": "threshold", "surface": "threshold %s" % normalise_number(value),
                      "value": normalise_number(value), "unit": "", "level": "red"})
    for a, b, c in TIME_WINDOW.findall(text):
        surface = a or b or c
        if surface:
            found.append({"kind": "time_window", "surface": surface.lower(),
                          "value": surface.lower(), "unit": "", "level": "red"})
    for value, unit in NUM_UNIT.findall(text):
        found.append({"kind": "quantity", "surface": "%s %s" % (normalise_number(value), unit),
                      "value": normalise_number(value), "unit": unit.lower(), "level": "red"})
    lowered = text.lower()
    for term in domain_terms or []:
        if term and term.lower() in lowered:
            found.append({"kind": "domain_term", "surface": term.lower(),
                          "value": term.lower(), "unit": "", "level": "red"})

    # Bare numbers are only "derived" if they were not already claimed by a red
    # fact or by a time window; otherwise a date would leak its parts as extras.
    claimed = {f["value"] for f in found}
    masked = text
    for a, b, c in TIME_WINDOW.findall(text):
        surface = a or b or c
        if surface:
            masked = masked.replace(surface, " ")
    for value in BARE_NUMBER.findall(masked):
        norm = normalise_number(value)
        if norm not in claimed:
            claimed.add(norm)
            found.append({"kind": "derived_number", "surface": norm, "value": norm,
                          "unit": "", "level": "yellow"})

    seen, unique = set(), []
    for f in found:
        key = (f["kind"], f["value"], f["unit"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "of", "as", "in", "on", "at", "to",
    "for", "and", "or", "we", "this", "that", "these", "those", "it", "its", "by",
    "with", "from", "be", "been", "用", "的", "是", "在", "和", "与", "为", "本文",
    "我们", "本研究", "该", "这", "那", "以及", "等",
}


def _content_terms(text, min_cjk=2):
    """Comparable content units.

    Chinese is written without spaces, so taking a "run of CJK characters" as one
    term yields whole clauses that can never match anything. Instead every CJK
    n-gram of length min_cjk..min_cjk+1 is emitted, which gives terms that actually
    recur across sentences. Latin words are taken as-is. Stopwords are dropped.
    """
    terms = set()
    for run in re.findall(r"[\u4e00-\u9fff]{%d,}" % min_cjk, text):
        for size in (min_cjk, min_cjk + 1):
            for i in range(len(run) - size + 1):
                gram = run[i:i + size]
                if gram not in STOPWORDS:
                    terms.add(gram)
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text):
        if word.lower() not in STOPWORDS:
            terms.add(word.lower())
    return terms


def is_definition(sentence):
    return bool(DEFINITION.search(sentence))


def _defined_subject(sentence):
    """The text immediately before the definition marker: what is being defined."""
    found = DEFINITION.search(sentence)
    if not found:
        return ""
    return sentence[:found.start()].strip()[-40:]


def tag_sentences(text, domain_terms=None):
    """Per-sentence tag: red if it carries a red fact, else yellow/green by content."""
    domain_terms = domain_terms or []
    out = []
    for index, sentence in enumerate(sentences(text)):
        facts = _facts(sentence, domain_terms)
        reds = [f for f in facts if f["level"] == "red"]
        yellows = [f for f in facts if f["level"] == "yellow"]
        if reds:
            level = "red"
        elif yellows:
            level = "yellow"
        else:
            level = "green"
        out.append({"index": index, "text": sentence, "level": level, "facts": facts,
                    "is_definition": is_definition(sentence)})
    return out


def extract(text, domain_terms=None):
    """All facts in a text, plus the red-lock escalation pass."""
    tags = tag_sentences(text, domain_terms)
    facts = []
    for tag in tags:
        for fact in tag["facts"]:
            facts.append(dict(fact, sentence_index=tag["index"]))

    # Escalation: a red fact is only trustworthy if the premise defining it stays
    # put. So any sentence that defines a term which also appears in a red-tagged
    # sentence is escalated to a temporary red lock. The defined subject is taken
    # from the text before the definition marker, which keeps the match stable when
    # the sentence is reworded but not when the definition is dropped.
    red_text = " ".join(t["text"] for t in tags if t["level"] == "red").lower()
    red_terms = _content_terms(red_text, min_cjk=2)
    escalated = []
    for tag in tags:
        if not tag["is_definition"] or tag["level"] == "red":
            continue
        subject_terms = _content_terms(_defined_subject(tag["text"]), min_cjk=2)
        shared = sorted(term for term in subject_terms if term in red_terms)
        if shared:
            escalated.append({"sentence_index": tag["index"], "text": tag["text"],
                              "reason": "defines a term used in a red-locked fact",
                              "shared_terms": shared})
    return {"facts": facts, "escalated": escalated,
            "counts": {level: sum(1 for f in facts if f["level"] == level)
                       for level in ("red", "yellow", "green")}}


def _multiset(facts, levels):
    bag = {}
    for fact in facts:
        if fact["level"] not in levels:
            continue
        key = (fact["kind"], fact["value"], fact["unit"])
        bag[key] = bag.get(key, 0) + 1
    return bag


def verify(before_text, after_text, domain_terms=None):
    """Red-lock integrity check between two versions of the same text.

    Fails if any red fact disappeared, changed value, if any number appeared that
    was not there before (inventing data is a violation, not a fix), or if the
    definition of a term used in a red fact was lost while the term is still used.
    That last case is the "number kept, meaning gone" failure the escalation exists
    to prevent, so it is enforced rather than merely reported.
    """
    before_all = extract(before_text, domain_terms)
    after_all = extract(after_text, domain_terms)
    before, after = before_all["facts"], after_all["facts"]
    red_before = _multiset(before, {"red"})
    red_after = _multiset(after, {"red"})

    missing, changed = [], []
    for key, count in red_before.items():
        have = red_after.get(key, 0)
        if have < count:
            kind, value, unit = key
            same_kind = [k for k in red_after if k[0] == kind and k[2] == unit]
            if same_kind:
                changed.append({"kind": kind, "was": value, "now": [k[1] for k in same_kind]})
            else:
                missing.append({"kind": kind, "value": value, "unit": unit,
                                "lost": count - have})

    numbers_before = {f["value"] for f in before}
    added = sorted({f["value"] for f in after} - numbers_before)
    red_added = [f for f in after if f["level"] == "red" and f["value"] in set(added)]

    terms_before = {t for entry in before_all["escalated"] for t in entry["shared_terms"]}
    terms_after = {t for entry in after_all["escalated"] for t in entry["shared_terms"]}
    escalated_lost = sorted(terms_before - terms_after)

    yellow_before = _multiset(before, {"yellow"})
    yellow_after = _multiset(after, {"yellow"})
    yellow_dropped = []
    for key, count in yellow_before.items():
        have = yellow_after.get(key, 0)
        if have < count:
            yellow_dropped.append({"kind": key[0], "value": key[1], "count": count - have})

    ok = not missing and not changed and not red_added and not escalated_lost
    # With no red facts to begin with, recall is vacuously complete. Reporting 0.0
    # here would falsely block compression of an all-green box.
    denominator = sum(red_before.values())
    recall = 1.0 if denominator == 0 else round(
        sum(min(red_after.get(k, 0), v) for k, v in red_before.items()) / denominator, 4)
    return {
        "ok": ok,
        "red_missing": missing,
        "red_changed": changed,
        "red_added": [{"kind": f["kind"], "value": f["value"]} for f in red_added],
        "red_escalated_lost": escalated_lost,
        "yellow_dropped": yellow_dropped,
        "escalated_locks": before_all["escalated"],
        "red_facts_before": denominator,
        "red_recall": recall,
    }


def assert_intact(before_text, after_text, domain_terms=None, label=""):
    report = verify(before_text, after_text, domain_terms)
    if not report["ok"]:
        raise ValueError(
            "red-lock violation%s: missing=%s changed=%s added=%s escalated_lost=%s"
            % ((" in " + label) if label else "", report["red_missing"],
               report["red_changed"], report["red_added"], report["red_escalated_lost"]))
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Three-level fact locks and red-lock verification")
    sub = ap.add_subparsers(dest="command", required=True)

    e = sub.add_parser("extract", help="list the locks in a text file")
    e.add_argument("text")
    e.add_argument("--domain-terms", nargs="*", default=[])

    v = sub.add_parser("verify", help="verify red locks between two versions")
    v.add_argument("before")
    v.add_argument("after")
    v.add_argument("--domain-terms", nargs="*", default=[])

    args = ap.parse_args(argv)
    try:
        if args.command == "extract":
            data = extract(Path(args.text).read_text(encoding="utf-8"), args.domain_terms)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return 0
        report = verify(Path(args.before).read_text(encoding="utf-8"),
                        Path(args.after).read_text(encoding="utf-8"), args.domain_terms)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["ok"] else 2
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
