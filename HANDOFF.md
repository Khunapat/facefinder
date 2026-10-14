# FaceFinder: full brief for continuing the work

Written 14 October 2026 by the session that built most of this, for a new
session that has only this repository. Read it all once. `CLAUDE.md` holds the
short standing rules; this file holds the history, the state and the plan.

## 1. The goal right now

Submit FaceFinder to the **Google Cloud AI Builder Cup 2026** (run by
Hack2skill) by **18 October 2026**. The owner's team is formed. Nothing has been
submitted yet. Section 6 lists what the submission needs and section 7 the gaps.

## 2. Who you are working with

- **Khunapat Prapassornchaikul** (goes by Jai). GitHub `Khunapat`, personal
  email `khunapat36795@gmail.com`. Commits to this repo must use that email,
  never a work address.
- English is not his first language. He writes short, informal messages with
  typos. Read for intent; do not ask him to rephrase.
- He is not a web developer. Answer in plain language, lead with the result,
  keep it short. He often sends a screenshot instead of describing a problem.
- When he has to run something, give **one complete command to paste**. Never
  say "press the up arrow" or "use the same command as before"; he said so.
- He works from a company-managed PC and browser. Sign-up pages and cloud
  consoles sometimes fail there for policy reasons, not because of our code.
- He cannot be asked for passwords, tokens or API keys in chat. He sets those
  himself as secrets (Codespaces secrets, Cloud Run environment variables).
- He decides by looking. Show him a working link or a picture early, then
  adjust. He has changed direction several times after seeing something.

## 3. What FaceFinder is

A web app for one problem: after a graduation, the photographer shares one
Google Drive folder with thousands of photos, and finding yours means scrolling
for an hour.

Flow: sign in with Google, paste the album's Drive folder link, the server scans
the album once and stores a face embedding for every face, then you say who you
want in one of two ways, check the results, and the app creates **one Drive
folder per person** and copies each person's photos into theirs.

The two ways to say who you want:

1. **I know who I'm looking for.** Add any number of people, each with one to
   three face photos and a name. Matching is cosine similarity against the
   cached embeddings.
2. **Show me everyone in the album.** No uploads. The cached embeddings are
   clustered into people (`app/cluster.py`, Chinese Whispers). The page shows
   one card per person with a face crop and a photo count; tick and name the
   ones you want; tap a face to review that person's photos.

Details that matter: it copies (never moves) with Drive's server-side
`files.copy`; a group photo goes to every selected person in it; two groups
given the same name share a folder; an export run twice copies only what is
missing (copies carry `appProperties.ff_src`).

## 4. Code map

```
app/config.py         all configuration from environment variables
app/faces.py          detection + embedding: InsightFace buffalo_l (512-d),
                      falls back to OpenCV YuNet + SFace (128-d); face crops
app/cluster.py        group an album's faces into people
app/google_drive.py   Drive listing, thumbnails, folders, server-side copy
app/store.py          SQLite cache: albums, photos, faces (embeddings as BLOBs)
app/main.py           FastAPI routes, background scan thread, export job
app/static/index.html the entire front end, one file, no build step
scripts/run-codespace.sh   starts the app inside a GitHub Codespace
.devcontainer/        Codespace setup; the server auto-starts on open
tools/diagnose.py     scan diagnosis helper
tests/                see section 9
design-canvas/        design work, see section 8
design-refs/          third-party design specs used as reference, see 7.6
Dockerfile            multi-stage, python:3.11-slim, bakes the face model in
```

Routes: `/oauth2/login`, `/oauth2/callback`, `/api/me`, `/api/album`,
`/api/index`, `/api/album/{id}/status`, `/api/search`, `/api/people`,
`/api/face/{folder}/{file}/{idx}`, `/api/thumb/{file}`, `/api/export`,
`/api/export/{job}`, `/healthz`.

Things that are easy to break:

- **Sign-in needs the PKCE verifier carried across the redirect** (in the
  session). Removing that breaks Google sign-in with `invalid_grant`.
- **Sessions are signed cookies.** Credentials, the PKCE verifier and the list
  of albums this session opened all live there. Keep the cookie small.
- **The index is shared between users of the same album**, so every album route
  checks that this session opened the album through its own Drive access
  (`_need_album`). Do not remove that check.
