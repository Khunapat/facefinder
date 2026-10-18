> Answers come from the code and docs at commit a8b5e24 (18 October 2026); every file:line points to that commit.
> Commit 4af5620 later moved some `app/static/index.html` lines down by a few, and Best 10 now shows only for
> people with more than 10 photos.

# FaceFinder: 15 questions judges are likely to ask

Each question has a short answer you can say out loud. "Where" shows the proof
in the repo. "Note for us" is for the team only; do not read it out.

Placeholders: **[TIME FROM TEST]** is a time we still have to measure.
**[PRICE ...]** is a price to look up on the day. **[TOKENS ...]** is a token
count to read from Vertex AI usage after a real scan.

---

## 1. Why don't you use Gemini to recognise faces?

Because a face model is the right tool for that, and Gemini is not. FaceFinder
runs InsightFace buffalo_l (an ArcFace model) inside our Cloud Run container.
During the scan it turns each face into 512 numbers once. After that, "is this
the same person?" is a dot product against numbers already stored: no API
call, and the same answer every time. With Gemini, every search would send
photos again, so cost would grow with photos × searches, and a generative
model would decide who someone is. Gemini does what a face model cannot:
quality scores, flaws, descriptions, sorting, folder suggestions and the
reasons in Best 10. Its prompt tells it not to invent names, not to copy names
from badges, and not to guess age, ethnicity, religion, health, disability or
gender identity.

- Where: `app/faces.py:37-71` (model on CPU, built into the image),
  `app/main.py:652` (`sims = mat @ query`), `app/cluster.py:33` (fixed seed:
  same album, same groups), `app/gemini.py:126-134` (no names, no sensitive
  guesses), `app/curate.py:1` (Cull and Best 10 read saved notes only).
- Note for us: we never measured Gemini on face matching. Say "we expect it to
  be slower and costlier", not "we measured it is less accurate".

## 2. How accurate is it?

We have small checks, not a full benchmark. `python -m tests.test_matching`
runs on the 5 sample photos in `tests/img` (2 people, one group photo). Same
person in another photo scored 0.78, same person at low resolution 0.98, same
person inside a group photo 0.75. A different person scored -0.05. The match
line is 0.38. The test's "separation" (lower of the two single-person scores
minus the different person) is about 0.83; `requirements.txt` records 0.828
for the pinned library versions, and the README rounds it to 0.8.
`python -m tests.test_people` groups those same 5 photos (6 faces) into exactly
2 people, with the group photo under both people. For small faces at the back
of a group photo (about 18 px wide in a made-up crowd), the commit that added
scanning at 640 px and 1280 px reports all 40 found, against 0 of 40 at 640 px
only; the test passes at 36 or more. These are local test scripts (the
`tests/` folder is left out of the Cloud Run upload), and we have not measured
accuracy on a real graduation album yet.

- Where: `tests/test_matching.py:46-61` and `65-83`, `README.md:83-94`
  ("Measured on the bundled sample photos"), `requirements.txt:8-11`,
  `tests/test_people.py:78-89`, commit `eaf4308` (the 40 small faces),
  `.gcloudignore` (`tests/`).
- `HANDOFF.md` section 9 says: "On 16 photos of 5 people, the grouping put
  every face with the right person at all three strictness settings." That
  test is not in the repo, so I could not confirm it.
- Note for us: `tests/img` still holds photos of public figures copied from
  another open-source project (`HANDOFF.md` 7.6). `CLAUDE.md` says no public
  figures in the repo. Replace them before judges open the repo. The numbers
  above will then change, so run the test again.

## 3. What if two people look alike?

