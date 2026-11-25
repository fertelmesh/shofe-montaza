# ODLUKE

Svaka značajna odluka: datum, odluka, zašto, alternative, izvori. Najnovije na vrhu.

## 2026-11-25 — Naredbe po vremenu (uredi.py): rezovi u vremenu izvornog videa, poravnati na riječi
- Odluka: „makni 1:20–1:45" / „zadrži samo 0:10–0:40" pretvaraju se u popis `izrezi` u edit.json: dijelovi **izvornog** videa (`od`, `do` u sekundama source.mp4) + broj naredbe, tekst naredbe i izrezane riječi. `render.py` (build_cuts) iz zadržanih odsječaka izbacuje riječi kojima je sredina u izrezu i oduzima te dijelove od rezova. Odsječci i njihovi brojevi ostaju isti (karta videa i transcript.txt i dalje odgovaraju).
- Vremena se čitaju iz **zadnjeg renderiranog videa** (`verzije/edit_vN.json`), jer korisnik gleda taj video: dvije naredbe zaredom bez novog rendera obje se odnose na isti video, a vremena izvornog videa u `izrezi` se ne pomiču kad se kasnije nešto drugo promijeni. `--verzija N` za stariji reel, `--trenutno` za trenutni edit.json.
- Granice se poravnaju na riječi: riječ ide van ako joj je sredina u zadanom dijelu; rez pada u sredinu pauze između riječi (najviše 0,3 s od riječi). Kad zadano vrijeme pada usred riječi, alat to javi i kaže je li riječ otišla ili ostala. Isto rade alati za montažu po tekstu (Premiere/Firefly text-based editing, Descript): korisnik bira riječi, rez ide na granicu riječi.
- Ispravljeni tekst (Claude ga mijenja u edit.json, pa broj riječi ne mora odgovarati transkriptu) poravna se s riječima transkripta preko difflib, pa izrez usred odsječka miče i pravi dio ispravljenog teksta.
- „Vrati": prije svake naredbe kopija edit.json ide u `povijest/NNN_naredba.json`; `uredi.py vrati` vraća zadnju. Puni sustav verzija je M2.4.
- Alternative: (a) mijenjati `od`/`do` odsječaka i dijeliti odsječke na dva — mijenja brojeve odsječaka i lomi ispravljeni tekst; (b) izrezi u vremenu gotovog videa — pomiču se nakon svake druge izmjene; (c) rez točno na zadanim sekundama — reže usred riječi.
- Bez novih paketa.
- Izvori: https://helpx.adobe.com/premiere-pro/using/text-based-editing-faq.html , https://helpx.adobe.com/firefly/web/firefly-video-editor/work-with-transcript/text-based-editing.html , https://docs.python.org/3/library/difflib.html

## 2026-11-25 — Pregled karte videa: jedna HTML datoteka s vlastitim SVG-om, bez biblioteka
- Odluka: `pregled.py` piše `pregled.html` u mapu projekta: jedna datoteka, sav CSS i JavaScript unutra, podaci kao JSON u `<script type="application/json">`, vremenska crta crtana kao SVG u čistom JavaScriptu. Video se pušta iz `source.mp4` iz iste mape (H.264 + AAC, faststart — Edge i Chrome ga puštaju s diska). Radi bez interneta i bez servera: dvoklik u Exploreru.
- Sadržaj: brojke (trajanje, LUFS, udio govora, tišine, govornici, loši kadrovi), video, najjači trenuci po ocjeni, vremenska crta u 5 traka (glasnoća s tišinama, govornici, teme, trenuci, slika: loši kadrovi, rezovi, spojevi klipova) sa zumom, teme, udio govornika, upozorenja, transkript po odsječcima s pretragom. Klik bilo gdje skače u videu, a trenutni odsječak se ističe dok video ide.
- Ovojnica zvuka: najviša razina po stupcu iz istih 50-ms prozora koje analyze.py već mjeri (nema drugog dekodiranja), skalirana od 2. percentila (najmanje −60 dB) do vrha → 0–100; najviše 3000 stupaca (sat videa ≈ 140 KB stranice). U `analiza.json` je ne spremamo: Claude tu datoteku čita i ne treba mu 3000 brojeva.
- Sigurnost: tekst iz transkripta i Claudeovih opisa ide u stranicu samo kao JSON (svaki `<` kao `\u003c`) i u DOM kao `textContent`, pa „</script>" u govoru ne može pokvariti stranicu.
- `analyze.py` napravi pregled nakon analize i nakon `--provjeri` (kad Claude upiše teme i trenutke); ako pregled ne uspije, analiza svejedno vrijedi.
- Alternative: wavesurfer.js (BSD-3, dobar valni oblik i regije, ali ~30–40 KB koda za ugraditi i zasebni dodaci; vrijedi ponovno razmotriti za M6.1 gdje treba uređivanje); vis-timeline (Apache-2.0/MIT, ali ~500 KB i vuče moment/vis-data); matplotlib PNG (nema klikanja ni zuma). Vlastiti SVG je ~250 redaka, bez novih ovisnosti i licenci.
- Izvori: https://github.com/katspaugh/wavesurfer.js , https://github.com/visjs/vis-timeline , https://developer.mozilla.org/en-US/docs/Web/HTML/Element/script#embedding_data_in_html