- **Scan and export run in background threads inside the web process.** State
  for running jobs is in memory. More than one instance, or an instance that is
  CPU-throttled between requests, breaks them. See 7.2.
- **googleapiclient objects are not thread-safe**; worker threads build their
  own service.
- File names from Drive are escaped before going into the page (`esc()`).

Face recognition deliberately does **not** use an LLM. Embeddings are the right
tool, cost nothing per photo and are more accurate. Gemini is being added for
other jobs (section 7.1), not to replace the matching.

## 5. Where things stand

**Code:** `main` on GitHub has the two-mode app described above, merged with the
Codespaces fixes. Last commit before this brief: `8b7f6f7`.

**Running copy:** a GitHub Codespace (`literate-waffle-...`), opened from branch
`claude/deployment-setup-hosting-i2vf6f`. It auto-starts the server with
`bash scripts/run-codespace.sh` and gets `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` from Codespaces secrets. Its address ends in
`-8000.app.github.dev`. When last seen it still showed the **old** one-person
version; the owner was given this command to update it and it is not known
whether he ran it:

```bash
cd /workspaces/facefinder && { pkill -f "uvicorn app.main" ; git pull origin main && git log --oneline -1 && bash scripts/run-codespace.sh ; }
```

A Codespace sleeps when idle, so it is **not** an acceptable prototype link for
the competition.

**Google Cloud:** project `facefinder-508213` exists and holds the OAuth client.
When last checked, the Cloud Run API was not enabled and the console said the
signed-in account had no permission to enable it, which usually means the wrong
Google account was signed in or billing is missing. Not resolved.

**Dead ends, do not retry:** Hugging Face Spaces (Docker Spaces now need a paid
plan); free tiers on Render or Koyeb (512 MB and a tenth of a CPU, far too slow
for scanning).

**Never tested for real:** the Docker image build, and the whole flow against
real Google Drive from this side. All testing so far used a stand-in for Drive
(section 9). The owner has used the old version in the Codespace with real
Google sign-in, so OAuth itself works there.

**Other branches:**

- `claude/eloquent-feynman-0cbszg`: a 20-second promo video rendered from code
  (`promo/`) plus a skill for making such reels. Not merged. Possibly useful for
  the demo video's intro; it shows the old design.
- `people-folders`: same commit as `main`.

## 6. The competition

- **Theme chosen:** Media, Content & Digital Experiences. "Build an AI-powered
  solution that transforms how content is created, discovered, personalized,
  understood, or experienced."
- **Suggested technologies for that theme:** Gemini on Vertex AI, Imagen, Veo,
  Speech-to-Text, Text-to-Speech, Cloud Translation, BigQuery, Cloud Storage,
  Cloud Run.
- **Hard requirements:** use a Google AI model (Gemini or Gemma family, or an
  agent platform); deploy the prototype on Cloud Run or Firebase.
- **Judging:** Technical Merit and Gen AI Implementation 40%; Problem Alignment
  and Impact 25%; Innovation and Creativity 25%; User Experience and Solution
  Design 10%.
- **The submission form asks for:**
  1. the challenge;
  2. a prototype link deployed on Google Cloud, which must keep working through
     evaluation (19 October to 6 November) with no retries if it is down;
  3. the pitch deck on their template, exported to PDF, 5 MB at most;
  4. a public GitHub repository link;
  5. a demo video link, **3 minutes at most** (the rules text says 3 to 4
     minutes, the form and site say 3; make it under 3), public on YouTube,
     Vimeo or Drive, showing the solution actually working;
  6. a brief description that says how the entry uses **Firebase, Firestore,
     Cloud Run and Gemini**.
- **Deck template slides, in order:** team details (team name, leader, problem
  statement); brief about the idea; opportunities (how it differs, how it
  solves the problem, USP); list of features; process flow or use-case diagram;
  wireframes or mock-ups (optional); architecture diagram; technologies;
  estimated implementation cost (optional); snapshots of the prototype;
  prototype performance report or benchmarking; additional details and future
  development; links (public GitHub repo, demo video, final product).
- **Eligibility, as stated on the site:** 21 or older, working professionals,
  entrepreneurs or startups; students are not eligible. The owner was told this
  and did not say which he is. It is his call; do not raise it again unless he
  asks.
- All materials must be in English.

