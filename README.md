# FaceFinder

Sort a big shared Google Drive album by who is in it: every person gets their
own folder of photos in your Drive.

Built for the graduation-photo problem: the photographer hands over one folder
with 4,000 photos in it, and finding yourself (or sorting out who gets which
photos) means scrolling for an hour.

## How it works

1. You sign in with Google.
2. You paste the link of the album the photographer shared.
3. The server scans the album once and stores a **face embedding** — a vector of
   512 numbers — for every face it finds. This is the slow step, and it happens
   only once per album.
4. You say who you want, in one of two ways (below).
5. You uncheck any wrong photos, then the app makes **one folder per name** and
   copies each person's photos into theirs.

### Two ways to say who you want

**I know who I'm looking for.** Add as many people as you like. Each gets one to
three photos of their face and a name. Each face becomes a vector, and matching
is a dot product against the cached vectors.

**Show me everyone in the album.** No uploads. The cached vectors are grouped
into people (`app/cluster.py`: link every pair of faces above a similarity
threshold, then let the labels settle — Chinese Whispers, the approach dlib
uses). You get one card per person with a face crop and a photo count. Tick the
ones you want a folder for and type a name; tap a face to review that person's
photos. If one person shows up as two cards, give both the same name and they
share a folder. The "Grouping" control trades that kind of split against the
opposite mistake, two people merged into one.

Either way a group photo is copied into the folder of every selected person in
it, and running the export again only copies what is missing.

### Where the folders go

Leave the destination empty and you get `FaceFinder - <album name>` in My Drive
with a folder per person inside. Type a name to choose that folder's name
instead. Paste a Drive folder link to put the person folders inside a folder you
already have — see `DRIVE_ACCESS` below, because Google only allows that with
the wider permission.

### Who is in a photo: a face model, not Gemini

Face recognition is not a language-model job. It uses **InsightFace buffalo_l**
(an ArcFace model) running locally in the container through ONNX Runtime. It
costs nothing per photo and has no token limit. Asking Gemini "is this the same
person?" would be slower, more expensive, and *less* accurate. Gemini does the
jobs a face model cannot: judging photo quality for culling, describing photos
for search and sorting, and suggesting folders.

**Model licence.** The `insightface` Python library is MIT-licensed, but its
pretrained model packs, buffalo_l included, are released by the InsightFace
project for non-commercial research use only. FaceFinder uses them as a
non-commercial competition prototype. A commercial release would need a
commercial licence from InsightFace or a face model with a commercial licence;
only `app/faces.py` would change.

Measured on the bundled sample photos (`python -m tests.test_matching`):

| photo                            | cosine score |
|----------------------------------|--------------|
| same person, different photo     | 0.78         |
| same person, low resolution      | 0.98         |
| same person, in a group photo    | 0.75         |
| **different person**             | **-0.05**    |

The gap between "same person" and "different person" is about 0.8, which is why
a threshold anywhere from 0.35 to 0.55 works. The default is 0.38, and the UI
exposes a slider.

### Two things that make it cheap

- **Drive thumbnails, not originals.** Scanning pulls Drive's own ~1600px JPEG
  rather than the 12 MB original. Roughly 50x less bandwidth, and detection
  accuracy is unaffected.
- **`files.copy` is server-side.** Google duplicates the file inside its own
  storage. The app never downloads or re-uploads a full-resolution photo, so
  copying 300 photos takes seconds.

### Privacy

The server stores face vectors, face box positions and file IDs. It does not
store the photos — image bytes are fetched, embedded, and discarded. The small
face crops shown on the "everyone" screen are cut from the photo on request and
held in memory only. The index is shared between users of the same album, so a
session can only read an album after opening it through its own Drive access. Copies land in the user's own
Drive; the app never takes ownership of the album.

---

## Privacy: what FaceFinder keeps

- **Photos are not stored.** They are read from Google Drive with the user's own
  sign-in when needed. Nothing in Drive is changed, moved or deleted; exports are
  copies. FaceFinder's own export folders and copies are skipped by later scans.
- **Face data:** per face, a 512-number embedding and its box in the photo, used
  only to match faces within that album. Matching runs in the container; Gemini
  never decides who is in a photo.
- **Gemini's notes:** per photo, a short description and quality score from
  Gemini on Vertex AI, from a copy shrunk to 768 px on the long side.
- **Per account:** the names typed for people and the recent albums, under a
  hash of the email address.
- **Where:** Firestore and Cloud Run in the project's own Google Cloud project.
  Face crops and thumbnails stay in memory only. The Google sign-in lives in a
  signed session cookie and is removed on sign-out.
