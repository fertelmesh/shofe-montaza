# ODLUKE

Svaka značajna odluka: datum, odluka, zašto, alternative, izvori. Najnovije na vrhu.

## 2026-11-25 — CI i Windows: prepoznavanje ffmpega po libavfilteru, choco u CI-ju
- Odluka: `-/filter_complex` (ffmpeg 7+) ili `-filter_complex_script` (≤6) bira se po glavnoj verziji iz `ffmpeg -version`; kad je to git build bez broja verzije (Gyan "2025-…-git", BtbN "N-…"), verzija se računa iz libavfilter (10 → 7, 11 → 8). Prije je nepoznata verzija značila "6", a staru opciju ffmpeg 7 samo trpi kao zastarjelu.
- CI: Linux (apt, ffmpeg 6.1) + Windows (choco, Gyan build 7/8) za sve testove i dimni test prave transkripcije (whisper tiny) na oba sustava; prije testova `doctor.py` mora javiti ffmpeg OK (subtitles, loudnorm, zscale, libx264…).
- Sitni Windows popravci: `doctor.py --popravi` više ne koristi `os.execv` (na Windowsu lomi putanje s razmacima), concat lista escapea apostrof u putanji, svi `subprocess` izlazi čitaju se kao UTF-8.
- Provjereno lokalno s ffmpeg 6.1 i 7.0.2 (statički build), testna mapa ima razmak, dijakritike i apostrof.
- Alternative: FedericoCarboni/setup-ffmpeg akcija (dodatna ovisnost, ništa ne dobivamo), winget na runneru (nije pouzdano dostupan u GitHub Actions).
- Izvori: https://ffmpeg.org/ffmpeg-all.html (opcija `-/`), https://trac.ffmpeg.org/ticket/10893 , https://docs.python.org/3/library/os.html#os.execv

## 2026-11-25 — Agent radi samostalno
- Odluka (Marko): agent sam odlučuje prema istraživanju, sam spaja promjene kad CI prođe, radi u krugovima svaka 2 sata. Kontrolne točke su pregledi s demom, ne zaustavljanje.

## 2026-11-25 — DaVinci: izvoz timelinea, ne dodatak
- Odluka: modul 10 izvozi FCPXML + SRT; nema dodatka unutar DaVincija.
- Zašto: DaVinci Resolve 21.1 je izbacio Python skripte iz besplatne verzije (treba Studio, 295 $); dodatak radi samo uz otvoren DaVinci i agent ga ne može testirati. Besplatni Resolve uvozi timeline (File > Import > Timeline) i SRT.
- Izvori: https://www.pugetsystems.com/blog/2026/09/10/how-davinci-resolve-free-v21-1-scripting-changes-affect-puget-bench/ , https://sonix.ai/ai/add-subtitles-davinci-resolve/

## 2026-11-24 — Grafika: HyperFrames, ne Remotion
- Odluka: HTML predlošci renderirani HyperFramesom; ffmpeg za sve ostalo.
- Zašto: Apache-2.0, bez naknada i ograničenja veličine tvrtke; radi s GSAP/CSS/Lottie/three.js; napravljen za AI agente. Remotion je besplatan samo za pojedince i tvrtke do 3 osobe.
- Izvori: https://github.com/heygen-com/hyperframes , https://www.remotion.dev/docs/license/faq

## 2026-11-24 — Izdvajanje osobe: ne GPL dok se ne odluči o prodaji
- Robust Video Matting je GPL-3.0. Tražiti permisivni model.
- Izvor: https://github.com/PeterL1n/RobustVideoMatting

## 2026-11-24 — Temelj v1
- Python + ffmpeg, bez okvira; Claude Code skill kao sučelje. Lokalna transkripcija faster-whisper (MIT), zadani model large-v3-turbo, hr.
- Rezovi: select na mreži sličica (granice zaokružene na 1/fps, tolerancija pola sličice) + zvuk atrim s mikro-pretapanjem 8–12 ms → bez pomaka zvuka i slike.
- Titlovi: ASS + libass, fontovi Montserrat i Anton (OFL) iz mape projekta (fontsdir), da rade na Windowsu bez instalacije fontova.
- Zvuk: highpass, afftdn, kompresor, glazba sa sidechain stišavanjem, loudnorm −14 LUFS.
