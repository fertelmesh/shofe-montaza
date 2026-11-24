---
name: shofe-montaza
description: Shofe Video Editor - edits raw talking-head phone clips into finished reels (9:16) or YouTube videos (16:9) - cuts pauses, fillers and bad takes, adds Croatian word-by-word subtitles, punch-in zooms, colour grade, hook title, background music with ducking. Use when the user says "montiraj", "montiraj ga", "napravi reel", "izreži pauze", "dodaj titlove", or asks to edit/cut video clips; also for revisions of a reel made with it ("povećaj titlove", "drugi stil", "makni dio o...").
---

# Shofe montaža

You film, Claude edits. Everything runs locally with Python + ffmpeg; transcription is free and offline (faster-whisper).
Talk to the user in Croatian. Scripts live in `scripts/` next to this file (the skill's base directory, called `<skill>` below).
On Windows use forward slashes and quote every path: `python "<skill>/scripts/render.py" "C:/Users/.../shofe_projekt"`. If `python` is not found, try `py -3`.

## First edit of a video

1. **Check setup** (once per session): `python "<skill>/scripts/doctor.py"`. If anything is `[!!]`, run it with `--popravi`, and if ffmpeg was just installed tell the user to restart Claude.
2. **Prepare clips**: `python "<skill>/scripts/prepare.py" <clips or folder> --out shofe_projekt [--format 9:16|16:9|1:1|4:5]`
   - Clips are joined in the given order (a folder → sorted by file name). Ask about the order only if the names don't make it obvious.
   - Default 9:16. Use 16:9 for "YouTube"/"dugi video". Landscape clips get centre-cropped; adjust with `--crop-x 0.3` (0 left … 1 right) after checking a frame.
   - Put the project folder next to the clips unless the user says otherwise.
3. **Transcribe**: `python "<skill>/scripts/transcribe.py" shofe_projekt` (default model large-v3-turbo, language hr). The first run downloads the model (~1.6 GB), so warn the user it will take a few minutes once. For speed on a weak laptop use `--model medium`. Other languages: `--jezik sr|bs|en|auto`.
4. **Plan**: `python "<skill>/scripts/plan.py" shofe_projekt --stil <style>`. It writes `edit.json` and `transcript.txt` and auto-marks retakes and filler-only segments with `"zadrzi": false`.
5. **Edit `edit.json` yourself** (this is the creative part, do it carefully):
   - Read `transcript.txt`. Verify every auto mark (`X`, `<- ponovljeno…`). For retakes keep the **last complete** take. Also drop false starts, off-topic rambling, "je l' snima?", and anything the user asked to remove.
   - Fix misheard words in `tekst` (names, brands, diacritics č ć š ž đ). Words marked `[nesigurno: …]` are the likely errors. Changing `tekst` only changes the subtitles; timing is kept.
   - Add filler words to cut inside a kept segment via `"izbaci": ["eee", "ovaj"]` (only when "ovaj"/"ono" really are fillers in that segment).
   - To trim the start/end of a segment, change its `od`/`do` (seconds, source timeline).
   - `hook`: 3–7 word title for the first seconds, taken from the strongest promise/question in the video, in natural Croatian. Leave empty if the video already opens strongly and the user wants no title.
   - `naglasi`: 2–6 key words (nouns, numbers, the payoff) to colour in the accent colour.
   - Pick `stil` if the user didn't: energetic/selling → `suncani`; podcast clips → `podcast`; viral hook, short punchy → `udarno`; calm advice, explainers, YouTube → `cisto`; story/atmosphere/festival → `kino`.
6. **Look before rendering**: `python "<skill>/scripts/render.py" shofe_projekt --kadar 1,5,12` (seconds of the final video) → `kadrovi.png`. Open the image and check: face not cut off, subtitles not covering the face or the mouth, hook readable, text fits. Fix (crop, `pozicija_titlova`, `velicina_titlova`) and repeat if needed.
7. **Render**: `python "<skill>/scripts/render.py" shofe_projekt` → `reel_vN.mp4` (new version each time; the edit used is saved in `verzije/`). `--brzo` gives a fast half-resolution preview; `--kvaliteta visoka` for the final YouTube upload.
8. **Report** in 3–4 lines: file path, length before → after, what was cut (segment numbers + a few words each), style. Offer the most useful next tweak, not a list.

## Revisions (no re-transcribing)

Change `edit.json`, then run `render.py` again. Only rerun `prepare.py` + `transcribe.py` if clips were added/replaced; rerun `prepare.py` alone (same clips) to change cropping — the transcript stays valid.

| User says | Change in edit.json |
|---|---|
| veći / manji titlovi | `velicina_titlova`: 1.2 / 0.85 (relative) |
| titlovi gore / u sredini / dolje | `pozicija_titlova`: "gore" / "sredina" / "dolje" |
| bez titlova | `titlovi`: false |
| velika / mala slova | `velika_slova`: true / false |
| druga boja, npr. plava | `boja`: "#2F8BFF" (accent: highlight, keywords, hook box) |
| drugi stil | `stil`: suncani / podcast / udarno / cisto / kino |
| više / manje / bez zumova | `zoom`: "jako" / "blago" / "nema" |
| toplije, hladnije, živje, filmski, crno-bijelo | `boja_slike`: toplo / hladno / zivo / kino / crnobijelo / neutralno |
| brže / sporije | `brzina`: 1.1 (max ~1.25 for speech) / 1.0 |
| dodaj glazbu | `glazba`: path to an mp3/wav the user owns or has rights to |
| glazba tiša / glasnija | `glazba_glasnoca`: -24 / -16 (dB, default -20) |
| makni dio o X | find the segment(s) in `odsjecci`, set `"zadrzi": false` |
| vrati dio o X | set `"zadrzi": true` |
| promijeni naslov | `hook`; `hook_trajanje` for how long it shows |
| traka napretka | `traka_napretka`: true |
| kraće pauze / više zraka | pick a style with tighter/looser cuts, or edit `rezanje` in that style's JSON |

Null fields mean "use the style default". Keep `odsjecci` IDs unchanged.

## Styles

Defined in `<skill>/styles/*.json` (Croatian keys). To make a new look the user likes, copy the closest style file to a new name and change `font` (Montserrat Black / Montserrat ExtraBold / Montserrat SemiBold / Anton, all bundled in `fonts/`), sizes, colours (`#RRGGBB`, background `#RRGGBBAA`), `nacin` (karaoke = active word lit; rijec = one big word; linija = whole line), `max_rijeci`, `otkrivanje` (words appear as spoken), `pop`, `zoom`, `boja_slike`, `rezanje` ([seconds before, seconds after] each kept phrase), hook colours, `traka_napretka`.

## Vocabulary

`<skill>/rjecnik.txt` lists names and terms whisper should spell correctly. When you fix the same misheard name twice, add it there (one per line) and tell the user.

## Troubleshooting

- `ffmpeg nije pronađen` right after installing → restart Claude so PATH updates, or run doctor again (it also searches the winget folder).
- Transcription very slow → `--model medium` or `small`; an NVIDIA GPU is used automatically if CUDA libraries are present.
- Empty transcript → the clip has no speech or the wrong language; try `--jezik auto`.
- Subtitles in a wrong font → make sure `shofe_projekt/fonts` exists (render.py copies it) and the style's `font` name matches one of the four bundled fonts exactly.
- Never delete the user's original clips; all work happens in the project folder.