## 7. What is missing, in the order I would do it

Four days are left. The first two items carry most of the score and the
prototype link, so do them first.

### 7.1 Gemini features (65% of the score rides on Gen AI use)

Proposed to the owner; he chose the theme but **has not yet said yes to these
three**. Confirm in one line, then build:

1. **Best shots.** For each person, Gemini looks at their photos and picks the
   best (sharp, eyes open, smiling, well framed) with a one-line reason. Each
   folder gets a "Best of" set.
2. **Ask the album.** A search box in plain words, Thai or English, such as
   "Nan on stage receiving her certificate". Gemini reads the photos and returns
   the matching ones.
3. **Your graduation story.** Gemini writes a short caption for each chosen
   photo and a few lines telling that person's day, ready to share.

Use Gemini on Vertex AI through the `google-genai` SDK so Cloud Run needs no API
key (it uses the service account), with a `GEMINI_API_KEY` fallback for the
Codespace. Send Drive thumbnails, not originals. Describe each photo once and
cache the description in the store, so "Ask the album" searches cached text
instead of calling Gemini per query per photo.

### 7.2 Cloud Run, Firestore and Firebase

- **Cloud Run:** deploy from the Dockerfile. Because scan and export are
  background threads with in-memory state, it needs `--no-cpu-throttling`,
  `--max-instances 1`, at least `--memory 2Gi --cpu 2`, a long `--timeout`, and
  `--allow-unauthenticated`. Region `asia-southeast1`. The owner has to run the
  deploy from Cloud Shell; a session cannot sign in to Google for him.
- **Firestore:** Cloud Run's disk is temporary, so the SQLite index is lost on
  every restart. Move albums, photos, faces and export jobs to Firestore
  (embeddings as bytes; mind the 1 MiB document limit, one document per face is
  fine). This is also what the brief description must mention.
- **Firebase:** the form asks how Firebase is used. The honest minimum is
  Firebase Hosting for the public landing or demo page in front of the Cloud Run
  service, or Firebase Auth for Google sign-in. Do not claim a use that is not
  real.
- After the first deploy, the Cloud Run URL goes into `PUBLIC_BASE_URL` and into
  the OAuth client's redirect URIs as `<url>/oauth2/callback`.

### 7.3 A way in for judges

The app asks for the `drive.readonly` scope, which Google treats as restricted.
The OAuth client is in Testing mode, so **only listed test users can sign in**.
Judges are not on that list and would be blocked. Add a **"Try the demo album"**
path that needs no sign-in: a pre-scanned sample album served from storage, with
the full flow working up to a simulated folder creation. Sample photos must be
ones we may publish: generated faces or photos from people who agreed. Do not
use public figures.

### 7.4 The new design

The owner chose a playful pink direction with a mascot; see section 8. The live
app still has the older design. Apply the new one to `app/static/index.html`.

### 7.5 Deck, video, description

The owner's team makes the video and finishes the deck. Prepare for them:
screenshots of the real app, an architecture diagram, a process-flow diagram,
the feature list, the benchmark numbers in section 9, and the brief description
text. The deck must use their template and be exported to PDF under 5 MB.

### 7.6 Before the repository goes public

- `design-refs/` holds community-written design specs for Airbnb, Pinterest and
  Claude. The old page's `--accent: #ff385c` is Airbnb's colour. Both go away
  with the new design; remove `design-refs/` and the README's "Visual design"
  section when it lands.
- `tests/img/` holds photos of public figures taken from another open-source
  project. Replace them with photos we may publish, and update the three tests'
  expected names and counts.
- Check that no secret was ever committed (none has been, to my knowledge).

## 8. Design

**Chosen direction: playful pink with a mascot.** The owner liked the feel of
parnuan.com: pale pink page, large rounded white panels, a strong pink accent,
pill-shaped buttons, numbered steps, and one character who appears in a
different pose for each activity.

**Do not copy Parnuan itself.** No logo, no aunty mascot, no display font, no
exact colours of theirs, and never upload their artwork to an image model as a
reference. The owner asked for that twice and was told no both times.

Our own system, as built in the mock-ups:

- page `#fdf0f5`, panels `#ffffff` with radius 32px and shadow
  `0 10px 30px rgba(31,37,64,0.06)`, ink `#1f2540`, muted text `#5b6178`,
  accent `#d6336c` (white text on it passes 4.5:1), tint border `#f3bcd0`
