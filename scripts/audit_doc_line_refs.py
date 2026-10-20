#!/usr/bin/env python3
"""Doc line-reference audit (Track 3, run after implementation and before commit).

Checks every `path:line`, `path:start-end` and `path:l1,l2,...` reference in the brand docs:
  * the file exists,
  * every referenced line number is inside the file,
  * for table rows that quote the *current* phrase in backticks, the phrase is still present in that file
    (if it is gone the row is reported as RESOLVED, which is expected after a copy wave).
Exit code 1 only for missing files or out-of-range lines (hard drift). RESOLVED rows are informational.
Usage: python3 scripts/audit_doc_line_refs.py [doc ...]
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DOCS = ["docs/BRAND_COPY_INVENTORY.md"]
REF = re.compile(r"`((?:web|core|scripts|tests)/[\w./\-]+\.\w+):([\d,\-]+)`")
BARE = re.compile(r"((?:web|core|scripts|tests)/[\w./\-]+\.\w+):([\d,\-]+)")
QUOTE = re.compile(r"`([^`]{6,})`")


def line_numbers(spec):
    nums = []
    for part in spec.split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                nums += [int(a), int(b)]
        elif part.isdigit():
            nums.append(int(part))
    return nums


def audit(doc):
    hard, resolved, ok = [], [], 0
    path = os.path.join(ROOT, doc)
    for lineno, row in enumerate(open(path, encoding="utf-8"), 1):
        refs = BARE.findall(row)
        if not refs:
            continue
        cols = row.split("|")
        phrases = []
        if len(cols) > 3:
            phrases = [q for q in QUOTE.findall(cols[2]) if not REF.fullmatch(f"`{q}`") and ":" not in q[:40]]
        for rel, spec in refs:
            fp = os.path.join(ROOT, rel)
            if not os.path.exists(fp):
                hard.append(f"{doc}:{lineno}: MISSING FILE {rel}")
                continue
            text = open(fp, encoding="utf-8", errors="ignore").read()
            n_lines = text.count("\n") + 1
            bad = [n for n in line_numbers(spec) if n > n_lines]
            if bad:
                hard.append(f"{doc}:{lineno}: OUT OF RANGE {rel}:{spec} (file has {n_lines} lines)")
                continue
            if phrases and not any(p.replace("&amp;", "&") in text or p in text for p in phrases):
                resolved.append(f"{doc}:{lineno}: RESOLVED {rel}:{spec} (quoted phrase no longer in file)")
            else:
                ok += 1
    return hard, resolved, ok


def main():
    docs = sys.argv[1:] or DEFAULT_DOCS
    total_hard = 0
    for d in docs:
        hard, resolved, ok = audit(d)
        print(f"== {d}: {ok} refs ok, {len(resolved)} resolved, {len(hard)} hard drift")
        for r in resolved:
            print("  ", r)
        for h in hard:
            print("  ", h)
        total_hard += len(hard)
    sys.exit(1 if total_hard else 0)


if __name__ == "__main__":
    main()
