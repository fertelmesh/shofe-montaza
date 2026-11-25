# DNEVNIK

Jedan unos po krugu, najnoviji na dnu.

## 2026-11-25 00:15 — Postavljanje (Claude s Markom)
- Napravljen repo, prenesena Shofe v1 montaža (prepare, transcribe, plan, render, 5 stilova), testovi (9 prolazi lokalno na Linuxu), SPEC, EFEKTI, ROADMAP, ODLUKE, upute za agenta (CLAUDE.md).
- Dodan CI za Linux i Windows (još nije prošao ni jednom: prvi zadatak agenta je M1.3).
- Sljedeće: M1.3.

## 2026-11-25 00:40 — M1.3 CI na Linuxu i Windowsu
- Prvi CI: testovi montaže prolaze na Linuxu i Windowsu; pala je prava transkripcija. Uzrok: nova verzija paketa av (19) ne radi s faster-whisperom 1.2.1 — svaka svježa instalacija (i Markova) dobila bi grešku pri transkripciji.
- Popravak: `transcribe.py` sam dekodira zvuk ffmpegom (mono 16 kHz) i predaje ga whisperu; PyAV više nije bitan. Odluka u ODLUKE.md.
- CI: dimni test transkripcije (whisper tiny) sada i na Windowsu, provjerava jezik hr i vremena riječi; pokreće se i svakog ponedjeljka da uhvati pokvarene nove pakete. Novi testovi `tests/test_audio.py` (putanja s razmakom i č/ć/ž, snimka bez zvuka).
- Windows CI je pao jer choco nije mogao skinuti ffmpeg (njihov server). Sada CI skida Gyan build s GitHuba (isti kao winget Gyan.FFmpeg kod Marka), choco je rezerva; dodan korak `doctor.py` koji provjerava sve što Shofe treba.
- Testovi lokalno: 11 prošlo, 1 preskočen (model se u sandboxu ne može skinuti; provjera u CI-ju).
- Za Marka: ako si već instalirao Shofe i transkripcija pada s „metadata_errors", ponovno pokreni INSTALIRAJ.bat nakon ovog spajanja.
- Sljedeće: M1.4 (requirements.txt, VERSION, verzija u doctor.py, install.ps1 iz requirements.txt).

## 2026-11-25 00:45 — M1.4 verzija i popis paketa
- PR #1 (M1.3) spojen: CI zelen na Linuxu i Windowsu, prava transkripcija (whisper tiny) prolazi i na Windowsu.
- Novo: `shofe-montaza/VERSION` (0.2.0), `doctor.py` ispisuje verziju (`--verzija` samo nju); `shofe-montaza/requirements.txt` (faster-whisper, numpy) iz kojeg instaliraju `install.ps1` i `doctor.py --popravi`.
- `install.ps1` na kraju javlja crveno ako nešto nedostaje i vraća kod greške; CI ga sada pokreće na Windowsu u Windows PowerShellu 5.1 kao INSTALIRAJ.bat.
- Popravak: `doctor.py --popravi` više ne puca na putanjama s razmakom (bez `os.execv`).
- Testovi lokalno: 15 prošlo, 1 preskočen.
- Sljedeće: M1.5 karta videa (`analyze.py`).

## 2026-11-25 01:20 — M1.5 karta videa
- Živa specifikacija pročitana: bez promjena u odnosu na SPEC.md. Otvorenih issuea i PR-ova nema.
- Novo: `analyze.py` → `analiza.json` + čitljivi `analiza.txt`: tišine, glasnoća (cijeli video u LUFS + po odsječku, oznake tiho/glasno), tempo govora (slogova u sekundi, sporo/normalno/brzo), rezovi i kadrovi, spojevi klipova, mutni/tamni/presvijetli dijelovi. Odsječci imaju iste brojeve kao u edit.json. `--bez-slike` za brzu analizu samo zvuka.
- Teme i najjači trenuci (hook, poanta, smijeh, savjet…) upisuje Claude prema uputama u SKILL.md; `analyze.py --provjeri` provjerava ih, ponovna analiza ih čuva.
- Bez novih paketa (samo numpy + ffmpeg). Odluka i izvori u ODLUKE.md. Verzija 0.3.0.
- Brzina u sandboxu (2 jezgre): 120 s videa 1080×1920 za 18 s → sat videa ≈ 9 min samo za sliku; zvuk par sekundi. Na Markovom laptopu treba izmjeriti (dio pregleda M1).
- Testovi: novi `tests/test_analyze.py` na sintetskom videu s poznatim tišinama, rezovima, mutnim i tamnim dijelom (svi pogođeni na ±0,1–0,25 s) + slogovi hrvatskih riječi. Lokalno 35 prošlo, 1 preskočen.
- Sljedeće: M1.6 govornici (diarizacija na procesoru, permisivna licenca).

## 2026-11-25 02:45 — M1.6 govornici (diarizacija)
- Živa specifikacija pročitana: bez promjena. Otvorenih issuea i PR-ova nema.
- Istraživanje: sherpa-onnx + pyannote segmentation-3.0 (MIT) + 3D-Speaker CAM++ (Apache-2.0) — bez PyTorcha i HuggingFace tokena, gotovi paketi za Windows. pyannote community-1 odbačen (CC-BY-4.0, token, PyTorch, sporo na procesoru), `diarize` (beta, PyTorch), Reverb (nekomercijalno). Detalji u ODLUKE.md.
- Novo: `govornici.py` → `govornici.json` (G1, G2… + udio govora), `--broj`, `--prag`, `--imena`. Naša druga provjera prebacuje krivo grupirane odsječke. `plan.py` i `analyze.py` stavljaju govornika na svaki odsječak; odsječak nikad ne prelazi na drugog govornika; `transcript.txt` piše `Ime: tekst`. `doctor.py` provjerava sherpa-onnx. Verzija 0.4.0.
- Test: novi probni razgovor `tests/fixtures/razgovor.m4a` (3 sintetska glasa, 13 rečenica) + `make_dvoglasje.py`. Točnost 12–13/13 rečenica i uz šum, jeku, tihi MP3; jedan govornik → 1. Promašuje samo „Točno tako." (< 1 s). Brzina 10 min zvuka / 89 s na 2 jezgre.
- Testovi lokalno: 45 prošlo, 1 preskočen (whisper). Pravi model se u CI-ju pokreće na Linuxu i Windowsu.
- Za Marka: ništa sad; na pregledu M1 trebat će prava snimka s dvoje-troje ljudi (sintetski glasovi nisu pravi ljudi).
- Sljedeće: M1.7 pregled karte videa kao HTML stranica.