- **How long:** until deleted. The album menu's "Delete this album's data"
  removes the face data, Gemini's notes and the user's names for that album.
- **Who:** a scan is shared by everyone who can open the same Drive folder;
  every album request is checked against Drive first (`_need_album`).

## Setup: Google OAuth credentials

You need these before the app can do anything.

1. Go to <https://console.cloud.google.com/> and create a project.
2. **APIs & Services → Library →** enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen →** choose **External**.
   Fill in the app name, your email, and save.
4. Under **Audience**, add the Google accounts that may use the app as **test
   users** — up to 100 of them. See the note on verification below.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Web application.**
   - Authorised redirect URI: `https://YOUR-APP-URL/oauth2/callback`
   - Copy the **client ID** and **client secret**.

### About the 100-user limit

The app reads someone else's shared album, which needs the `drive.readonly`
scope. Google classes that as a **restricted** scope: publishing the app to
unlimited users requires Google verification plus a third-party CASA security
assessment, which costs money and takes weeks.

For a graduation class this does not matter — leave the app in **Testing** mode
and add your friends' emails as test users. The only cost is that their consent
expires after 7 days and they sign in again.

If you later want it fully public, the route is to switch to the
`drive.file` scope with the Google Picker, which is *not* restricted, at the
price of the user picking the folder through Google's own dialog instead of
pasting a link.

---

## Deploy

The app is a single Docker container. It reads all its configuration from
environment variables.

| variable               | required | meaning                                        |
|------------------------|----------|------------------------------------------------|
| `GOOGLE_CLIENT_ID`     | yes      | from the step above                            |
| `GOOGLE_CLIENT_SECRET` | yes      | from the step above                            |
| `PUBLIC_BASE_URL`      | yes      | e.g. `https://you-facefinder.hf.space`         |
| `SESSION_SECRET`       | yes      | any long random string                         |
| `DATA_DIR`             | no       | mount a volume here to keep the index          |
| `DEFAULT_THRESHOLD`    | no       | default match strictness (0.38)                |
| `DRIVE_ACCESS`         | no       | `limited` (default) or `full`, see below       |
| `CLUSTER_THRESHOLD`    | no       | similarity that links two faces when grouping (0.46) |
| `COPY_WORKERS`         | no       | parallel copies while creating folders (4)     |
| `INDEX_WORKERS`        | no       | parallel downloads while scanning (4)          |
| `THUMB_SIZE`           | no       | pixels on the long edge when scanning (1600)   |

#### `DRIVE_ACCESS`: writing into a folder the user already has

With the default `limited`, the app asks for `drive.readonly` (read the album)
plus `drive.file` (write only to folders it created itself). That is enough to
create new folders in My Drive. It is **not** enough to write into an existing
folder whose link the user pastes: Google refuses, and the export falls back to
a new folder in My Drive and says so on the result card.

Set `DRIVE_ACCESS=full` to ask for the whole-Drive scope instead. Pasted
destination folders then work directly. The consent screen will say the app can
see, edit, create and delete all of the user's Drive files, and everyone has to
sign in again once. Google classes both `drive.readonly` and `drive` as
restricted, so this does not change the 100-test-user situation.

### Option A - GitHub Codespaces (free, and the quickest to try)

Runs the app on GitHub's machines straight from this repo, with a public
HTTPS URL anyone can open on a phone. Free tier is 120 core-hours a month,
which is about 60 hours on a 2-core machine.

Worth knowing: a codespace has proper datacenter cores and no thermal
throttling, so indexing an album is typically several times faster than on a
thin laptop, where a 15 W CPU throttles hard under a sustained scan.

1. Add your OAuth credentials as **Codespaces secrets** (not in the repo):
   <https://github.com/settings/codespaces> -> New secret ->
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, granted to this repository.
2. **Code -> Codespaces -> Create codespace**. The devcontainer installs the
   dependencies and pulls the face model on first build, so give it a few
   minutes.
3. In the codespace terminal:

   ```bash
   ./scripts/run-codespace.sh
   ```

   It works out the public URL from the codespace itself and prints the exact
   redirect URI to register - PUBLIC_BASE_URL and the redirect URI cannot
   drift apart, which is the usual reason sign-in fails.
4. Paste that redirect URI into the OAuth client in Google Cloud Console.
5. **PORTS** tab -> right-click port 8000 -> **Port Visibility -> Public**.
   Without this, visitors hit a GitHub login wall instead of the app.

Once the secrets are stored, starting the codespace is the whole procedure -
the devcontainer starts the server for you and forwards port 8000 publicly.
`tail -f /tmp/facefinder.log` shows what it is doing.

