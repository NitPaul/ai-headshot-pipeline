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
- [Generation modes](#generation-modes)
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

### Step 3 — Check it works

Put one employee photo in `01_inbox`, then double-click **`run.bat`**.

Nothing else to configure. Out of the box the tool runs in **manual mode**,
which uses the Gemini subscription you already have rather than a paid API.
See [Generation modes](#generation-modes) below.

---

## Daily use

### Adding a new employee

1. Put their photo in the **`01_inbox`** folder
2. Name the file with their name: `tanvir-ahmed.jpg`
3. Double-click **`run.bat`** — it prepares the photo and tells you what to do
4. Open **`manual\START_HERE.html`** and follow the steps on that page:
   copy the instruction, paste it into Gemini with the prepared picture,
   and save what Gemini returns into `manual\2_put_results_here`
5. Double-click **`run.bat`** again — it finishes everything
6. Open **`03_review\_contact_sheet.html`** and look at the result
7. Their finished photo is in **`05_final`** — send that to the web team

You always run the tool twice: once before generating, once after. It keeps
track of who is at which stage, so you can generate five people today and the
rest next week.

The file name becomes the website file name, so name it properly.
`tanvir-ahmed.jpg` produces `tanvir-ahmed.png`. Avoid names like
`IMG_20260811.jpg` or `photo(1).jpg`.

You can leave every photo in `01_inbox` forever. Running the tool again only
processes faces it has not seen, so it costs nothing extra.

### Replacing someone's photo

Put the new photo in `01_inbox` with **exactly the same file name** as before
and run again. The tool notices the photo changed and redoes just that person.

### Doing the first big batch

For your first 30–100 employees, start with one person only:

```
run.bat --limit 1
```

Generate that one, run again, and look at the result carefully before doing the
rest. Once you are happy, drop everyone into `01_inbox` and run normally.

You do not have to finish in one sitting. Generate as many as you like, run the
tool, and repeat another day — it always picks up exactly where you stopped.

---

## The folders

| Folder | What it is |
|---|---|
| **`01_inbox`** | **You put photos here.** That is the only folder you add to. |
| **`03_review`** | Before/after pictures and the contact sheet. **Check this.** |
| **`04_needs_attention`** | Photos the tool was not confident about. |
| **`05_final`** | **Finished photos for the website.** |
| **`manual`** | **Where you generate photos.** Open `START_HERE.html` inside it. |
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

The tool combines every suit colour with every shirt and tie in `config.yaml`
and discards pairings that clash — it will never put a navy tie on a navy suit.
That gives **132 professional combinations** out of the box.

Each person is given one based on their name. If a colleague already has that
outfit, they get the next free one, so people look different from each other.

Once someone has been given an outfit it is recorded and **never changes** —
not when you re-run the tool, not when new staff are added, and not even if
they send a new photo. Women get a suit and tie too, as the company standard.

To force an exact outfit for someone, add them under `overrides`:

```yaml
attire:
  overrides:
    tanvir-ahmed: { suit: "navy blue", shirt: "crisp white", tie: "deep red" }
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

## Generation modes

The tool can create the suits in three ways. Change it with `provider.name`
in `config.yaml`.

### `manual` — the default, and what WeGro uses

You generate each photo in the Gemini app, using the subscription the company
already pays for. The tool does everything else.

- **Free.** No API key, no billing, no card.
- **Best quality** — it is the full Gemini image model, not a cut-down one.
- Costs your time: roughly 1–2 minutes per person.

Run `run.bat`, open `manual\START_HERE.html`, work down the list, then run
`run.bat` again. For a first batch of 30–100 staff, allow two or three hours,
split over as many days as you like. After that each new hire is one photo.

> **Important:** Google's free API tier does **not** include image generation
> at all. Any guide claiming otherwise is out of date. That is why this mode
> exists — it is the only way to use a Gemini subscription legitimately from a
> tool like this.

### `gemini` — fully automatic, paid

Hands-off batch processing through the Gemini API. This needs **billing enabled**
on the Google Cloud project behind your API key. It costs roughly 4 US cents per
photo, so about **$4 for 100 employees**, then a few cents per new hire.

To use it: put a key in the `.env` file (copy `.env.example` if it is missing),
and set `provider.name: gemini` in `config.yaml`.

### `stub` — no AI at all

Runs every step except the generation. Use it to check framing, background,
file names and the whole process without generating anything:

```
run.bat --provider stub
```

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
| `attire.suits` / `attire.ties` | The suit and tie colours to choose from |
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
run.bat --provider stub          test the whole process using no AI at all
run.bat --rebuild-review         rebuild the contact sheet only
run.bat --verbose                show extra detail when something goes wrong
```

`--provider stub` is genuinely useful: it runs every step except the generation,
so you can check framing, background and file names without generating anything.

**A note on `--force-all`:** in manual mode this re-queues everybody for
generation by hand, so only use it if you really do want to redo the whole
company. `--force <name>` for one person is usually what you want.

---

## Troubleshooting

**"Python is not installed"**
Python is missing, or it was installed without ticking *Add Python to PATH*.
Reinstall it and tick that box.

**"Your Google plan does not include image generation"**
You are in `gemini` mode without billing enabled. Google's free API tier does
not include image generation. Either switch back to `provider.name: manual` in
`config.yaml`, or enable billing. See [Generation modes](#generation-modes).

**"No Google API key found"**
Only `gemini` mode needs a key. If you meant to use the free route, set
`provider.name: manual` in `config.yaml`.

**Nothing happens except "waiting for you"**
That is manual mode working correctly. Open `manual\START_HERE.html`, generate
the photos listed there, save them into `manual_put_results_here`, then run
the tool again.

**A result was ignored**
The file name must match exactly. `alvi-rahman.png` works; `alvi-rahman (1).png`
or `Alvi-Rahman.png` will not be picked up.

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
The first run loads several models and is slow to start. After that the tool
itself takes only a few seconds per person; the time goes on generating.

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
   │                  ↓ the ONLY step that is not deterministic
   ├─ 4  GENERATE   ── manual / gemini / stub ──► suit + tie on plain grey
   │                  in manual mode the run pauses here and resumes
   │                  on the next run, once the result has been saved
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
| Queued for manual generation | Recorded as `awaiting_generation`, retried next run |

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
