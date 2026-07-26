# Cue cards

A dead-simple flashcard app. Live at <https://learn.fedecuci.com>
(also <https://cuecards.fedecuci.com>).

Cards live in `site/cards.json` on the server — a plain list:

```json
[
  {"topic": "Networking", "front": "What is a CNAME record?", "back": "A DNS record that points one name at another name instead of an IP."}
]
```

`topic` and `back` are optional; `front` is required and is the card's identity —
change a `front` and it counts as a different card. A card with no `back` is treated
as *unfinished*: it's hidden from Review and listed under the **Unfinished** tab.

This repo holds the **app code**. The card content (`site/cards.json`) is owned by
the running server, is **not** tracked in git, and is backed up by the host's normal
backups (restic → Backblaze, nightly). There is no laptop/GitHub card syncing — you
author cards on the site.

## Adding cards

All from the website's **Manage** tab (needs the edit password):

- **Add / edit / delete** cards by hand. `Ctrl`/`Cmd`+`Enter` adds a card.
- Leave the back blank now, fill it later.
- **Unfinished** tab → *"✨ Write missing answers with AI"* fills every blank back
  in one batch (uses the OpenRouter key in `.env`).

## Running it

```sh
cp .env.example .env   # set EDIT_PASSWORD, OPENROUTER_API_KEY, OPENROUTER_MODEL
docker compose up -d --build
```

Serves on `127.0.0.1:8100`; the VPS publishes it through a Cloudflare tunnel.
`.env` (edit password + OpenRouter key) is not committed. A fresh deploy starts with
no cards until you add some. Code changes need `docker compose up -d --build`.

## Studying (spaced repetition)

Tabs:

- **Review** — only cards that are *due* (and have an answer), one at a time. Flip,
  then rate *Got it* or *Missed*. Rating needs no password.
- **Browse** — every card, free flip / shuffle / arrow-key navigation.
- **Unfinished** — cards still missing a back (appears only when there are any).
- **Manage** — add / edit / delete content (password-protected).

Scheduling is a simple 5-box [Leitner](https://en.wikipedia.org/wiki/Leitner_system)
system: *Got it* moves a card up a box and further out (1 → 3 → 7 → 16 → 35 days);
*Missed* drops it back to box 1 (due tomorrow). A new card is due immediately.

Progress lives in `data/progress.db` (SQLite), keyed on each card's `front`. It is
**not** in git — it's per-server study state, not content. Editing a card's topic or
back keeps its progress; changing its `front` starts it fresh. Deleting `progress.db`
just resets all schedules; your cards are untouched.