**A stopped codespace cannot be woken by a visitor.** Idle for the timeout
period and it stops; the URL is then dead until you open the codespace again.
Nothing in the repo can change that, so it is worth raising the timeout to its
240-minute maximum under <https://github.com/settings/codespaces>. If you need
a URL that stays up unattended for days, a small always-on host is the honest
answer, not a codespace.

Other caveats: a long scan with nobody connected can be interrupted (it resumes
by skipping already-indexed file IDs). The index lives in the codespace, so deleting it loses the index,
not the model. And it is a development environment rather than a hosting
product - fine for one graduation, not a permanent home.

### Option B - Hugging Face Spaces

2 vCPU and 16 GB RAM, which is far more memory than any other tier here
and makes this a comfortable fit for a model workload.

**No longer free.** Hugging Face now requires a paid plan (PRO for personal
accounts) to create Gradio or Docker Spaces - only Static Spaces are free.
PRO also unlocks "Protected" visibility, which is the setting you want here:
the source stays private while the running app is publicly reachable. A
*Private* Space returns 404 to everyone but you, so classmates cannot use it.

1. Create a Space, SDK = **Docker**, visibility public or private.
2. Put this at the very top of the Space's `README.md`:

   ```yaml
   ---
   title: FaceFinder
   sdk: docker
   app_port: 8000
   ---
   ```
3. **Settings → Variables and secrets:** add the four required variables as
   *secrets*. `PUBLIC_BASE_URL` is `https://<user>-<space>.hf.space`.
4. Push this folder to the Space's git remote. It builds and deploys itself.

Caveat: persistent storage for Spaces was retired in 2026, so a restart clears
the index and the next search re-scans the album.

### Option C - Google Cloud Run

Neat because it lives in the same Google Cloud project as the OAuth client, and
it scales to zero so an idle app costs nothing.

```bash
gcloud run deploy facefinder --source . --region asia-southeast1 \
  --allow-unauthenticated --memory 2Gi --cpu 2 --timeout 3600 \
  --set-env-vars "PUBLIC_BASE_URL=https://YOUR-URL,DEFAULT_THRESHOLD=0.38" \
  --set-secrets "GOOGLE_CLIENT_ID=gcid:latest,GOOGLE_CLIENT_SECRET=gcsec:latest,SESSION_SECRET=sess:latest"
```

Deploy once to learn the URL, put that URL into `PUBLIC_BASE_URL` and into the
OAuth client's redirect URI, then deploy again.

### Running it locally (only for development)

```bash
pip install -r requirements.txt
export GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
       PUBLIC_BASE_URL=http://localhost:8000 SESSION_SECRET=dev
uvicorn app.main:app --reload --port 8000
```

Add `http://localhost:8000/oauth2/callback` as a second redirect URI.

---

## Layout

```
app/config.py         environment configuration
app/faces.py          detection + embedding (insightface, opencv fallback)
app/cluster.py        group an album's faces into people
app/google_drive.py   Drive listing, thumbnail fetch, folders, server-side copy
app/store.py          SQLite cache of embeddings, one row per face
app/main.py           FastAPI routes
app/static/index.html the whole front end
tests/test_matching.py accuracy check on real photos
tests/test_pipeline.py index and search without Google
tests/test_people.py  grouping, multi-person search and export, through the routes
tests/fakedrive.py    a stand-in for Google Drive backed by local folders
tests/devserver.py    the whole app on that stand-in, to try the UI offline
```

### Trying the UI without Google

```bash
python -m tests.devserver
```

Open `http://127.0.0.1:8077/dev/login`, then paste the album link it prints. The
album is the sample photos in `tests/img`, and "copied" folders are written
under `data/dev-export`. Nothing in `app/` knows about this; the stand-in lives
entirely in `tests/`.

## Performance

Roughly 4–8 photos per second per CPU core when scanning, dominated by the
thumbnail download rather than the model. A 4,000-photo album takes about 10–15
minutes on a 2-core host, once. Every search after that returns in well under a
second, for every person who searches that album.

---

## Visual design

FaceFinder's own pink system, made for this project: a pale pink page, one
white workspace with the header, album menu and tabs in a single bar, navy
headings in Mitr, text in Noto Sans Thai (both cover Thai and Latin), and one
strong pink (`--accent: #d6336c`) kept for primary actions and the active tab.
The camera mascot (`app/static/img/cam-*.png`, drawn for FaceFinder) appears on
the start, processing and done screens. All colours are tokens at the top of
`app/static/index.html`.