The user always decides, and the app gives them three controls. In **Find
people**, the **Match strictness** slider (0.20 to 0.70, default 0.38) sets how
close a face must be. Photos just above the line get a "Check match" tag. In
**Everyone**, the **Grouping** control (Looser / Balanced / Stricter) moves the
grouping line (0.46, minus or plus 0.06). Small faces (under 30 px) and
low-confidence faces are not used to build groups, so they cannot glue two
people together. A photo that fits its group weakly gets "Check match". The
user taps a face, sees all of that person's photos, and can untick any, or
press "Confident only". Nothing is copied until they press **Export to Drive**
and then **Export**.
The opposite mistake, one person split into two cards, is handled too: two
groups whose average faces agree are joined. If two cards remain, give both the
same name and they share one folder.

- Where: `app/static/index.html:678-680` (slider), `693-699` (Grouping),
  `784` (Confident only), `1078` and `1482` ("Check match" rule and tag),
  `805` (the **Export** button); `app/main.py:664`,
  `678`, `715`, `1083` (same name, case ignored, one folder);
  `app/cluster.py:83-103` (clear faces only, then the join), `139`.
- Note for us: no test in the repo covers look-alikes. Very similar faces, for
  example twins, can still end up together; the review step is the safety net.

## 4. How do you handle privacy and deletion?

FaceFinder never stores photos. It reads them from Drive with the user's own
Google sign-in when it needs them, and it never changes, moves or deletes
anything in Drive; export makes copies. What we keep is listed in the app's
"What FaceFinder keeps" window: face data and Gemini's notes per album, plus
each account's names and recent albums, stored under a hash of the email. In
the album menu, **Delete this album's data** removes the album's face data, its
Gemini notes (from the cache too), and your names and recent entry. It is
refused while a scan runs, and nobody can delete the shared sample album.
Signing out clears the cookie that holds the Google sign-in. Gemini is told not
to invent names or guess age, ethnicity, religion, health, disability or gender
identity, and the names users type on Everyone are never sent to Gemini (only
folder names typed in **Sort** are).

- Where: `app/main.py:200` (email hash), `224-248` (delete), `174-177`
  (sign-out), `513-517` (sample album protected); `app/static/index.html:811-837`
  (privacy window, with a link to myaccount.google.com/permissions), `993-1003`
  (delete asks first), `2007-2015` (Sort sends only its own folders);
  `app/gemini.py:126-134`.
- Note for us: Gemini does see each photo (a 768 px copy) to write its note;
  say so if asked. Deleting removes the scan for everyone who uses that folder;
  the window says this. Sign-out does not cancel Google's permission; that is
  done at myaccount.google.com/permissions. Request URLs contain Drive folder
  and file ids (for example `/api/thumb/{file_id}`), so any request logs hold
  them; I did not check the project's log settings. `app/google_drive.py:176`
  logs a file name when it falls back to the original. The privacy window does
  not mention logs.

## 5. What happens to the face data?

For each face, the scan stores 512 numbers (the embedding, about 2 KB), the
face's box in the photo and a detection score. For each photo it also stores
the size and a 64-bit fingerprint used to spot near-copies. All of it is in
Firestore in our own Google Cloud project, one document per photo
(`albums/{folder}/photos/{file}`). The embedding is not a picture. FaceFinder
has no code to turn it back into one, and face crops are cut from the Drive
photo only when shown and kept only in memory. It is still data about a
person's face, which is why it can be deleted. One scan serves everyone who can
open the same Drive folder, so the same album is not scanned twice. Every
album request goes through `_need_album`: this session must have opened the
folder through Drive, and Drive is asked again once 5 minutes have passed.
Matching only compares faces inside one album. Face photos uploaded in Find
people are used once in memory and not saved.

- Where: `app/store_firestore.py:7-15`, `91-105`; `app/curate.py:28-35`
  (fingerprint); `app/main.py:79-112` (`_need_album`), `606-619` (one album's
  faces only), `633-637` (uploaded photos read, not stored), `732-760` (crops
  in memory, per sign-in).

## 6. What does it cost per 1,000 photos?

