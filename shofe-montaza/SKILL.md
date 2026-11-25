---
name: shofe-montaza
description: Shofe Video Editor - edits raw talking-head phone clips into finished reels (9:16) or YouTube videos (16:9) - cuts pauses, fillers and bad takes, adds Croatian word-by-word subtitles, punch-in zooms, colour grade, hook title, background music with ducking. Use when the user says "montiraj", "montiraj ga", "napravi reel", "izreži pauze", "dodaj titlove", "analiziraj video", "što je u ovom videu", "pokaži kartu videa", "najjači trenuci", "tko govori", or asks to edit/cut/analyse video clips; also for revisions of a reel made with it ("povećaj titlove", "drugi stil", "makni dio o..."), time-based commands on a rendered video ("makni od 1:20 do 1:45", "izreži 0:05-0:08", "zadrži samo 0:10-0:40", "što je na 1:20", "vrati kako je bilo"), subtitle files ("SRT za YouTube", "titlovi kao datoteka", "VTT"), translated subtitles ("engleski titlovi", "prevedi titlove", "titlovi na engleskom", "English subtitles"), vocabulary ("zapamti ime", "uvijek piši X", "pokaži rječnik", "što je Shofe naučio"), DaVinci Resolve export ("otvori u DaVinciju", "izvezi za DaVinci", "timeline za Resolve", "FCPXML", "XML za montažu"), versions ("pokaži verzije", "vrati verziju 2", "što se promijenilo", "usporedi verziju 1 i 3") and content-based commands ("izreži dio gdje pričam o cijeni", "zadrži drugi pokušaj", "zadrži samo savjet o X", "vrati dio o X", "gdje spominjem X").
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
   - Fix misheard words in `tekst` (names, brands, diacritics č ć š ž đ). Words marked `[nesigurno: …]` are the likely errors. Changing `tekst` only changes the subtitles; timing is kept. Segments marked `[rječnik: …]` were already corrected from the learned vocabulary — check them too. Your corrections are learned on render (see "Vocabulary"), so fix names consistently, word for word.
   - Add filler words to cut inside a kept segment via `"izbaci": ["eee", "ovaj"]` (only when "ovaj"/"ono" really are fillers in that segment).
   - To trim the start/end of a segment, change its `od`/`do` (seconds, source timeline).
   - `hook`: 3–7 word title for the first seconds, taken from the strongest promise/question in the video, in natural Croatian. Leave empty if the video already opens strongly and the user wants no title.
   - `naglasi`: 2–6 key words (nouns, numbers, the payoff) to colour in the accent colour.
   - Pick `stil` if the user didn't: energetic/selling → `suncani`; podcast clips → `podcast`; viral hook, short punchy → `udarno`; calm advice, explainers, YouTube → `cisto`; story/atmosphere/festival → `kino`.
8. **Look before rendering**: `python "<skill>/scripts/render.py" shofe_projekt --kadar 1,5,12` (seconds of the final video) → `kadrovi.png`. Open the image and check: face not cut off, subtitles not covering the face or the mouth, hook readable, text fits. Fix (crop, `pozicija_titlova`, `velicina_titlova`) and repeat if needed.
9. **Render**: `python "<skill>/scripts/render.py" shofe_projekt` → `reel_vN.mp4` (new version each time; the edit used is saved in `verzije/`, see "Versions"). `--brzo` gives a fast half-resolution preview; `--kvaliteta visoka` for the final YouTube upload.
10. **Report** in 3–4 lines: file path, length before → after, what was cut (segment numbers + a few words each), style. Offer the most useful next tweak, not a list.

## Commands by time in the finished video (`uredi.py`)

When the user names times they saw in the rendered video ("makni od 1:20 do 1:45", "izreži 0:05–0:08 i 1:10–1:12", "zadrži samo 0:10–0:40"), do NOT convert them to segments yourself — the finished video is cut, sped up and shifted, so its times differ from `transcript.txt`. Use:

- `python "<skill>/scripts/uredi.py" shofe_projekt makni 1:20-1:45 [more ranges]` — removes that part of the finished video.
- `python "<skill>/scripts/uredi.py" shofe_projekt zadrzi 0:10-0:40` — keeps only that part (everything else goes out).
- Times are read from the **version the user is watching**: the last render, or the version restored with `verzije.py vrati N` (`reel_vN`), so several commands in a row without a new render all use the same video. `--verzija N` if the user means an older reel; `--trenutno` to use the current edit.json (e.g. after `popis`). Formats: `1:20`, `1:20.5`, `0:01:20`, `80`, `od 1:20 do 1:45`.
- Cuts snap to whole words (a word goes out if its middle is inside the range) and are written to `edit.json` → `izrezi` (source seconds, with the command and the removed text). It prints the removed words and the new length: read them and tell the user in one line what was removed („…prve riječi … zadnje…“). If the cut leaves a broken sentence (it prints notes when a time falls inside a word), suggest extending it to the sentence end.
- Add `--proba` to preview without changing anything (use it when the user's range looks odd, e.g. very long).
- `python "<skill>/scripts/uredi.py" shofe_projekt popis` — finished-video timeline: each kept segment with its times and text, plus the time cuts. Use it to answer "što je na 1:20?" or to check a range before cutting.
- `python "<skill>/scripts/uredi.py" shofe_projekt vrati` — undo the last uredi.py command (repeat to go further back; history is in `povijest/`). For a whole render version use `verzije.py vrati N` (see "Versions"); never copy files in `verzije/` by hand.
- Then render (`render.py`, or `--kadar` first if the cut is near the hook). `plan.py --prepisi` starts from scratch and drops `izrezi`.

## Commands by content (`uredi.py` with quotes)

When the user describes WHAT to cut or keep ("izreži dio gdje pričam o cijeni", "makni rečenicu o suboti", "zadrži drugi pokušaj", "zadrži samo savjet o filteru", "vrati dio o održavanju"), **you** find the part in `transcript.txt` (and `analiza.json` topics), then let the tool cut by exact words — never edit `odsjecci`/`izrezi` by hand for this:

- `python "<skill>/scripts/uredi.py" shofe_projekt makni --od "Prvo, koliko košta" --do "tristo eura."` — from the first quote to the end of the second (quotes copied verbatim from transcript.txt, 2–5 words each; the end is searched after the start). Without `--do` the quote itself is the selection.
- `--cijele-recenice` extends the selection to whole sentences. Use it whenever the user talks about a sentence/part/topic, not specific words.
- `--tema "održavanje"` or `--tema 4` — a whole topic from `analiza.json` `teme`. `--odsjecak 5-7,9` — segment numbers from transcript.txt. `--rijeci 40-62` — word numbers from `trazi`. Several selectors add up.
- Commands: `makni` (out of the video), `zadrzi` (only this stays; it also brings back words that were cut), `dodaj` (put back a cut part: a dropped retake, a removed topic — the segment is switched on and earlier cuts over it shrink).
- "zadrži drugi pokušaj" = two commands: `dodaj --od "<start of take 2>" --cijele-recenice`, then `makni` the take that was kept (check transcript.txt: `X` segments are dropped takes).
- `python "<skill>/scripts/uredi.py" shofe_projekt trazi "cijena"` — where a word/phrase is said: word number, source time, time in the last rendered video, segment, context, and whether it is currently cut. Use it when unsure.
- Matching ignores case, punctuation and diacritics and accepts other forms of a word (cijena/cijenu) and small ASR errors; your corrected `tekst` in edit.json is searchable too. A quote that is not in the transcript is an error with the closest matches — never guess, re-read transcript.txt. If a quote occurs more than once it lists all with times: add words or `--pojava N` (ask the user only if the request itself is ambiguous).
- Read the output: it prints the selected text, every part that goes out / comes back with its time in the finished video, notes when a selection starts or ends mid-sentence, and the new length. Tell the user in one or two lines what went out or came back. `--proba` first when the selection is large (a whole topic) or you are unsure. `vrati` undoes it like any uredi.py command.

## Shorten to N seconds (`uredi.py skrati`)

"Skrati na 60 sekundi", "neka bude ispod minute", "skrati za 15 s", "treba mi verzija od 30 s": the tool drops the least important **whole thoughts** (never half a sentence) until the finished video fits, and measures the real finished length (style cut margins, `brzina`) so the result is ≤ N.

1. `python "<skill>/scripts/uredi.py" shofe_projekt skrati 60 --proba` — prints every thought (misao) in the current video: number, time in the current video, length, importance 1–5 with the reason, `X` = would go out, `^` = cannot stay without the previous one. Thoughts already respect sentence ends, question + answer, "Drugo, ugradnja." + what it announces, and sentences starting with "A/Ali/Zato/To/Još…" (kept only together with the one before). Automatic importance uses `analiza.json` `trenuci` (ocjena), how central a thought is to the whole video, and a bonus for the opening and the closing line — it does not understand the content.
2. **You rate the thoughts** — always, unless the video has only a few thoughts and the automatic result is clearly right. Read the list and give every thought 1–5 for THIS video: 5 = hook / main point / the thing the user asked to keep, 4 = strong support, call to action, 3 = useful, 2 = filler-ish, 1 = repetition, aside, tangent. Respect what the user said ("glavno je cijena" → cijena 5). Then run for real:
   `python "<skill>/scripts/uredi.py" shofe_projekt skrati 60 --ocjene "1:5,2:2,3-5:4,6:1,…"`
   - `--obavezno "verbatim quote"` (repeatable) — must stay no matter what (e.g. the user said "ali ostavi dio o garanciji"); `--nebitno "quote"` — goes out first.
   - `skrati 1:00`, `skrati na 45`, `skrati za 15` (shorter by 15 s) all work. It only removes; it never brings back parts that were cut before (use `dodaj` for that).
3. Tell the user in two or three lines what went out (by topic, not a list of every sentence) and the new length. If it says the result is clearly shorter than the target, thoughts were too long to fit — offer a higher target or a different rating. `vrati` undoes it; then `render.py`.

## Versions (`verzije.py`)

Every full or `--brzo` render is a version (`reel_vN.mp4` + `verzije/edit_vN.json` + date/length in `verzije/verzije.json`); `--izlaz` renders are not. Nothing is ever deleted.

- "pokaži verzije", "koje verzije imam": `python "<skill>/scripts/verzije.py" shofe_projekt` — every version with date, length, style, file, a one-line summary of what changed from the previous one, ► the version the user is watching, and unrendered changes in edit.json. Tell the user the list briefly (version, length, what changed).
- "vrati verziju 2", "vrati kako je bilo u prvoj", "ona prije mi je bila bolja": `python "<skill>/scripts/verzije.py" shofe_projekt vrati 2` (`--proba` to preview). edit.json becomes exactly that version; newer versions stay; its video already exists, so **do not render again** unless the user asks for changes — tell them which file to open. Later time-based commands read times from that version. `uredi.py vrati` undoes it.
  - "Vrati kako je bilo" is ambiguous: if there were uredi.py commands since the last render, use `uredi.py vrati` (one command back); if the user means the previous video they watched, use `verzije.py vrati <previous N>`. Ask only if both make sense.
- "što se promijenilo", "usporedi verziju 1 i 3", "što je drukčije od prve": `python "<skill>/scripts/verzije.py" shofe_projekt usporedi [A] [B]` (A/B = number or `trenutno`; no arguments = watched version → current edit.json if it has unrendered changes, otherwise previous → last render; one argument = that version → current). It prints length change, commands added/no longer active, removed and added parts with their time in each version and the reason, changed settings and subtitle text fixes. Summarise it for the user in 2–4 lines.
- "nazovi verziju 3 za Instagram": `verzije.py shofe_projekt nazovi 3 "za Instagram"` (shown in the list and comparisons).

## Subtitle files (`titlovi.py`)

Every render also writes `<video name>.srt` next to the video (`reel_v3.mp4` → `reel_v3.srt`): readable phrase subtitles for YouTube/Facebook/DaVinci/VLC — whole phrases, max 2 lines × 42 characters, 0.83–7 s each, broken at sentence ends and pauses, text exactly as corrected in `edit.json` (`tekst`, `izbaci`), times of the finished video (after `izrezi`, retakes and `brzina`). Hook is not included; case is as spoken (not the style's capitals). UTF-8 with BOM.

- After a render, mention the `.srt` in the report for YouTube uploads (YouTube Studio → Subtitles → Upload file → With timing). For a long 16:9 YouTube video suggest `titlovi: false` (no burned-in captions) + the SRT, so captions don't show twice.
- "napravi VTT", "titlovi za web": `python "<skill>/scripts/titlovi.py" shofe_projekt --format vtt` (or `oba`).
- "titlovi za verziju 2": `--verzija 2` (default: the version the user is watching). `--trenutno` = current edit.json before rendering (→ `titlovi_trenutno.srt`). `--ispis` prints them (use it to check text or answer questions about subtitle timing). `--izlaz ime` sets the file name.

## English subtitles (`prijevod.py`)

"Napravi engleske titlove", "prevedi titlove na engleski": **you** translate, cue by cue; the tool keeps the translations and writes `<video>.en.srt` with exactly the same times as the Croatian SRT.

1. `python "<skill>/scripts/prijevod.py" shofe_projekt` (default: the version the user is watching; `--verzija N`, `--trenutno` like titlovi.py). It writes `prijevod_en.json` in the project and lists the cues to translate (number, time, `max_znakova`, Croatian text); exit code 1 while something is missing.
2. Edit `prijevod_en.json`: fill `"en"` for every cue in `titlovi`, never change `"hr"`. Read all cues first so you translate with the whole video in mind. Rules:
   - natural spoken English as a native speaker would say it, not word for word; keep the speaker's tone (casual stays casual);
   - each cue translates what is said **during that cue** (a viewer reads it while hearing it); move a word to the neighbouring cue only when English word order needs it;
   - keep names, brands and show titles as they are (Sunčani4M, SF klima, Sunčani put, Sunčano AJMO!, Kutina, Renault 4); numbers as digits, prices as `€300`;
   - at most `max_znakova` characters (fits 2 lines × 42 and a comfortable reading speed); shorter is better than complete; optional manual line break with ` | `.
3. Run the same command again: it checks every cue (too long = error, nothing written; fast reading speed, untranslated = warning — fix them) and writes `reel_vN.en.srt` (`--format oba` adds `.en.vtt`, `--ispis` prints Croatian and English side by side). Tell the user the file name and how to upload it to YouTube as an extra language (Studio → Subtitles → Add language → English → Upload file).
- From then on **every render** also writes `<video>.en.srt` when all cues are translated, or prints `Titlovi (en): N titlova treba prevesti…` — then repeat steps 1–3 (only new/changed cues are empty; translations are matched by Croatian text, so cuts don't lose them). A cue with `"napomena": "preuzeto iz sličnog titla … — provjeri"` got the translation of a slightly different older cue (e.g. a corrected word): check it, fix `"en"` if needed and delete `napomena`.
- Other languages: `--jezik de` (→ `prijevod_de.json`, field `"de"`, `.de.srt`). Burned-in English captions are not supported yet (only the file).

## DaVinci Resolve export (`davinci.py`)

Every render also writes `<video name>.fcpxml` next to the video and its `.srt` (`reel_v3.mp4` → `reel_v3.fcpxml`): an FCPXML 1.10 timeline that DaVinci Resolve 18+ (free version too) imports with File > Import > Timeline. It uses the user's **original clips** (paths from `project.json`) with exactly the same cuts as the video, the same framing (landscape clips fill the 9:16 frame, shifted like `--crop-x`), punch-in zooms as Zoom, music on its own track (lane below, ducking not carried over) and markers for the style, hook title and zooms. Sound and colour stay untouched so the user can finish them in DaVinci. Subtitles: File > Import > Subtitle > `reel_v3.srt`, then drag onto the timeline.

- "otvori u DaVinciju", "izvezi za DaVinci": tell the user the `.fcpxml` and `.srt` file names and the two import steps above; say that Resolve asks to find the clips only if they were moved.
- For an older version / before rendering: `python "<skill>/scripts/davinci.py" shofe_projekt [--verzija N | --trenutno] [--ispis]` (also writes the `.srt` if missing; `--ispis` lists every shot: source file and in–out).
- If an original clip no longer exists, the whole timeline uses the prepared `source.mp4` (already cropped, 30 fps) and the tool says so. `--izvor priprema` forces that — use it when the user reports wrong framing or frame-off cuts from mixed frame rates in DaVinci.
- Projects prepared before Shofe 0.13 have no per-clip crop in `project.json`: the default crop (`--crop-x 0.5`) is assumed; if the user had used `--crop-x`, use `--izvor priprema`.

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
| makni dio o X | `uredi.py makni --od … --do …` / `--tema` (see "Commands by content") |
| makni 1:20–1:45 / zadrži samo 0:10–0:40 | `uredi.py` (see above), never by hand |
| vrati dio o X / zadrži drugi pokušaj | `uredi.py dodaj --od … --cijele-recenice` (+ `makni` the other take) |
| pokaži verzije / vrati verziju 2 / što se promijenilo | `verzije.py` (see "Versions") |
| skrati na 60 s / ispod minute / za 15 s | `uredi.py skrati 60 --proba`, rate thoughts, then `skrati 60 --ocjene …` (see "Shorten") |
| promijeni naslov | `hook`; `hook_trajanje` for how long it shows |
| traka napretka | `traka_napretka`: true |
| kraće pauze / više zraka | pick a style with tighter/looser cuts, or edit `rezanje` in that style's JSON |

Null fields mean "use the style default". Keep `odsjecci` IDs unchanged.

## Styles

Defined in `<skill>/styles/*.json` (Croatian keys). To make a new look the user likes, copy the closest style file to a new name and change `font` (Montserrat Black / Montserrat ExtraBold / Montserrat SemiBold / Anton, all bundled in `fonts/`), sizes, colours (`#RRGGBB`, background `#RRGGBBAA`), `nacin` (karaoke = active word lit; rijec = one big word; linija = whole line), `max_rijeci`, `otkrivanje` (words appear as spoken), `pop`, `zoom`, `boja_slike`, `rezanje` ([seconds before, seconds after] each kept phrase), hook colours, `traka_napretka`.

## Vocabulary

The vocabulary learns from corrections, so the user corrects each misheard name only once or twice:

- `<skill>/rjecnik.txt` is the base list of names/terms (shipped with Shofe; reinstalling overwrites it). The user's own data lives in `%LOCALAPPDATA%/Shofe/rjecnik.json` and survives reinstalls — never edit that file by hand, use `rjecnik.py`.
- **Learning is automatic**: every render compares your corrected `tekst` with the transcript and remembers real misrecognitions (names, brands, diacritics, capitalised names, up to 3 words → 3 words: `Fertelmes → Fertelmeš`, `esef → SF`, `sunčani četiri m → Sunčani4M`, `kutine → Kutine`). Grammar fixes (case endings like `klime → klima`, short words like `je → sam`), rewording, number formatting, removed fillers and sentence-initial capitals are NOT learned. A correction becomes **active** after it was seen twice (in one or several videos); render prints `Rječnik naučio: X → Y` — tell the user in one line.
- Active corrections are applied by `plan.py` to the new `edit.json` (`transcript.txt` shows `[rječnik: …]`; the segment gets `"rjecnik": [{"iz", "u"}]`). Check them like any other text. If one is wrong in this video, just change `tekst` back: the next render notices the revert and switches that learned correction off. Corrected names (with capitals/digits or multi-word) also go into whisper's prompt (≤ 200 tokens, base list first) so transcription spells them right.
- `python "<skill>/scripts/rjecnik.py" popis` — terms and corrections (✓ active, · waiting `viđen 1/2`, switched off). Use it when the user asks "što je Shofe naučio" / "pokaži rječnik".
- `rjecnik.py dodaj "Ime Prezime"` — a term for transcription (user: "zapamti ime X", a guest's name before transcribing). `rjecnik.py dodaj "krivo" "točno"` — a correction active immediately (user: "uvijek piši X umjesto Y").
- `rjecnik.py zaboravi "krivo"` — switch off a correction for good (or remove a term the user added). `rjecnik.py primijeni shofe_projekt [--proba]` — apply active corrections to an existing edit.json (a project planned before the word was learned). `plan.py --bez-rjecnika` plans without them.

## Troubleshooting

- `ffmpeg nije pronađen` right after installing → restart Claude so PATH updates, or run doctor again (it also searches the winget folder).
- Transcription very slow → `--model medium` or `small`; an NVIDIA GPU is used automatically if CUDA libraries are present.
- Empty transcript → the clip has no speech or the wrong language; try `--jezik auto`.
- Subtitles in a wrong font → make sure `shofe_projekt/fonts` exists (render.py copies it) and the style's `font` name matches one of the four bundled fonts exactly.
- `govornici.py` cannot download models (no internet / firewall) → it needs internet once; models live in `%LOCALAPPDATA%/Shofe/modeli` (or `SHOFE_MODELI`). Wrong speaker on a short reply ("Da.", "Točno.") is expected: under ~1 s there is too little voice; fix that segment's `govornik` by hand if it matters.
- Never delete the user's original clips; all work happens in the project folder.
