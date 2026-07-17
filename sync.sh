#!/bin/bash
# Two-way sync of cards.json between this VPS and GitHub.
# Commits cards added via the website, merges in cards pushed from elsewhere,
# pushes the result back. Run by learn-sync.timer; safe to run by hand.
set -euo pipefail
cd /home/fcuci/apps/learn

if ! git diff --quiet -- site/cards.json; then
  git add site/cards.json
  git commit -q -m "cards: edits from the website"
  echo "committed local card edits"
fi

git fetch -q origin

if ! git merge -q --no-edit origin/main; then
  git merge --abort || true
  echo "merge failed — resolve by hand in /home/fcuci/apps/learn" >&2
  exit 1
fi

git push -q origin main
echo "in sync"