Short answer: the first scan makes 1,000 Gemini calls, one per photo, each with
a single 768 px image (plus retries if Gemini is busy). A rescan of the same
photos, or a second person opening the same folder, makes 0 calls for photos
that already have a note, because each note is cached by Drive file id +
checksum. After the scan, only Sort and Suggest folders call Gemini, and they
send text only. Cull, Best 10 and the face features make no Gemini calls. The
money formula is below; look up the prices on the day.

**Gemini calls, traced in the code:**

| Step | Gemini calls | What is sent | Where |
|---|---|---|---|
| First scan | 1 per new photo = **1,000** | the photo shrunk to 768 px + the fixed judge prompt | `app/main.py:405-406`, `374-382`; `app/gemini.py:212-217` |
| Rescan, Resume, or another user, same photos with a note | **0** | nothing (cache: Drive id + checksum) | `app/main.py:338-343`, `360-372`, `479-482` |
| Photos whose note failed last time | **1 each**, on the next scan | the photo shrunk to 768 px | `app/main.py:408-422` |
| Suggest folders | **1 per press** | up to 150 saved descriptions, as text | `app/main.py:886-890`; `app/gemini.py:262-264` |
| Sort the photos | **ceil(J / 40) per run** = 25 for 1,000 photos | up to 40 saved descriptions + up to 12 folder rules, as text | `app/main.py:898-917`; `app/gemini.py:27`, `315-319` |
| Cull, Best 10, photo notes, Everyone, Find people | **0** | they read saved notes and face data | `app/curate.py:1`, `app/main.py:623-729`, `812-868` |

J = photos that have a Gemini note (at most N). Retries: a call that gets
HTTP 429, 500, 502, 503 or 504 is tried again. The scan and Sort allow up to 5
attempts, waiting 2, 4, 8 and 16 s between them; Suggest allows 2 attempts,
with one 2 s wait (`app/gemini.py:81-104`, `264`). Each attempt stops after
60 s (`app/gemini.py:78`). A photo whose call still fails has no note: it goes
to Review in Cull (`app/curate.py:96-99`), and the next scan tries it again.
"Delete this album's data" also clears the cached notes, so scanning that
album again pays again (`app/main.py:237`). I could not confirm whether failed
attempts are billed.

**Cost formula for N = 1,000 photos (first scan):**

```
Gemini  = N × [ (T_image + T_prompt) × [PRICE per input token]
              + (T_answer + T_thinking) × [PRICE per output token] ]
        + per Sort run:      ceil(J/40) × (T_sort_in × [PRICE per input token] + T_sort_out × [PRICE per output token])
        + per Suggest press: 1 × (T_sug_in × [PRICE per input token] + T_sug_out × [PRICE per output token])

Cloud Run = T_scan × (4 × [PRICE per vCPU-second] + 8 × [PRICE per GiB-second])

Firestore ≈ N × (4 × [PRICE per document write] + 1 to 2 × [PRICE per document read])
          + N × [PRICE per document read] for each Cull, Best 10, Sort or Suggest press
          + stored data × [PRICE per GiB-month]

Total for 1,000 photos ≈ Gemini + Cloud Run + Firestore
```

- `T_image` = tokens for one image of 768 px on the long side:
  [TOKENS per 768 px image]. `T_prompt` = the judge prompt
  (`app/gemini.py:122-173`). `T_answer` = the JSON note. `T_thinking` =
  thinking tokens; the code sets thinking level LOW (`app/gemini.py:90`). Read
  the real numbers from Vertex AI usage after one scan of the sample album:
  [TOKENS FROM TEST].
- Cloud Run: deployed with `CPU=4` (`README.md:208`, `HANDOFF.md:105`), which
  gives 8 GiB; the script's own default is 2 CPUs and 4 GiB
  (`scripts/deploy-cloudrun.sh:23`, `33`, `115-120`). The CPU is always on, so the
  instance is billed for as long as it is up, not only during requests.
  `T_scan` for 1,000 photos = [TIME FROM TEST]. The page's own time estimate
  uses 2 s per photo with Gemini (0.6 s without), and the code comment says
  this was "measured on Cloud Run, 4 CPUs" (`app/static/index.html:1188`).
  There is no test log for it in the repo.