- headings in **Mitr**, body in **Noto Sans Thai** (both Google Fonts, Thai and
  Latin)
- pill buttons and pill inputs, 44 to 52px tall
- pastel face tiles: `#fde3ec`, `#e7ecff`, `#fff1d6`, `#e2f5ec`

**Mascot:** a small pink camera with a cream face and a graduation cap. The
owner supplied the final sheet himself. Cut-outs with transparent background,
all at one scale, are in `design-canvas/assets/`:

| file | pose | use it for |
|---|---|---|
| `cam-wave.png` | waving | start screen |
| `cam-search.png` | magnifying glass | scanning, searching |
| `cam-point.png` | pointing left (mirror it to point right) | choosing who gets a folder |
| `cam-photo.png` | holding a photo | reviewing photos, copying |
| `cam-celebrate.png` | arms up | folders created |
| `cam-shrug.png` | shrug with question mark | nothing found |
| `cam-stand.png` | standing | quiet or empty states |
| `cam-sad.png` | sorry | errors |

`camera-sheet-chosen.jpg` is the original sheet.

**Mock-ups:** `design-canvas/project/` holds the design canvas source files
(`*.dc.html`, a templating format; `canvas.json` lays them out).
`Playful.dc.html` is the pink "everyone in the album" screen and
`Prototype.dc.html` is a clickable prototype of the whole pink flow; treat those
two as the reference for layout, copy and behaviour. Images in those files are
referenced as `/_blob/<id>`, which only resolves inside the hosted canvas; the
same pictures are the `cam-*.png` files above. The remaining `*.dc.html` files
show the older design. The owner has not confirmed that the prototype rendered
correctly; it was published without being viewed.

## 9. Testing

Google sign-in cannot be exercised by a coding session, so there is a stand-in
for Drive backed by local folders:

```bash
python -m tests.test_matching   # accuracy of the face model on sample photos
python -m tests.test_pipeline   # index and search without Google
python -m tests.test_people     # 19 checks through the real HTTP routes
python -m tests.devserver       # whole app on the stand-in, to click through
```

With the dev server, open `/dev/login`, then paste the album link it prints.
`tests/fakedrive.py` is the stand-in; nothing in `app/` imports it.

The tests download the face model on first run (about 280 MB from GitHub
releases). If the network blocks that, the engine falls back to the small OpenCV
models and the thresholds in the tests will not hold.

Numbers so far, useful for the deck's benchmark slide: same person scores 0.75
to 0.98 cosine similarity, a different person scores about -0.05, a separation
of 0.83. On 16 photos of 5 people, the grouping put every face with the right
person at all three strictness settings. Scanning runs at roughly 4 to 8 photos
per second per core on a normal machine; the first builder's PC was far slower
and its timings are not usable.

## 10. Settings

| variable | meaning |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | OAuth client from the Cloud project |
| `PUBLIC_BASE_URL` | public address, no trailing slash; must match the redirect URI |
| `SESSION_SECRET` | long random string; changing it signs everyone out |
| `DATA_DIR` | where the SQLite index lives |
| `MODEL_ROOT` | where the face model lives; separate from `DATA_DIR` on purpose |
| `DRIVE_ACCESS` | `limited` (default) or `full`, see below |
| `DEFAULT_THRESHOLD` | match strictness for named people, default 0.38 |
| `CLUSTER_THRESHOLD` | link strength for grouping, default 0.46 |
| `INDEX_WORKERS`, `COPY_WORKERS` | parallelism, default 4 each |

`DRIVE_ACCESS`: with `limited` the app can only write into folders it created,
so a pasted destination folder is refused by Google and the export falls back to
a new folder in My Drive and says so. `full` requests the whole-Drive scope and
writes anywhere the user can. The owner was told about this and did not choose;
it is `limited`.

## 11. Decisions already made, so they are not reopened

- Online only; the owner does not want to run anything on his own PC.
- No LLM for face matching.
- The OAuth app stays in Testing mode with test users; no Google verification.
- The pink direction and the camera mascot are chosen.
- Theme: Media, Content & Digital Experiences.
- Imagen, Veo and BigQuery are not being added just to tick boxes.
