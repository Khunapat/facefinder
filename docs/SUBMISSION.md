# FaceFinder: submission pack

Google Cloud AI Builder Cup 2026, theme: Media, Content & Digital Experiences.
Live app: <https://facefinder-508213.web.app>

Numbers marked **[TIME FROM TEST]** still need a measured value.

Submission checklist (from the official rules): theme **Media, Content & Digital
Experiences**; working deployed link; public GitHub repository; deck as a PDF;
a public YouTube, Vimeo or Google Drive video of **3 to 4 minutes** (the submission form's rule; aim for about 3:30); everything in
English.

---

## 1. Pitch and description

**One line:** FaceFinder turns one huge shared Google Drive photo album into a
folder per person, so everyone gets their photos in minutes, not hours.

**Description (150 words):**
After a graduation, the photographer shares one Google Drive folder with
thousands of photos. Finding yourself, or sending each friend their photos,
means scrolling for an hour. FaceFinder fixes that. Sign in with Google, paste
the album link, and FaceFinder scans it once. A face-recognition model
(InsightFace) finds every face and groups them into people, so you can name the
people you want or upload a face photo to find someone. Gemini on Vertex AI does
the jobs a face model cannot: it judges each photo's quality to help the
photographer cull, writes a short description so you can sort the album by plain-language descriptions, suggests folders, and explains each pick in a
person's Best 10. When you are happy, FaceFinder creates one folder per person
in your own Drive and copies their photos in. Nothing in the original album is
changed, and photos are never stored by FaceFinder.

---

## Brief description for the submission form

FaceFinder turns one shared Google Drive event album into one folder per person.
Paste the album link and FaceFinder scans it once: an InsightFace face model,
running inside our Cloud Run container, groups every face into people, and
Gemini on Vertex AI writes one short note per photo with a quality score, flaws
and a description. Anyone can then name a face or upload a selfie to find a
person, let Gemini suggest Keep, Review or Rejected with a reason for each
photo, sort the album by a plain-word description, and copy one folder per
person into their own Drive. Originals are never changed and photos are never
stored.

Google services: **Cloud Run** runs the whole app (FastAPI, the face model and
background scans). **Firestore** stores face data, Gemini's notes, typed names
and recent albums, so scans survive restarts. **Firebase Hosting** gives the
public address and forwards every request to Cloud Run. **Gemini** (Vertex AI)
judges and describes each photo once (cached, so rescans cost nothing), sorts
by description and suggests folders. The **Google Drive API** reads albums and
copies photos with the user's own sign-in.

## 2. How we use Google Cloud

**Face matching uses the InsightFace buffalo_l model running inside our Cloud
Run container, not Gemini.** Gemini never decides who is in a photo.

**Cloud Run.** The whole app runs here as one Docker container: the FastAPI web
server, the front end, and the InsightFace face model, which is built into the
image. It runs in `asia-southeast1` with **one instance** (`--max-instances 1`)
and CPU always on (`--no-cpu-throttling`), deployed with 4 CPUs. The reason:
album scans and folder exports run as background jobs inside the web process,
and their progress is kept in memory, so they need one instance that keeps its
CPU between requests. Scans and exports run as background jobs inside the instance, so no request
has to wait for them.

**Firestore.** Cloud Run's disk is wiped on every restart, so everything that
must last lives in Firestore: the album's scan status; for each photo its size,
a fingerprint for spotting near-identical frames, the **face data** (a
512-number embedding and box per face) and **Gemini's notes** (description,
quality score, flaws, reason); the **names** each account types for people; and
each account's **recent albums**. Accounts are stored under a hash of the email
address. Each photo is one Firestore document.

**Firebase.** Firebase **Hosting** gives the app its public address
(`facefinder-508213.web.app`) and forwards every request to the Cloud Run
service (a `run` rewrite in `firebase.json`). That is all it does. Firebase
does **not** handle sign-in (Google sign-in is done by the app itself with
OAuth), does not store data, and does not run code. The browser never talks to
Firestore directly; only Cloud Run does.

**Gemini on Vertex AI.** Gemini (default model `gemini-3.5-flash`) is reached
through Vertex AI with the Cloud Run service account, so no API key is needed.
During the scan, each photo is shrunk to 768 px and sent **once** to Gemini,
which returns a quality score, flaws (blurry, eyes closed, cut off...), a reason
and a short description. That one note powers:
- **Cull photos:** Keep / Review / Rejected piles for the photographer, each
  photo with a reason.