- Firestore, per new photo: save the photo with its faces, add 1 to the album's
  progress, save Gemini's note on the photo, save the note to the cache
  (4 writes), and read the cache once (`app/main.py:402-406`, `363-380`;
  `app/store_firestore.py:77-148`). The second read is the end-of-scan check
  for photos still without a note, which can read each photo once more
  (`app/main.py:421`). Small extras: one read and one write every 20 s while a
  scan runs (the heartbeat), and the status checks while the page is open
  (`app/main.py:320-327`, `594-603`).
- Drive API calls and network traffic are not in the formula: [PRICE].
- What keeps it low: the sample album is scanned once for all judges, and
  visitors cannot delete it, stop its scan or rescan it from the start
  (`app/main.py:229`, `462`, `513-517`, `581`); users can also choose to scan
  only some days of an album (`app/static/index.html:640`).

## 7. Why only one Cloud Run instance, and how would it scale?

Scans, exports and sorts run as background threads inside the web process, and
their progress is kept in memory (`_jobs`, `_exports`, `_sorts`). A second
instance would not know about a job started on the first, and a CPU that is
throttled between requests would pause the work. So the deploy script sets
`--max-instances 1`, `--no-cpu-throttling`, `--concurrency 40`, and we deploy
with 4 CPUs and 8 GiB. Scans, the album's face data and Gemini's notes are in
Firestore, the session is a signed cookie, and a scan killed by a restart
shows as stopped with Resume. A running sort or export is lost on restart and
the page says to run it again. **Our idea, not built and not in our docs
yet:** put each scan and export on a queue (Cloud Tasks) or run it as a Cloud
Run job, keep job progress in Firestore instead of memory, then let the web
service scale to many instances while the workers scale on their own.

- Where: `app/main.py:36-43`, `311`, `895`, `995`; `scripts/deploy-cloudrun.sh:113-120`;
  `README.md:208`; `app/main.py:320-327` and `520-535` (heartbeat every 20 s;
  silent for 90 s means stopped), `966`, `1139-1140` (lost sort or export).
- Firebase Hosting stops a request at 60 s (code comment, `app/gemini.py:263`),
  so long work cannot run inside a request; scans, exports and sorts run in the
  background. Suggest folders is the one Gemini call the page waits for, so it
  gets only 2 attempts.
- Gemini calls are already parallel: up to 24 at a time per scan, and Sort
  uses a pool of the same size (`app/config.py:73`, `app/main.py:357`, `916`).
- `MIN_INSTANCES` is 0 by default, so the service sleeps when idle and the
  first visit after a quiet time waits for a cold start: [TIME FROM TEST]
  (`scripts/deploy-cloudrun.sh:14-15`).
- Note for us: each photo adds 1 to the same album document in Firestore
  (`app/store_firestore.py:77-84`). With many workers on one album, that
  counter would need batching first.

## 8. Does it work in other languages?

The screens are in English. Gemini reads a folder description written in plain
words, and it also understands other languages (for example Thai, the language
of our first users), because the description is sent to Gemini unchanged and
matched against Gemini's own notes on each photo. Names typed for people are
kept as written, so a name in any script becomes the Drive folder name (the
code only trims spaces and cuts a name at 100 characters). Gemini writes its
photo notes and folder suggestions in English.

- Where: `app/gemini.py` (sort prompt and `ensure_ascii=False`),
  `app/main.py` `_clean_name` (folder names).
- Not tested: sorting quality in languages other than English; the automatic
  tests use English descriptions.

## 9. What about the face model's licence?

