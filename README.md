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
