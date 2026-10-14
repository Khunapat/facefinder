# FaceFinder

A web app that sorts a shared Google Drive photo album into one Drive folder per
person. FastAPI, InsightFace embeddings, one-file front end.

**Read `HANDOFF.md` before doing anything.** It has the history, the current
state, the competition deadline (18 October 2026) and the plan.

## Working with the owner

- Khunapat (Jai) is not a web developer and English is not his first language.
  Plain words, short answers, result first.
- When he must run something, give one complete command to paste. Never "press
  the up arrow" or "the same command as before".
- Never ask for passwords, tokens or API keys in chat. He sets secrets himself.
- Commits use `khunapat36795@gmail.com`.
- He wants everything hosted online, nothing run on his own PC.

## Rules for this repo

- Face matching stays on the embedding model. Gemini is for curation, search and
  writing, not for deciding who is in a photo.
- Do not copy another brand's look. The design is our own pink system with the
  camera mascot in `design-canvas/assets/cam-*.png`. Never use Parnuan's logo,
  mascot or artwork, including as a reference for an image model.
- Keep `_need_album` on every album route and the PKCE verifier in the sign-in
  flow; `HANDOFF.md` section 4 says why.
- Sample photos in the repo and in any public demo must be ones we may publish.
  No public figures.
- Say plainly what was tested and what was not. Real Google sign-in and Cloud
  Run cannot be tested from a coding session; the owner tests those.

## Checks

```bash
python -m tests.test_people
python -m tests.test_matching
python -m tests.test_pipeline
```

`python -m tests.devserver` runs the whole app on a stand-in for Google Drive;
open `/dev/login`.
