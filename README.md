# Cue cards

A dead-simple flashcard app. Live at <https://learn.fedecuci.com>.

Cards live in [`site/cards.json`](site/cards.json) — a plain list, safe to edit by hand
or with AI:

```json
[
  {"topic": "Networking", "front": "What is a CNAME record?", "back": "A DNS record that points one name at another name instead of an IP."}
]
```

`topic` is optional; `front` and `back` are required. A card's `front` is its identity —
change a `front` and it counts as a different card.

## Adding cards

Either way works, and they sync:

- **On the website** — the *Manage* button (add / edit / delete). Needs the edit password.
- **From any machine** — edit `site/cards.json`, commit, push. The VPS pulls every 10
  minutes, so cards show up on the site on their own.

## Running it

```sh
cp .env.example .env   # then set EDIT_PASSWORD
docker compose up -d --build
```

Serves on `127.0.0.1:8100`; the VPS publishes it through a Cloudflare tunnel.
`.env` holds the edit password and is not committed.

## Sync

The VPS runs `sync.sh` every 10 minutes (`learn-sync.timer`): commit web edits →
merge remote → push.

`site/cards.json` uses a custom merge driver ([`merge_cards.py`](merge_cards.py)) so
cards added in two places at once both survive instead of conflicting. Merge drivers
are configured per-clone and can't be committed, so **run this once in every clone**:

```sh
git config merge.cuecards.name "cue card merge"
git config merge.cuecards.driver "python3 $PWD/merge_cards.py %O %A %B"
```

Without it you'll still get normal (line-level) conflicts in `cards.json` — nothing
breaks, it's just annoying.

Pulled code changes need `docker compose up -d --build`; card changes need nothing.

## Studying (spaced repetition)

The site has three tabs:

- **Review** — shows only cards that are *due*, one at a time. Flip, then rate
  *Got it* or *Missed*. Rating needs no password.
- **Browse** — every card, free flip / shuffle / arrow-key navigation. No rating.
- **Manage** — add / edit / delete card content (password-protected).

Scheduling is a simple 5-box [Leitner](https://en.wikipedia.org/wiki/Leitner_system)
system: *Got it* moves a card up a box and further out (1 → 3 → 7 → 16 → 35 days);
*Missed* drops it back to box 1 (due tomorrow). A new card is due immediately.

Progress lives in `data/progress.db` (SQLite), keyed on each card's `front`. It is
**not** in git and never syncs — it's per-server study state, not content. Editing a
card's topic or back keeps its progress; changing its `front` starts it fresh (the
`front` is the card's identity). Deleting `progress.db` just resets all schedules,
your cards are untouched.
