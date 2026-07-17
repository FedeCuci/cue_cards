#!/usr/bin/env python3
"""Git merge driver for site/cards.json.

Cards get added on the VPS (via the website) and on other machines (by hand or
with AI), so both sides routinely append to the same JSON array — which a plain
text merge always reports as a conflict. This merges by card instead of by line:
a card's `front` is its identity, so edits to a card's topic/back are tracked
rather than looking like a delete plus an add.

Called by git as: merge_cards.py <ancestor> <ours> <theirs>
Writes the merged result over <ours>. Exit 0 = merged, 1 = leave it to git.
"""
import json
import sys


def load(path):
    with open(path) as f:
        cards = json.load(f)
    if not isinstance(cards, list):
        raise ValueError("cards.json must be a list")
    return {c["front"]: c for c in cards}, [c["front"] for c in cards]


def pick(base, ours, theirs, key):
    """Resolve one card across the three sides. None means 'drop it'."""
    o, a, b = base.get(key), ours.get(key), theirs.get(key)
    if a == b:
        return a
    if a is None:
        # Absent from ours: either theirs added it, or ours deleted it.
        return b if o is None or b != o else None
    if b is None:
        return a if o is None else (None if a == o else a)
    # Present on both sides but different: whoever changed it wins; if both
    # changed it differently, ours wins (this side's edit is the newer one).
    return b if a == o else a


def main():
    try:
        base, _ = load(sys.argv[1])
        ours, ours_order = load(sys.argv[2])
        theirs, theirs_order = load(sys.argv[3])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return 1  # malformed input — let git raise a normal conflict

    order = ours_order + [k for k in theirs_order if k not in ours]
    merged = []
    for key in order:
        card = pick(base, ours, theirs, key)
        if card is not None:
            merged.append(card)

    with open(sys.argv[2], "w") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
