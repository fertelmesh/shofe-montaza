---
name: shofe-montaza
description: Shofe Video Editor - edits raw talking-head phone clips into finished reels (9:16) or YouTube videos (16:9) - cuts pauses, fillers and bad takes, adds Croatian word-by-word subtitles, punch-in zooms, colour grade, hook title, background music with ducking. Use when the user says "montiraj", "montiraj ga", "napravi reel", "izreži pauze", "dodaj titlove", "analiziraj video", "što je u ovom videu", "pokaži kartu videa", "najjači trenuci", "tko govori", or asks to edit/cut/analyse video clips; also for revisions of a reel made with it ("povećaj titlove", "drugi stil", "makni dio o...").
---

# Shofe montaža

You film, Claude edits. Everything runs locally with Python + ffmpeg; transcription is free and offline (faster-whisper).
Talk to the user in Croatian. Scripts live in `scripts/` next to this file (the skill's base directory, called `<skill>` below).
On Windows use forward slashes and quote every path: `python "<skill>/scripts/render.py" "C:/Users/.../shofe_projekt"`. If `python` is not found, try `py -3`.

## First edit of a video

1. **Check setup** (once per session): `python "<skill>/scripts/doctor.py"`. If anything is `[!!]`, run it with `--popravi`, and if ffmpeg was just installed tell the user to restart Claude. The first line shows the Shofe version (`doctor.py --verzija` prints only that); tell it to the user when they ask which version they have or report a bug. Python packages come from `<skill>/requirements.txt`.
2. **Prepare clips**: `python "<skill>/scripts/prepare.py" <clips or folder> --out shofe_projekt [--format 9:16|16:9|1:1|4:5]`
   - Clips are joined in the given order (a folder → sorted by file name). Ask about the order only if the names don't make it obvious.
   - Default 9:16. Use 16:9 for "YouTube"/"dugi video". Landscape clips get centre-cropped; adjust with `--crop-x 0.3` (0 left … 1 right) after checking a frame.
   - Put the project folder next to the clips unless the user says otherwise.
3. **Transcribe**: `python "<skill>/scripts/transcribe.py" shofe_projekt` (default model large-v3-turbo, language hr). The first run downloads the model (~1.6 GB), so warn the user it will take a few minutes once. For speed on a weak laptop use `--model medium`. Other languages: `--jezik sr|bs|en|auto`.
4. **Speakers** (only when more than one person talks: podcast, interview, conversation, a guest): `python "<skill>/scripts/govornici.py" shofe_projekt` (after transcribe, before analyze/plan) → `govornici.json`. Runs on the CPU, ~7× faster than real time; the first run downloads two small models (~36 MB). If the user knows how many people talk, add `--broj N` (more reliable). Speakers are `G1`, `G2`… in order of first appearance; it prints a transcript by speaker — read it, work out who is who (e.g. the host introduces the guest), confirm with the user if unsure, then name them: `--imena "G1=Marko,G2=Ivan"` (instant, no re-analysis; names survive reruns). If one person was split into two, rerun with `--broj`; if two people were merged, rerun with `--broj` or `--prag 0.4` (lower → more speakers). After this, `plan.py` and `analyze.py` put the speaker on every segment (`"govornik"`), a segment never spans two speakers, and `transcript.txt` shows `Ime: tekst`. Skip it for a solo reel.
5. **Video map** (`analiza.json`): `python "<skill>/scripts/analyze.py" shofe_projekt` (after transcribe; ~8× faster than real time on a weak laptop, `--bez-slike` skips the picture part). It measures speakers' share (`govornici`, if govornici.json exists), silences, loudness (whole video + per segment), speech tempo (syllables/s), scene cuts, blurry/dark/overexposed shots and clip joins, and writes `analiza.txt`, a short readable summary. Segment numbers match `edit.json` (same `--pauza` as plan.py, default 0.3). Always run it for videos longer than ~3 min, podcasts and clip hunting; for a short reel it is optional but read its `Loši kadrovi` line.
   - Then **you** add the meaning, in `analiza.json` (rerunning analyze.py keeps these):
     - `teme`: `[{"od": s, "do": s, "naslov": "3–6 words", "sazetak": "one sentence"}]` — consecutive topics covering the talk, in source seconds (take them from the word times in `transcript.json` / segment times).
     - `trenuci`: `[{"od": s, "do": s, "vrsta": "hook|poanta|smijeh|emocija|savjet|citat|akcija|ostalo", "ocjena": 1-5, "opis": "why it is strong"}]` — the strongest moments: a promise/question that makes people stay (hook), the payoff, laughs, emotional or quotable lines, concrete tips. 5 = would open a reel with it. Quality over quantity (for 1 min ~2–4, for 60 min ~20–40).
   - Check with `python "<skill>/scripts/analyze.py" shofe_projekt --provjeri` (refreshes `analiza.txt`; on mistakes exits 1 and lists them — fix and rerun).
   - **Visual overview for the user**: analyze.py (and `--provjeri`) also writes `pregled.html` in the project folder — one offline page with the video, a zoomable timeline (loudness + silences, speakers, topics, moments, bad shots, cuts), the moments list, topics, speaker shares, warnings and a searchable transcript; clicking anything jumps the video there. After you add `teme`/`trenuci` and run `--provjeri`, tell the user they can open it (double-click `pregled.html`, or `python "<skill>/scripts/pregled.py" shofe_projekt --otvori` to rebuild and open it in the browser). When the user says "pokaži kartu", "otvori pregled" or "pokaži mi analizu", run that command.
   - Use the map: cut or avoid `losi_kadrovi` (blurry/dark parts), consider `tiho` segments (mic problem?) and `brzo` tempo when choosing `brzina`, and pick `hook`/`naglasi` from the best `trenuci`. When the user asks what is in the video, answer from `analiza.txt`.
6. **Plan**: `python "<skill>/scripts/plan.py" shofe_projekt --stil <style>`. It writes `edit.json` and `transcript.txt` and auto-marks retakes and filler-only segments with `"zadrzi": false`.
7. **Edit `edit.json` yourself** (this is the creative part, do it carefully):
   - Read `transcript.txt`. Verify every auto mark (`X`, `<- ponovljeno…`). For retakes keep the **last complete** take. Also drop false starts, off-topic rambling, "je l' snima?", and anything the user asked to remove.
   - Fix misheard words in `tekst` (names, brands, diacritics č ć š ž đ). Words marked `[nesigurno: …]` are the likely errors. Changing `tekst` only changes the subtitles; timing is kept.
   - Add filler words to cut inside a kept segment via `"izbaci": ["eee", "ovaj"]` (only when "ovaj"/"ono" really are fillers in that segment).
   - To trim the start/end of a segment, change its `od`/`do` (seconds, source timeline).
   - `hook`: 3–7 word title for the first seconds, taken from the strongest promise/question in the video, in natural Croatian. Leave empty if the video already opens strongly and the user wants no title.
   - `naglasi`: 2–6 key words (nouns, numbers, the payoff) to colour in the accent colour.
   - Pick `stil` if the user didn't: energetic/selling → `suncani`; podcast clips → `podcast`; viral hook, short punchy → `udarno`; calm advice, explainers, YouTube → `cisto`; story/atmosphere/festival → `kino`.
8. **Look before rendering**: `python "<skill>/scripts/render.py" shofe_projekt --kadar 1,5,12` (seconds of the final video) → `kadrovi.png`. Open the image and check: face not cut off, subtitles not covering the face or the mouth, hook readable, text fits. Fix (crop, `pozicija_titlova`, `velicina_titlova`) and repeat if needed.
9. **Render**: `python "<skill>/scripts/render.py" shofe_projekt` → `reel_vN.mp4` (new version each time; the edit used is saved in `verzije/`). `--brzo` gives a fast half-resolution preview; `--kvaliteta visoka` for the final YouTube upload.
10. **Report** in 3–4 lines: file path, length before → after, what was cut (segment numbers + a few words each), style. Offer the most useful next tweak, not a list.

## Revisions (no re-transcribing)

Change `edit.json`, then run `render.py` again. Only rerun `prepare.py` + `transcribe.py` (+ `govornici.py`, `analyze.py`) if clips were added/replaced; rerun `prepare.py` alone (same clips) to change cropping — the transcript stays valid.

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
- `govornici.py` cannot download models (no internet / firewall) → it needs internet once; models live in `%LOCALAPPDATA%/Shofe/modeli` (or `SHOFE_MODELI`). Wrong speaker on a short reply ("Da.", "Točno.") is expected: under ~1 s there is too little voice; fix that segment's `govornik` by hand if it matters.
- Never delete the user's original clips; all work happens in the project folder.