The `insightface` Python library is MIT-licensed. Its pretrained model packs,
buffalo_l included, are released by the InsightFace project for non-commercial
research use only. FaceFinder uses them as a non-commercial competition
prototype, and the README and submission say so. For a commercial release we
need a commercial licence from InsightFace or a face model with a commercial
licence. The face model code is all in `app/faces.py`, so that is the file to
swap. Every album would then need a rescan, because vectors from the old model
cannot be compared with the new one, and the match lines in `app/config.py`
(0.38 for search, 0.46 for grouping) would need tuning again for the new model.

- Where: `README.md:76-81`, `docs/SUBMISSION.md` section 4;
  `app/main.py:647-650` (refuses vectors of a different size),
  `716-717` (lines differ by model: lowered by 0.08 for the small fallback
  model); `app/config.py:58`, `70`.
- Note for us: `app/faces.py:74` already has a second engine (OpenCV YuNet +
  SFace) as a fallback. I did not check its licence or measure its accuracy.

## 10. What happens if Drive access is removed?

Every album request goes through `_need_album`. The session must have opened
the album through Drive, and Drive is asked again once 5 minutes have passed
since the last check. If Drive now answers 403 or 404, the server replies "You
no longer have access to this album in Google Drive." If that comes back on a
status check (opening the album or watching a scan), the page goes back to the
start screen and shows the no-access box: which account you are signed in as,
why, and three ways out: **Open in Drive** to request access (with **Copy a
message for the owner**), **I shared it, try again**, and **Use another Google
account**. In the other tabs it shows as an error line. New photos and
thumbnails are fetched from Drive with the user's own sign-in. Until the next
check (up to 5 minutes), what the page already loaded and face crops the
server holds in memory can still show. Copies already in the user's Drive are
theirs to keep, and the shared scan stays for people who still have access.

- Where: `app/main.py:79` (`ALBUM_RECHECK = 300`), `82-112`, `732-760` (face
  crops cached per sign-in); `app/google_drive.py:157-168`;
  `app/static/index.html:883-913` (the box), `1357` (shown when a status check
  is refused).
- If the user removes FaceFinder in their Google account, the album check
  turns a Drive 401 or a failed token refresh into "Your Google sign-in has run
  out. Sign in again." (`app/main.py:95-99`).
- Note for us: when the saved access token has already expired, `_creds`
  (`app/main.py:66-76`, `app/google_drive.py:41-42`) refreshes it outside any
  `try`. If that refresh fails (access removed), the server answers 500. On the
  scan screen every refusal except no-access, 401 included, ends as "Cannot
  reconnect" (`app/static/index.html:1355-1361`), so the user never sees "Sign
  in again" there. `/api/thumb` has no `_need_album` check and reuses a
  photo's Drive details for up to 10 minutes (`app/main.py:763-783`); I could
  not confirm whether Drive refuses that saved thumbnail link once access is
  removed.

## 11. What about offline or slow connections?

FaceFinder needs a connection (there is no offline mode), but the phone does
little of the work. The server reads Drive's own 1600 px preview instead of the
original (the original only when there is no preview or it fails), and Gemini gets a 768 px
copy. The page loads small, lazy-loaded pictures: 200 to 400 px in grids,
192 px face crops, and 1200 px only in the preview. Scans and exports run on
the server, so the user can close the page and come back (a sort also runs on
the server, but only the page that started it can read the result). The scan
progress check retries with longer waits and, after 3 failures, says "Cannot
reconnect. Try again when your connection is back." Export and Sort checks try
up to 5 times, then say "Lost the connection. The work carries on; check your
Drive in a minute."
Export uses Drive's server-side `files.copy`, so no photo passes through the
phone, and pressing **Export to Drive** again copies only what is missing.

- Where: `app/google_drive.py:157-184` (preview first), `217-245` (copy;
  copies carry `appProperties.ff_src`); `app/gemini.py:176-186` (shrink);
  `app/static/index.html:1286-1366` (scan progress), `935-942` (`retrying`),
  `2018`, `2211` (Sort and Export checks), `1256`, `1480`, `1576`, `1884`
  (picture sizes), `2237-2238` (export again); `app/faces.py:151` (192 px
  crop); `app/main.py:962-968` (a sort is read only by the session that
  started it).
