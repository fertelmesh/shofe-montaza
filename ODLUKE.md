# ODLUKE

Svaka značajna odluka: datum, odluka, zašto, alternative, izvori. Najnovije na vrhu.

## 2026-11-25 — Karta videa (analyze.py): vlastita mjerenja u numpyju, bez OpenCV-a i PySceneDetecta
- Odluka: `analyze.py` radi dva prolaza ffmpegom. Zvuk: mono 16 kHz → RMS po 50 ms, prag tišine prilagođen snimci (5. i 95. percentil: šum i govor, prag na 35 % između, granice −55 dB i govor −12 dB), tišine ≥ 0,5 s; ukupna glasnoća, raspon i vrh iz ffmpeg `ebur128`. Slika: siva sličica (dulja stranica 256 px) za svaku sličicu → svjetlina, promjena (prosječna razlika blokova 8×8) i oštrina (varijanca Laplaceovog operatora) 5× u sekundi.
- Rezovi: kao PySceneDetect AdaptiveDetector — promjena sličice uspoređuje se s prosjekom 2 susjedne sličice sa svake strane (omjer ≥ 3, najmanja promjena 12, kadar najmanje 0,5 s); tako kretanje kamere ne daje lažne rezove. AdaptiveDetector ima najbolji F1 na BBC i AutoShot testovima PySceneDetecta (91,6 / 73,9).
- Mutno: oštrina ovisi o sadržaju (rešetka ima 3× manju varijancu od testne slike, a nije mutna — vidjeli na probnom klipu), pa se mjeri unutar kadra: mutno kad padne ispod 35 % 90. percentila istog kadra. Tamno: srednja svjetlina < 40 (Y), presvijetlo > 230. Sve ≥ 0,5 s.
- Tempo: slogovi hrvatske riječi = samoglasnici (ije = jedan) + slogotvorno r (krv, Hrvatska); oznake sporo < 4, brzo > 6,5 slogova/s. Brojke za hrvatski nismo našli (radovi Kovač 2018 i Matticchio 2018 daju samo usporedbe), pa su granice procjena za uobičajeni govor i prilagodit će se na Markovim snimkama.
- Teme i trenuci: piše ih Claude u `analiza.json` (ne lokalni model) — Claude ionako čita transkript, besplatno je i najbolje razumije hrvatski. `--provjeri` provjerava oblik; ponovna analiza ih čuva.
- Brzina: 120 s videa 1080×1920 (12 Mbit/s) za 18 s na 2 jezgre u sandboxu, gotovo sve je dekodiranje H.264 → 60 min ≈ 9 min na 2 jezgre, na Markovom laptopu (4–8 jezgri) procjena 3–5 min. `--bez-slike` za samo zvuk (sekunde).
- Alternative: PySceneDetect (BSD-3, ali vuče OpenCV ~40 MB i radi isti dekod); ffmpeg `scdet`/`select=scene` (fiksni prag, lošiji kod kretanja); `blurdetect` filter (nije u svim ffmpeg buildovima, treba ffmpeg 6+). Nema novih ovisnosti (numpy, BSD-3, već postoji).
- Izvori: https://raw.githubusercontent.com/Breakthrough/PySceneDetect/main/benchmark/README.md , https://www.scenedetect.com/docs/api.html , https://hrcak.srce.hr/clanak/295046 , https://www.bib.irb.hr/937198 , https://ffmpeg.org/ffmpeg-filters.html#ebur128

## 2026-11-25 — Verzije i popis paketa proizvoda
- Odluka: `shofe-montaza/VERSION` (semver, počinje 0.2.0 jer je v1 montaža bila 0.1), ispisuje je `doctor.py`. Python paketi proizvoda u `shofe-montaza/requirements.txt` (kopira se sa skillom); iz njega instaliraju `install.ps1` i `doctor.py --popravi`; korijenski `requirements.txt` samo upućuje na njega.
- Granice verzija: `faster-whisper>=1.1,<2` — gornja granica jer bi nova glavna verzija mogla promijeniti API; tjedni CI s najnovijim paketima javlja kvar prije Marka. Ne prikivamo točne verzije: na Windowsu bi to s novim Pythonom značilo da nema gotovih paketa.
- `doctor.py --popravi` više ne koristi `os.execv` (na Windowsu razbija putanje s razmacima).
- Alternative: lock datoteka (pip-tools/uv) — previše za Markovu instalaciju dvoklikom; verzija u kodu umjesto datoteke — teže za čitanje izvan Pythona.

## 2026-11-25 — Zvuk za transkripciju dekodira naš ffmpeg, ne PyAV
- Odluka: `transcribe.py` sam dekodira zvuk ffmpegom (mono, 16 kHz, float32) i predaje faster-whisperu numpy niz.
- Zašto: prvi CI je pao — svježa instalacija daje faster-whisper 1.2.1 + av 19.0.2, a av je izbacio argument `metadata_errors` koji faster-whisper koristi (`TypeError: open() got an unexpected keyword argument`). Marko bi s novom instalacijom dobio istu grešku. ffmpeg ionako mora postojati, a sam faster-whisper u kodu preporučuje ffmpeg izravno. Time PyAV više nije bitan za rad.
- Alternative: prikovati `av<17` (krhko, ruši se kad faster-whisper podigne donju granicu; na Windowsu možda nema gotovog kotača za Python 3.13+); čekati popravak u faster-whisperu (neizvjesno).
- Uz to: CI sada pokreće pravu transkripciju (whisper tiny) i na Windowsu, plus jednom tjedno, da se ovakvi kvarovi paketa uoče prije Marka. Akcije podignute na verzije s Node 24 (checkout@v5, setup-python@v6, cache@v5).
- Nova razvojna ovisnost: numpy (BSD-3-Clause), već dolazi s faster-whisperom.
- Izvori: https://github.com/SYSTRAN/faster-whisper/issues/719 , https://github.com/PyAV-Org/PyAV/issues/1559 , https://pypi.org/project/av/ , https://github.com/actions/checkout/pull/2248

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