- **Sort:** describe a folder in plain words (for example "people in
  blue staff shirts") and Gemini puts the matching photos in it, reading the
  stored descriptions rather than the photos again.
- **Folder suggestions:** Gemini reads the album's descriptions and proposes
  ways to sort it.
- **Best 10:** a person's best photos, each with Gemini's one-line reason.

Results are cached per photo (Drive file id plus checksum), so a rescan of the
same photos costs nothing.

**Google Drive API.** FaceFinder reads the album with the **user's own Google
sign-in** and downloads Drive's 1600 px previews instead of the full originals (the
original only when Drive has no preview). Export uses
Drive's server-side `files.copy`: it creates new folders in the user's Drive and
**copies** photos into them. It never moves, changes or deletes anything in the
album.

---

## 3. Architecture

```mermaid
flowchart LR
  B[Browser<br/>phone or laptop] --> H[Firebase Hosting<br/>facefinder-508213.web.app]
  H -->|every request forwarded| R[Cloud Run<br/>FastAPI + InsightFace face model]
  R -->|read album, copy photos<br/>with the user's sign-in| D[Google Drive API]
  R -->|face data, Gemini notes,<br/>names, recent albums| F[(Firestore)]
  R -->|768 px photo once per photo;<br/>text for Sort and suggestions| G[Gemini on Vertex AI]
```

1. The browser opens `facefinder-508213.web.app`; Firebase Hosting forwards
   every request to the Cloud Run service.
2. The user signs in with Google and pastes an album link; Cloud Run reads the
   album's thumbnails through the Drive API with the user's own sign-in.
3. Cloud Run finds every face with InsightFace and asks Gemini once per photo
   for a quality note and description; both are saved in Firestore.
4. Everyone, Find people, Best 10 and Cull work from the stored data; Sort and
   folder suggestions send Gemini the stored text, not the photos.
5. On export, Cloud Run creates one folder per person in the user's Drive and
   copies the photos in with Drive's server-side copy.

---

## 4. Privacy and safety

