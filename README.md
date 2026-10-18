# FaceFinder

Sort a big shared Google Drive album by who is in it: every person gets their
own folder of photos in your Drive.

Built for the graduation-photo problem: the photographer hands over one folder
with 4,000 photos in it, and finding yourself (or sorting out who gets which
photos) means scrolling for an hour.

## For judges

- **Open:** <https://facefinder-508213.web.app>
- **Sign in with Google.** Google may show "Google hasn't verified this app".
  Press **Advanced**, then **Go to FaceFinder**. The app asks to read Drive so
  it can open the shared album.
- **Open the Sample album card** on the start page (it shows after sign-in). It
  holds photos of made-up people created with Gemini.

**What to try in 2 minutes:**
1. **Everyone:** see the album grouped into people; type a name on a face.
2. **Find people:** add a person with one face photo and see their photos;
   open Best 10 to read Gemini's reasons.
3. **Sort:** describe a folder in plain words and watch photos fill it.
4. **Cull photos:** see Keep, Review and Rejected, each photo with a reason.
5. **Export to Drive:** copies land in a new `FaceFinder - <album name>` folder in
   your own Drive. You can delete that folder afterwards.

Submission notes, architecture and video script: [`docs/SUBMISSION.md`](docs/SUBMISSION.md).

## How it works

![FaceFinder architecture: the browser reaches Firebase Hosting, which forwards every request to Cloud Run. Cloud Run runs the FastAPI app and the InsightFace face model, which does all face matching. Cloud Run talks to the Google Drive API, Firestore and Gemini on Vertex AI; Gemini only writes notes and sorts photos.](docs/architecture.svg)

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
has no per-photo fee and no token limit, and its decisions are repeatable. We
have not benchmarked Gemini for identity matching; we keep that job on a
dedicated face model on purpose. Gemini does the
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

See [Privacy: what FaceFinder keeps](#privacy-what-facefinder-keeps) below.

## Privacy: what FaceFinder keeps

- **No photo library is kept.** Photos are processed temporarily; a resized copy
  goes to Gemini on Vertex AI. They are read from Google Drive with the user's own
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
4. Under **Audience**, press **Publish app** so the status reads **In
   production**. See the note on verification below.
5. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Web application.**
   - Authorised redirect URI: `https://YOUR-APP-URL/oauth2/callback`
   - Copy the **client ID** and **client secret**.

### About the 100-user limit

The app reads someone else's shared album, which needs the `drive.readonly`
scope. Google classes that as a **restricted** scope: publishing the app to
unlimited users requires Google verification plus a third-party CASA security
assessment, which costs money and takes weeks.

FaceFinder is **published (In production) without verification**, so anyone
can sign in: Google first shows a "Google hasn't verified this app" warning
(press Advanced, then Go to FaceFinder). Google limits an unverified app to 100
users. Do not leave the app in Testing mode: then only listed test users can
sign in, and their sign-in expires after 7 days.

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
| `PUBLIC_BASE_URL`      | yes      | e.g. `https://facefinder-508213.web.app`; sign-in returns here |
| `SESSION_SECRET`       | yes      | any long random string                         |
| `DATA_DIR`             | no       | mount a volume here to keep the index          |
| `DEFAULT_THRESHOLD`    | no       | default match strictness (0.38)                |
| `DRIVE_ACCESS`         | no       | `limited` (default) or `full`, see below       |
| `CLUSTER_THRESHOLD`    | no       | similarity that links two faces when grouping (0.46) |
| `COPY_WORKERS`         | no       | parallel copies while creating folders (4)     |
| `INDEX_WORKERS`        | no       | parallel downloads while scanning (4)          |
| `THUMB_SIZE`           | no       | pixels on the long edge when scanning (1600)   |
| `STORE`                | no       | `sqlite` (default) or `firestore` (Cloud Run)  |
| `GOOGLE_CLOUD_PROJECT` | for Gemini/Firestore | the Google Cloud project           |
| `GEMINI_MODEL`         | no       | default `gemini-3.5-flash`                     |
| `GEMINI_LOCATION`      | no       | Vertex AI location (`global` on Cloud Run)     |
| `GEMINI_WORKERS`       | no       | parallel Gemini calls while scanning (24)      |
| `SAMPLE_ALBUM`         | no       | a Drive folder shared "Anyone with the link", shown as the sample album |

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
restricted, so this does not change the 100-user limit.

### Google Cloud Run (what FaceFinder uses)

From Cloud Shell, in this repo:

```bash
CPU=4 bash scripts/deploy-cloudrun.sh
```

The script enables the APIs, stores the secrets in Secret Manager, creates the
Firestore database and deploys with the settings the app needs: **one instance**
(`--max-instances 1`) with **CPU always on** (`--no-cpu-throttling`), because
scans and exports run as background jobs inside the instance, and
`STORE=firestore`, because Cloud Run's disk is wiped on every restart. It then
puts Firebase Hosting in front (`scripts/deploy-firebase.sh`). Add
`SAMPLE_ALBUM="<Drive folder link>"` before `CPU=4` to set the sample album; it
is remembered for later deploys. Every deploy restarts the instance and stops a
running scan or export (the scan can be resumed).

GitHub Codespaces and Hugging Face Spaces were tried earlier and are not used:
a codespace sleeps when idle, and Docker Spaces now need a paid plan.

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
app/store.py          SQLite store (local), one row per face
app/store_firestore.py the same functions on Firestore (Cloud Run)
app/gemini.py         Gemini on Vertex AI: photo notes, sorting, suggestions
app/curate.py         culling: bursts, flaws, Best 10
app/main.py           FastAPI routes
app/static/index.html the whole front end
tests/test_matching.py accuracy check on real photos
tests/test_pipeline.py index and search without Google
tests/test_people.py  grouping, multi-person search and export, through the routes
tests/test_gemini.py  the Gemini features, scans, stop/resume, names, delete
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

An estimate from an earlier setup, not a measurement on the current Cloud Run
service: roughly 4–8 photos per second per CPU core when scanning, dominated by the
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
