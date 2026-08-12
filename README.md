# WeGro Employee Photo Tool

Turns any employee photo — a phone snap, a WhatsApp forward, an old ID photo —
into a standard WeGro website headshot: formal suit and tie, the official WeGro
background, and every person's head at exactly the same size and position.

Drop a photo in a folder, double-click one file, done.

```
  01_inbox/tanvir-ahmed.jpg        ──►      05_final/tanvir-ahmed.png
  (whatever photo they sent)                (1445 x 1089, ready for the site)
```

**Everyone already done is skipped automatically**, so adding a new hire later
costs one photo and a few seconds.

---

## Contents

- [Installing on a new computer](#installing-on-a-new-computer)
- [Daily use](#daily-use)
- [The folders](#the-folders)
- [How it keeps faces accurate](#how-it-keeps-faces-accurate)
- [Suit and tie colours](#suit-and-tie-colours)
- [When a photo needs attention](#when-a-photo-needs-attention)
- [Free usage limits](#free-usage-limits)
- [Changing how photos look](#changing-how-photos-look)
- [All commands](#all-commands)
- [Troubleshooting](#troubleshooting)
- [How it works inside](#how-it-works-inside)
- [Privacy and consent](#privacy-and-consent)

---

## Installing on a new computer

### Step 1 — Get the tool

Download the ZIP from GitHub (green **Code** button → **Download ZIP**), then
right-click it → **Extract All**.

Put the extracted folder somewhere sensible and permanent, such as
`C:\WeGro Photo Tool`. Avoid OneDrive or Desktop folders that sync, because the
tool writes a lot of temporary files.

### Step 2 — Run setup

Double-click **`setup.bat`**. That is the whole installation.

It takes about 10 minutes and needs an internet connection. It will:

- check whether the computer has Python and **install it automatically if not**
  (the official installer from python.org, for the current user only, so it
  never asks for an administrator password)
- build a private environment for the tool
- download about 220 MB of face-detection models

You only ever do this once per computer. Nothing needs to be installed by hand.

### Step 3 — Add the free Google key

1. Go to <https://aistudio.google.com/apikey>
2. Sign in with a Google account and click **Create API key** — it is free
3. Copy the key
4. In the tool folder, open the file called **`.env`** with Notepad
5. Paste the key after `GEMINI_API_KEY=` so the line looks like:

   ```
   GEMINI_API_KEY=AIzaSy...your-actual-key...
   ```

6. Save and close

**Never share this file or put it on GitHub.** It is your personal key.

### Step 4 — Check it works

Put one employee photo in `01_inbox`, then double-click **`run.bat`**.

---

## Daily use

### Adding a new employee

1. Put their photo in the **`01_inbox`** folder
2. Name the file with their name: `tanvir-ahmed.jpg`
3. Double-click **`run.bat`**
4. Open **`03_review\_contact_sheet.html`** and look at the result
5. Their finished photo is in **`05_final`** — send that to the web team

The file name becomes the website file name, so name it properly.
`tanvir-ahmed.jpg` produces `tanvir-ahmed.png`. Avoid names like
`IMG_20260811.jpg` or `photo(1).jpg`.

You can leave every photo in `01_inbox` forever. Running the tool again only
processes faces it has not seen, so it costs nothing extra.

### Replacing someone's photo

Put the new photo in `01_inbox` with **exactly the same file name** as before
and run again. The tool notices the photo changed and redoes just that person.

### Doing the first big batch

For your first 30–100 employees:

```
run.bat --limit 1
```

Check that one result carefully first. If you are happy, run `run.bat` normally
to do the rest. See [Free usage limits](#free-usage-limits) — a large first
batch usually takes a few days.

---

## The folders

| Folder | What it is |
|---|---|
| **`01_inbox`** | **You put photos here.** That is the only folder you add to. |
| **`03_review`** | Before/after pictures and the contact sheet. **Check this.** |
| **`04_needs_attention`** | Photos the tool was not confident about. |
| **`05_final`** | **Finished photos for the website.** |
| `02_working` | Step-by-step images, for troubleshooting. Safe to delete. |
| `logs` | What happened on each run. Safe to delete. |
| `assets` | The WeGro background plate. Do not delete. |

---

## How it keeps faces accurate

This is the part that matters most, so it is worth understanding.

AI image tools are good at creating clothes, but they quietly change people's
faces. The result often looks like *someone similar* rather than the actual
person — which is unacceptable for a staff page.

So the tool does not trust the AI with the face:

1. The AI generates the suit and the studio lighting.
2. The tool then takes **the real pixels of the person's face from their
   original photo** and places them back on top, adjusted to match the new
   lighting so it does not look pasted on.
3. The finished face is then **scored against the original photo** using face
   recognition — the same kind of comparison a phone's face unlock makes.
4. Anything scoring below the threshold goes to `04_needs_attention` instead of
   `05_final`.

**Nothing reaches `05_final` without passing that check.** The score for each
person is shown on the contact sheet.

The tool also puts every face in an identical position: eyes level, same head
size, eyes on the same line. That framing was measured from the photo already
on the WeGro website, so new photos line up beside the existing ones.

---

## Suit and tie colours

Each person is automatically given one of ten professional suit-and-tie
combinations, chosen from their name. The same person always gets the same
outfit, even if you run the tool again, and adding a new employee never changes
anyone else's. Women get a suit and tie too, as the company standard.

To force a particular outfit, open `config.yaml` and add them under `overrides`
with the number of the combination you want from the list above it:

```yaml
attire:
  overrides:
    tanvir-ahmed: 3
    sadia-rahman: 7
```

---

## When a photo needs attention

The file name in `04_needs_attention` tells you why. The usual causes:

| Problem | What to do |
|---|---|
| Face did not match well enough | Use a clearer, front-facing photo |
| No face found | Too dark, too small, or the head is turned side-on |
| More than one face | Crop so only the employee is in the picture |
| Marked `LOW_QUALITY` | The original is small — ask for a bigger photo |
| Eyes not lined up | Usually fixes itself with a straighter photo |

Fix the source photo, put it in `01_inbox` with the same name, run again.

### What makes a good source photo

- Face looking towards the camera, both eyes visible
- Reasonably bright, even light on the face
- At least 800 pixels across, ideally more
- Only the employee in the picture
- Any clothing is fine — the tool replaces it

---

## Free usage limits

The AI is free, but Google limits how many images you can make per day, and
they change that limit from time to time. Check yours at
<https://aistudio.google.com/rate-limit>.

If you hit the limit, the tool **stops politely** and tells you how many people
are left:

```
  The free daily image quota is used up. Run this again tomorrow -
  everyone already finished will be skipped automatically.
  47 person(s) still waiting.
```

Just run it again the next day. It carries on exactly where it stopped. Nothing
is lost, nothing is repeated, and no quota is wasted redoing finished people.

For a first batch of 30–100 employees, expect a few days. After that, new
employees are one at a time and finish in seconds.

---

## Changing how photos look

Open **`config.yaml`** with Notepad. Every setting is explained in the file.
The most useful ones:

| Setting | What it does |
|---|---|
| `framing.face_width_ratio` | Bigger number = more zoomed in on the face |
| `framing.eye_line` | Where the eyes sit, top to bottom |
| `plate.background_softness` | Blurs the background if the leaf is distracting |
| `plate.shadow` | The soft shadow behind each person |
| `qa.min_face_similarity` | Stricter face checking (higher = fussier) |
| `attire.combinations` | The list of suit and tie colours |
| `output.width` / `height` | Final image size |

After changing something, test on one person first:

```
run.bat --force tanvir-ahmed
```

To redo everybody with a new look, use `run.bat --force-all` — but be aware
this uses your daily quota all over again.

---

## All commands

Hold **Shift**, right-click in the tool folder, choose **Open PowerShell window
here**, then use any of these:

```
run.bat                          normal run - process anyone new
run.bat --status                 list everyone and their current state
run.bat --dry-run                show what would happen, change nothing
run.bat --limit 3                only do the next 3 people
run.bat --only tanvir-ahmed      process just this person
run.bat --force tanvir-ahmed     redo this person even though they are done
run.bat --force-all              redo everybody from scratch
run.bat --provider stub          test the whole process using NO AI quota
run.bat --rebuild-review         rebuild the contact sheet only
run.bat --verbose                show extra detail when something goes wrong
```

`--provider stub` is genuinely useful: it runs every step except the AI, so you
can check framing, background and file names without spending any quota.

---

## Troubleshooting

**"Python is not installed"**
Python is missing, or it was installed without ticking *Add Python to PATH*.
Reinstall it and tick that box.

**"No Google API key found"**
The `.env` file has no key in it. See [Step 3](#step-3--add-the-free-google-key).

**"The API key was rejected by Google"**
The key was copied incorrectly, or it has been deleted in AI Studio. Create a
new one and paste it again.

**"No face detection model could be loaded"**
The setup downloads did not finish. Run `setup.bat` again.

**Everything goes to `04_needs_attention`**
The face check may be too strict for your photos. Lower
`qa.min_face_similarity` in `config.yaml` a little — try `0.40` — and look
carefully at the results before trusting it.

**A photo looks wrong but passed the check**
Delete that person's files from `05_final`, put a better photo in `01_inbox`
with the same name, and run again. The automatic check catches obvious
problems, not taste.

**It is very slow**
The first run loads several models and is slow to start. After that, expect
roughly 15–30 seconds per person, mostly waiting on Google.

---

## How it works inside

For whoever maintains this later.

```
01_inbox/tanvir-ahmed.jpg
   │
   ├─ 1  INGEST     name -> id, SHA-256 fingerprint, skip if unchanged
   ├─ 2  NORMALIZE  EXIF rotate, neutralise colour cast, upscale if small
   ├─ 3  ALIGN      level the eyes, fixed head size, fixed eye line
   │
   ├─ 4  GENERATE   ── Gemini ──► suit + tie on plain grey   (1 API call)
   │
   ├─ 5  FACE LOCK  paste the REAL face back, lighting-matched
   ├─ 6  RE-ALIGN   re-impose exact framing, because models drift
   ├─ 7  CUT OUT    remove the plain backdrop, remove edge halo
   ├─ 8  COMPOSITE  place on the cached WeGro plate
   ├─ 9  CHECK      face recognition score vs the original
   └─ 10 EXPORT     05_final + review images + contact sheet
```

The guiding idea: **the AI does only what only the AI can do — invent
clothing. Everything that must be exact is done by ordinary code.** That is why
the backgrounds are pixel-identical and the heads all line up.

`manifest.json` is the ledger. Each person is keyed by a slug of their file
name, with a SHA-256 of their source photo:

| Situation | Behaviour |
|---|---|
| New name | Process |
| Same name, same photo | Skip, no API call |
| Same name, different photo | Redo as a new version, archive the old |
| File removed from inbox | Leave `05_final` alone |

Models used, all free: MediaPipe FaceLandmarker (framing and face mask),
OpenCV YuNet (backup detector), OpenCV SFace (identity check), U2-Net
(background removal), Google Gemini image models (clothing).

Generation sits behind `providers/base.py`, so a local GPU back-end can be
added later without touching the rest of the pipeline.

---

## Privacy and consent

These are AI-edited photographs of real colleagues.

- **Show each person their own photo before it goes on the website.**
- Source photos are sent to Google's API for editing. Confirm that is
  acceptable to HR before processing the whole company.
- Employee photos are deliberately excluded from this repository. Keep them on
  the company machine.
- The automatic face check catches obvious failures. The design team is the
  final judge of whether someone looks like themselves.