What FaceFinder keeps (the same as the app's "What FaceFinder keeps" window):
- **Photos are not stored.** They are read from Drive with your sign-in when
  needed. Nothing in your Drive is changed, moved or deleted; exports are copies.
- **Face data:** per face, 512 numbers and where the face sits in the photo. It
  is not a picture, and it is used only to match faces in that album.
- **Gemini's notes:** a short description and quality score per photo, made
  from a copy shrunk to 768 px, sent through Vertex AI. Google Cloud's terms say
  this data is not used to train Google's models.
- **Your names and recent albums,** kept under a coded form of your email. Only
  you see them.
- **Where:** FaceFinder's own Google Cloud project (Firestore, Cloud Run). Face
  crops and thumbnails are kept in memory only. Your sign-in lives in a signed
  cookie and is removed when you sign out.
- **How long:** until deleted, from the album menu ("Delete this album's
  data"). People who can open the same Drive folder share its scan; FaceFinder
  checks with Drive that they can open it first. Deleting removes the scan for
  everyone who uses this folder in FaceFinder; they can scan it again.

**Model licence.** The `insightface` Python library is MIT-licensed, but its
pretrained model packs, buffalo_l included, are released for non-commercial
research use only. FaceFinder uses them as a non-commercial competition
prototype. A commercial release would need a commercial licence from
InsightFace or a commercially licensed face model; only `app/faces.py` would
change.

**Sample photos.** The demo album shows made-up people created with Gemini. No
real people and no public figures.

---

## 5. Video script (3 to 4 minutes, aim for 3:30)

The submission form asks for 3 to 4 minutes and penalises longer videos. Show the
live app working; say on screen when a scan is sped up.
On screen at the start and whenever the sample album is visible:
*"Ploy, Ton, Mint, Bank and Fah are made-up people, created with Gemini."*

| Time | On screen | What I say |
|---|---|---|
| 0:00 | A Drive folder with many graduation photos, scrolling fast. | "After a graduation, the photographer shares one Google Drive folder with hundreds of photos. Finding yourself, or sending each friend their photos, takes an hour of scrolling. And the photographer still has to throw out the blurry shots by hand." |
| 0:25 | Start page; the line about the face model and Gemini. | "FaceFinder fixes that with two kinds of AI. A face-recognition model decides who is in each photo. Gemini on Vertex AI judges how good each photo is and describes what is in it. Gemini never decides who someone is." |
| 0:45 | Sign in with Google, open the Sample album card, the scan screen (caption: "sped up"). | "I sign in with Google and open a shared album. FaceFinder scans it once: it finds every face, and Gemini writes one short note per photo. The album itself is never changed." |
| 1:10 | Everyone: faces grouped; type Ploy, Ton and Mint; the cards tick themselves. | "Everyone shows each person in the album. I type a name, and that person gets a folder. If someone appears twice, giving both cards the same name joins them." |
| 1:35 | Find people: upload Mint's selfie, her photos appear; open Best 10 and read a reason; untick one photo. | "Or I upload one selfie. Mint's photos appear in about a second. Best 10 picks her best shots, and Gemini says why for each one. I stay in control and untick anything I don't want." |
| 2:05 | Sort: tap "Throwing caps", press Sort; then "Suggest folders with Gemini". | "Sort lets me describe a folder in plain words, like 'graduates throwing their caps'. Gemini fills it from the notes it wrote during the scan, so it does not look at every photo again, and it can suggest folders itself." |
| 2:35 | Cull photos: Keep, Review, Rejected; open the blurry photo and a burst look-alike with "tap to switch". | "For the photographer, Cull sorts the album into Keep, Review and Rejected, with a reason for every photo: blurry, eyes closed, or a weaker shot of the same moment." |
| 3:00 | Export to Drive, the done card, then Google Drive on a phone with the folders. | "One click copies each person's photos into a folder in my own Drive. Copies are made inside Google, so it takes seconds, and the original album is never touched." |
| 3:20 | "What FaceFinder keeps" window, then the architecture picture, then the logo. | "Photos are never stored, and every album's data can be deleted at any time. FaceFinder runs on Cloud Run with Firestore and Firebase Hosting, with Gemini on Vertex AI. FaceFinder: every friend's photos, sorted." |

## 6. Deck outline

1. **Problem**
   - One shared Drive folder after an event holds thousands of photos.
   - Finding yourself means scrolling for an hour; sending friends theirs is worse.
   - Photographers also spend hours culling before they share.
2. **Solution: FaceFinder**
   - Paste a Drive album link; the album is scanned once.
   - Find people, sort by description, cull, pick the best.
   - One folder per person, copied into your own Drive.
3. **Demo**
   - Sample album of made-up people created with Gemini.
   - Find people, Best 10, Sort by description, Cull, export.
   - Live at facefinder-508213.web.app.
4. **How Gemini is used**
   - One look per photo (768 px): quality score, flaws, reason, description.
   - Powers Cull, Sort by description, folder suggestions and Best 10 reasons.
   - Cached per photo, so a rescan costs nothing; face matching stays on InsightFace.
5. **Architecture**
   - Firebase Hosting in front of one Cloud Run service.
   - Firestore for face data, Gemini notes, names and recent albums.
   - Drive API with the user's sign-in; Gemini on Vertex AI without API keys.
6. **Feasibility and scale**
   - Works today: deployed on Cloud Run behind Firebase Hosting, tested end to end on a real Drive album.
   - One scan per album, shared by everyone who can open it; Gemini results are cached per photo, so cost grows with photos, not with users.
   - Next step to scale: move scans and exports from the one instance to Cloud Run jobs or Cloud Tasks; Firestore already holds all state.
7. **Face model accuracy**
   - InsightFace buffalo_l, running in the container.
   - Same person scores 0.75 to 0.98; a different person scores -0.05.
   - Measured on the repo's sample photos (`tests/test_matching`).
8. **Impact**
   - Finding one person: [TIME FROM TEST] instead of [TIME FROM TEST].
   - Scanning a test album of [PHOTOS FROM TEST] photos: [TIME FROM TEST].
   - Server-side copy: no photo is downloaded or uploaded again.
9. **Privacy**
   - Photos are never stored; exports are copies, the album is never changed.
   - Face data is 512 numbers per face, not a picture; deletable from the album menu.
   - Gemini data via Vertex AI is not used to train Google's models.
10. **What's next**
   - Licensed face model for a commercial release.
   - Google verification so the "unverified app" warning goes away.
   - More events beyond graduation: weddings, sports days, conferences.

---

## 7. For judges

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
