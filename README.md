# FaceFinder

Find every photo of one person inside a big shared Google Drive album, and copy
them into your own Drive folder.

Built for the graduation-photo problem: the photographer hands over one folder
with 4,000 photos in it, and finding yourself means scrolling for an hour.

## How it works

1. You sign in with Google.
2. You paste the link of the album the photographer shared.
3. The server scans the album once and stores a **face embedding** — a vector of
   512 numbers — for every face it finds. This is the slow step, and it happens
   only once per album.
4. You upload one to three photos of your own face.
5. Your face becomes a vector too, and matching is a dot product against the
   cached vectors. This part takes milliseconds.
6. You uncheck any wrong results, then the app copies the rest into your Drive.

### There is no LLM and no AI API key involved

Face recognition is not a language-model job. It uses **InsightFace buffalo_l**
(an ArcFace model) running locally in the container through ONNX Runtime. It is
free, needs no account, and has no token limit. Asking Gemini "is this the same
person?" would be slower, more expensive, and *less* accurate.

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

The server stores face vectors and file IDs. It does not store the photos —
image bytes are fetched, embedded, and discarded. Copies land in the user's own
Drive; the app never takes ownership of the album.

---

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
| `INDEX_WORKERS`        | no       | parallel downloads while scanning (4)          |
| `THUMB_SIZE`           | no       | pixels on the long edge when scanning (1600)   |

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

Caveats: codespaces stop after about 30 minutes idle, so a long scan with
nobody connected can be interrupted (it resumes by skipping already-indexed
file IDs). The index lives in the codespace, so deleting it loses the index,
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
app/google_drive.py   Drive listing, thumbnail fetch, server-side copy
app/store.py          SQLite cache of embeddings, one row per face
app/main.py           FastAPI routes
app/static/index.html the whole front end
tests/test_matching.py accuracy check on real photos
```

## Performance

Roughly 4–8 photos per second per CPU core when scanning, dominated by the
thumbnail download rather than the model. A 4,000-photo album takes about 10–15
minutes on a 2-core host, once. Every search after that returns in well under a
second, for every person who searches that album.

---

## Visual design

The front end follows a design system adapted from the community-written
`DESIGN.md` for Airbnb in <https://github.com/VoltAgent/awesome-design-md>
(`design-md/airbnb/DESIGN.md`, kept in `design-refs/` for reference).

What was taken: the 4px spacing scale, the radius scale (4/8/14/20/32/full),
the single-shadow elevation model, 48px buttons at 8px radius, 56px inputs,
the pill search surface with a circular accent orb, and the "open hero, dense
photo grid below" whitespace rhythm.

What was changed: Airbnb Cereal is proprietary, so the stack falls back to
Nunito Sans; no Airbnb name, logo or wording appears anywhere.

**Before you publish this, change the accent.** `--accent: #ff385c` in
`app/static/index.html` is Airbnb's brand colour. Those files are community
analyses of public websites, not official design systems, and the brands do not
endorse them — they are meant as a direction to start from, not a skin to copy.
Editing that one token, plus `--accent-active` and `--accent-disabled`, restyles
the entire app.