- Also: the user can scan only some days of an album ("By the day they were
  taken", `app/static/index.html:640`).

## 12. What was the hardest part?

Three things. First, long jobs on Cloud Run. Scans and exports are background
threads, so we needed one instance with the CPU always on, and a deploy or
restart still kills a running scan. We added a heartbeat every 20 s, Resume for
a scan that went quiet, and an export that skips photos already copied. A stuck
Gemini call once kept a scan "scanning" for 9 minutes, so each call now stops
after 60 s and Stop no longer waits for Gemini. Second, Google sign-in. Reading
someone else's shared folder needs the restricted `drive.readonly` scope, so
without Google verification users see an "unverified app" warning and the app
is capped at 100 users. We also had to carry the PKCE verifier across the
sign-in redirect and name the cookie `__session`, because Firebase Hosting
drops every other cookie. Third, keeping Gemini cheap: one 768 px look per
photo, cached, and every later feature reads that text.

- Where: commit `d90bcb5` (the 9-minute stuck scan), `889e504` (cache and
  heartbeat), `ad3b64c` (PKCE), `02dd78e` (`__session`); `README.md` "About
  the 100-user limit"; `app/main.py:24-32`, `131-135`.
- Also hard, if asked: small faces at the back of group photos. At 640 px a
  face 15 px wide was never found; scanning at 640 and 1280 px finds them
  (commit `eaf4308`, `app/faces.py:54-59`).

## 13. What is next?

From our plan: a face model with a commercial licence, Google verification so
the "unverified app" warning and the 100-user cap go away, and more events
beyond graduation: weddings, sports days and conferences. Another way to open
the app to everyone is the non-restricted `drive.file` scope with the Google
Picker, at the cost of picking the folder in Google's own dialog instead of
pasting a link. On the technical side, our idea (not yet in the deck) is to
move scans and exports to a job queue so the service can grow past one
instance (question 7). Our first brief also
proposed Gemini-written captions and a short story per person; that is not
built yet.

- Where: `docs/SUBMISSION.md` section 6, slide 9; `README.md` "About the
  100-user limit"; `HANDOFF.md` 7.1 (captions and story, proposed).

## 14. How is this different from Google Photos face grouping?

We make no claims about how Google Photos works inside; here is what FaceFinder
does. It works on a Google Drive folder that someone else shared, with your own
sign-in, which is how the photographer hands over the album in our graduation
case, and one scan of that folder serves everyone who can open it. It makes one Drive folder per
person, for many people at once, and copies their photos in with Drive's
server-side copy, so one friend can make everyone's folder, ready to share; the
original album never changes. You can find a person from one to three face
photos you upload, or name the groups it found. Gemini adds photographer tools:
Cull into Keep / Review / Rejected with a reason for each photo, Best 10 with
reasons, and Sort by plain Thai or English descriptions.

- Where: `README.md` "How it works"; `app/main.py:1067-1132` (one folder per
  name); `app/google_drive.py:238-245` (server-side copy), `77-79` (a Google
  Photos link is refused with a message asking for a Drive folder).

## 15. Who are the users?

Graduates and their friends. After a graduation, the photographer shares one
Drive folder with thousands of photos. FaceFinder lets each person find their
own photos, or lets one person sort the album into a folder per friend.
Photographers: Cull sorts an album into Keep, Review and Rejected, with a
reason per photo, before they share it. More broadly, anyone who receives one
big shared Drive folder after an event; weddings, sports days and conferences
are next on our list. There is no user study in the repo, so we quote no user
numbers.

- Where: `README.md` intro, `HANDOFF.md` section 3, `docs/SUBMISSION.md`
  sections 1 and 6.