## 2026-11-25 — Govornici (diarizacija): sherpa-onnx + pyannote segmentation-3.0 + 3D-Speaker CAM++
- Odluka: `govornici.py` koristi **sherpa-onnx** (Apache-2.0, gotovi paketi za Windows i Python 3.12–3.14, ~20 MB, bez PyTorcha) s modelima **pyannote segmentation-3.0** (MIT, 5,9 MB, puna preciznost) i **3D-Speaker CAM++ VoxCeleb** (Apache-2.0, 28 MB). Modeli se skidaju jednom s GitHub izdanja sherpa-onnxa (bez HuggingFace računa i tokena) u `%LOCALAPPDATA%\Shofe\modeli`; SHA-256 se provjerava, ali razlika je samo upozorenje (autori su CAM++ datoteku već jednom zamijenili, 19. 11. 2026.).
- Druga provjera (naša, ~10 % vremena): nakon brzog grupiranja svaki odsječak ≥ 1 s uspoređuje se s prosječnim glasom svakog govornika (bez sebe) i prebacuje ako mu je drugi jasno bliži (razlika kosinusa > 0,05). Bez nje je kratko pitanje znalo ostati pripisano prethodnom govorniku. Probali smo i „rastapanje" malog govornika sličnog drugome — pogoršalo je šumnu snimku (spojilo dvoje ljudi), pa je izbačeno.
- Riječi dobivaju govornika po najvećem preklapanju; otok od jedne riječi < 0,5 s usred drugog govornika se izgladi. `transcript.json` se ne mijenja: `plan.py` i `analyze.py` čitaju `govornici.json`, a odsječak se dijeli na promjeni govornika (isti brojevi u edit.json i analiza.json).
- Mjerenje (probni razgovor 55 s, 13 rečenica, 3 sintetska glasa; točnih rečenica): izvorno 12/13, dvaput kodiran AAC 12/13, ružičasti šum 12/13, −12 dB MP3 12/13, jeka 13/13; jedan govornik → 1. Promašaj je uvijek „Točno tako." (2 riječi, < 1 s). Isti test s int8 segmentacijom: 11–12/13, a s jekom 4 govornika umjesto 3 — zato puna preciznost. Ugrađeni modeli za glas na čistom testu: CAM++ i NeMo TitaNet-small 12/13, WeSpeaker ResNet34 osjetljiv na prag (pri 0,6 sve spoji u jednog).
- Brzina (2 jezgre u sandboxu): 10 min zvuka za 89 s → sat ≈ 9 min na 2 jezgre, na Markovom laptopu (4–8 jezgri) procjena 3–5 min. Zajedno s transkripcijom to je glavni trošak za cilj „karta za 60 min u 20 min" — izmjeriti u pregledu M1.
- Sintetski glasovi za test: espeak-ng varijante biraju se po sličnosti CAM++ glasa da budu različiti kao stvarni ljudi (A–C 0,40, A–B 0,29; varijanta hr+m3 bila je 0,97 = isti čovjek, odbačena).
- Alternative: pyannote community-1 (najbolji poznati DER, ali CC-BY-4.0, zatvoren iza HF tokena, PyTorch ~1 GB, na CPU-u RTF ~0,86 prema autoru paketa diarize); `diarize` (Apache-2.0, Silero VAD + WeSpeaker + spektralno grupiranje, tvrdi 4,8 % DER na VoxConverse, ali beta od svibnja 2026., jedan autor, vuče PyTorch); NeMo Sortformer (CC-BY-4.0 / NVIDIA licenca, težak); Reverb diarization (nekomercijalna licenca — isključeno); WeSpeaker modeli (licenca prati VoxCeleb, CC-BY-4.0 — izvan dopuštenog popisa).
- Licenca CAM++ VoxCeleb: stranicu ModelScopea nismo mogli otvoriti; Apache-2.0 potvrđuju 3D-Speaker projekt i neovisne kopije istog modela. Ako Marko odluči prodavati, to provjeriti još jednom.
- Nove ovisnosti: sherpa-onnx i sherpa-onnx-core (Apache-2.0); modeli MIT i Apache-2.0 (skidaju se, ne nalaze se u repozitoriju).
- Izvori: https://csukuangfj.github.io/sherpa/onnx/speaker-diarization/models.html , https://huggingface.co/spaces/k2-fsa/speaker-diarization/blob/main/model.py , https://huggingface.co/pyannote/segmentation-3.0 , https://huggingface.co/pyannote/speaker-diarization-community-1 , https://pypi.org/project/diarize/ , https://gitee.com/RapidAI/3D-Speaker , https://huggingface.co/SteveShines-0123/campplus-voxceleb , https://github.com/viaalink/models/releases/tag/speaker-recognition-2026-09

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
