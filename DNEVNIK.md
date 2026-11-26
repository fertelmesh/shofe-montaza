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

## 2026-11-25 04:10 — M1.7 pregled karte videa (HTML)
- Živa specifikacija pročitana: bez promjena. Otvorenih issuea i PR-ova nema.
- Novo: `pregled.py` → `pregled.html` u mapi projekta: jedna datoteka, radi bez interneta (dvoklik). Video + najjači trenuci po ocjeni, vremenska crta (glasnoća s tišinama, govornici u boji, teme, trenuci, loši kadrovi / rezovi / spojevi) sa zumom, teme, udio govornika, upozorenja, transkript s pretragom. Klik bilo gdje skače u videu; trenutni odsječak se ističe.
- `analyze.py` ga sam napravi nakon analize i nakon `--provjeri` (kad Claude upiše teme i trenutke). SKILL.md: „pokaži kartu videa" → `pregled.py --otvori`. README za Marka dopunjen. Verzija 0.5.0.
- Bez novih paketa (vlastiti SVG, bez biblioteka); odluka u ODLUKE.md. Sat videa → stranica ~150 KB, otvara se < 0,5 s.
- Provjera očima: snimke stranice svijetlo/tamno/mobitel na probnom razgovoru (3 govornika, teme, trenuci, tamni dio) i na izmišljenoj karti od 60 min — izgleda uredno, bez JS grešaka.
- Testovi: novi `tests/test_pregled.py` (ovojnica, sigurnost teksta „</script>", analyze → pregled → --provjeri, test u Chromiumu kroz Playwright). CI na Linuxu sada instalira Playwright + Chromium. Lokalno 48 prošlo, 3 preskočena (pravi modeli).
- Sljedeće: M1.8 pregled M1 (demo videi + issue za Marka).

## 2026-11-25 06:20 — M1.8 pregled M1 (demo + issue)
- Živa specifikacija pročitana: bez promjena. Otvorenih issuea i PR-ova nema.
- Novo: `tests/make_demo.py` napravi demo u `demo/` iz probnih snimki: `M1_reel.mp4` (24 s sirovo → 15 s reel, stil suncani, hook, glazba), `M1_stilovi.mp4` (svih 5 stilova), `M1_karta_videa.mp4` (snimka zaslona karte videa: klik na trenutak, zum, tema, pretraga) + slike `M1_kadrovi.png`, `M1_karta_videa.png`. Ukupno 5 MB; `demo/README.md` objašnjava svaku datoteku.
- Provjera očima: kadrovi reela, svih 5 stilova i stranica karte videa pregledani; govornike na probnom razgovoru prepoznao pravi model (12/13, promašen „Točno tako."), rezovi na 18 s i 36 s i tamni dio 40–44 s pogođeni.
- Proizvod nepromijenjen (verzija ostaje 0.5.0). Testovi lokalno: 50 prošlo, 1 preskočen.
- Za Marka: issue „Pregled M1" — instalacija, jedan pravi reel, jedna dulja snimka s 2–3 osobe (izmjeriti vrijeme karte videa; cilj sat snimke ≤ 20 min), testni klipovi u `tests/real/`, otvorene odluke (laptop, kamere u R4).
- Sljedeće: M2.1 `uredi.py` (naredbe po vremenu).

## 2026-11-25 08:50 — M2.1 naredbe po vremenu (uredi.py)
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `uredi.py` — `makni 1:20-1:45` (i više dijelova odjednom), `zadrzi 0:10-0:40`, `popis` (što je gdje u gotovom videu), `vrati` (poništi zadnju naredbu, može i više puta), `--proba`. Vremena se čitaju iz zadnjeg renderiranog videa (ono što je Marko gledao); `--verzija N`, `--trenutno`. Prima `1:20`, `1:20,5`, `0:01:20`, `80`, `od 1:20 do 1:45`, dugu crticu s mobitela.
- Rezovi se poravnaju na cijele riječi i upisuju u edit.json kao `izrezi` u vremenu izvornog videa; `render.py` ih poštuje (i ispravljeni tekst titlova prati rez). Brojevi odsječaka se ne mijenjaju. Odluka u ODLUKE.md. Verzija 0.6.0.
- SKILL.md: Claude za vremena iz videa uvijek koristi uredi.py, javi koje su riječi otišle i novo trajanje. README za Marka dopunjen.
- Provjera očima: kadrovi nakon „makni" — titlovi nastavljaju točno iza reza, bez izrezanih riječi.
- Testovi: novi `tests/test_uredi.py` (23: oblici vremena, točne riječi, granica usred riječi, zadrži, vrati, proba, vremena iz zadnjeg rendera, ispravljeni tekst, pravi render s duljinom). Lokalno 71 prošlo, 3 preskočena.
- Sljedeće: M2.2 naredbe po sadržaju (testni skup od 10 naredbi).

## 2026-11-25 10:25 — M2.2 naredbe po sadržaju
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `uredi.py` radi i po sadržaju. Claude u transcript.txt nađe dio i preda doslovni citat: `makni --od "Prvo, koliko košta" --do "tristo eura."`; ili `--tema "održavanje"` (iz analiza.json), `--odsjecak 5-7`, `--rijeci 40-62`. `--cijele-recenice` širi na cijele rečenice. Nove naredbe: `dodaj` (vrati izbačeni dio, npr. drugi pokušaj ili maknutu temu) i `trazi "riječ"` (gdje se spominje, s vremenima u gotovom videu). `zadrzi` po sadržaju može vratiti i izbačene riječi.
- Novi `sadrzaj.py`: citat mora postojati u transkriptu (inače greška + najsličniji dijelovi), više pojava → popis s vremenima i `--pojava N`. Ne smetaju mu kvačice, velika slova, drugi padež ni sitne greške prepoznavanja; traži i u Claudeovim ispravcima teksta. Upozori kad odabir počinje/završava usred rečenice. Odluka i izvori u ODLUKE.md. Verzija 0.7.0.
- Testni skup od 11 naredbi (`tests/fixtures/naredbe_sadrzaj.json`, izmišljeni reel SF klima s tri pokušaja uvoda): „izreži dio o cijeni", „zadrži drugi pokušaj uvoda", „makni dio o održavanju", „zadrži samo savjet o filteru", „makni cijenu ali ostavi rečenicu o tisuću eura", citat bez kvačica, dvosmislen citat, izmišljeni citat… — svih 11 pogađa točne riječi.
- Provjera očima: render nakon „vrati drugi pokušaj + makni cijenu" — vremenski kod izvornog videa u kadrovima potvrđuje da su na pravim mjestima drugi pokušaj (6,4 s) i rečenica o tisuću eura (20,6 s); titlovi odgovaraju.
- Testovi: novi `tests/test_sadrzaj.py` (23 testa, uključujući pravi render). Lokalno 93 prošlo, 3 preskočena.
- Za Marka: ništa sad. Pravo mjerilo („9 od 10 naredbi pogodi pravi dio") provjerit ćemo na tvojim snimkama u pregledu M2.
- Sljedeće: M2.3 „skrati na N sekundi".

## 2026-11-25 12:25 — M2.3 „skrati na N sekundi"
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `uredi.py skrati 60` (i `1:00`, `na 45`, `za 15`) + modul `skrati.py`. Video se dijeli na cijele misli; pitanje ostaje s odgovorom, „Drugo, ugradnja." s onim što najavljuje, a rečenica koja počinje s „A/Zato/To/Još…" ne ostaje bez prethodne. `--proba` ispiše sve misli s vremenom u videu, trajanjem i važnošću; Claude ih ocijeni (`--ocjene "3:5,7-9:1"`), a `--obavezno "citat"` / `--nebitno "citat"` za ono što Marko izričito traži. Bez Claudeovih ocjena: trenuci iz analiza.json, središnjost misli (TF-IDF), uvod i kraj malo više.
- Odabir: naprtnjača po lancima misli (numpy), zatim mjerenje pravog trajanja gotovog videa i podešavanje dok ne bude ≤ N, tik ispod. Ide kroz iste `izrezi` kao druge naredbe, `vrati` radi; nikad ne vraća već izrezano. Odluka i izvori u ODLUKE.md. Verzija 0.8.0.
- Mjerenje: probni reel 46 s → 12/15/20/30/40 s daje 11,8/14,5/19,6/30,0/38,6 s, sve rečenice cijele. Sat snimke → 10 min: 9:58,7 za ~11 s.
- Provjera očima: render nakon „skrati na 20" s Claudeovim ocjenama (cijena i održavanje 5) — vremenski kod izvornog videa u kadrovima potvrđuje redoslijed uvod → cijena → održavanje → „Pratite SF klimu", titlovi odgovaraju, video 19,5 s.
- Testovi: novi `tests/test_skrati.py` (21: misli i veze, lanci, ocjene, trenuci, obavezno/nebitno, vrati, brzina, sat snimke, pravi render). SKILL.md (postupak: proba → Claude ocijeni → skrati) i README dopunjeni.
- Za Marka: ništa sad. Na pregledu M2 probaj „skrati na 30 sekundi" na pravom reelu.
- Sljedeće: M2.4 verzije (popis, „vrati verziju N", usporedba).


## 2026-11-25 14:35 — M2.4 verzije (popis, vrati verziju N, usporedba)
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `verzije.py` — `popis` (svaka verzija s datumom, trajanjem, stilom, datotekom i jednim retkom što se promijenilo prema prethodnoj; ► verzija koju Marko gleda; nerenderirane izmjene), `vrati N` (edit.json kao u verziji N; novije ostaju, video već postoji pa nema novog rendera; `uredi.py vrati` to poništava), `usporedi [A] [B]` (izbačene/dodane rečenice s vremenom u svakoj verziji i razlogom, nove i poništene naredbe, postavke, ispravci teksta), `nazovi N "naziv"`.
- `render.py` nakon uspješnog rendera upisuje verziju u `verzije/verzije.json` (datum, datoteka, trajanje, brzi pregled); broj verzije više ne može prepisati staru kad se video obriše. Vremena u naredbama čitaju se iz verzije koju Marko gleda (zadnji render ili vraćena verzija). Odluka i izvori u ODLUKE.md. Verzija 0.9.0.
- Brzina: vremenska crta gotovog videa za sat snimke 1,5 s → 0,05 s (binarno pretraživanje, rezultat provjeren identičan), pa su i sve `uredi.py` naredbe brže; popis 9 verzija sata snimke < 1 s.
- Provjera: ispis popisa, usporedbe i vraćanja na probnom reelu s tri verzije (makni, stil kino + veći titlovi + ispravak teksta, skrati na 10 s) — čitljivo, točne riječi i vremena.
- Testovi: novi `tests/test_verzije.py` (20, uključujući dva prava rendera i sat snimke). Lokalno 134 prošlo, 3 preskočena.
- Za Marka: ništa sad. Na pregledu M2 probaj „pokaži verzije", „vrati verziju 1" i „što se promijenilo".
- Sljedeće: M2.5 titlovi (SRT/VTT, rječnik iz ispravaka, engleski prijevod).

## 2026-11-25 16:30 — M2.5a titlovi kao datoteka (SRT/VTT)
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema. Na početku kruga GitHub je ~10 min vraćao 503 (kratko radio na zastarjeloj kopiji repozitorija; taj rad odbačen, ništa nije spojeno).
- M2.5 podijeljen na a (SRT/VTT), b (rječnik iz ispravaka), c (engleski prijevod).
- Novo: `render.py` uz svaki video napiše `reel_vN.srt` (isto ime → VLC ga sam učita, YouTube upload). `titlovi.py`: `--format vtt|oba`, `--verzija N`, `--trenutno`, `--ispis`, `--izlaz`. Titlovi su fraze za čitanje: najviše 2 retka × 42 znaka, 0,83–7 s, rez na kraju rečenice/stanci, preduga fraza puca na zarezu, redak ne završava prijedlogom; tekst iz edit.json (ispravci, izbaci), vremena gotovog videa (rezovi, izrezi, brzina). SRT u UTF-8 s BOM-om i CRLF na svakom sustavu (DaVinci/Windows; prvi CI na Windowsu pao jer je Python sam pretvarao LF u CRLF). Verzija 0.10.0. Odluka i izvori u ODLUKE.md.
- Provjera očima: SRT ucrtan na kadar gotovog videa na 8,5 s — „Drugi korak, skinite filter / i operite ga mlakom vodom." točno uz karaoke titl, dijakritike ispravne. Probni razgovor (125 riječi) → 15 titlova, svi prelomi na prirodnim mjestima.
- Testovi: novi `tests/test_titlovi.py` (9: rečenice, 2×42, prijelom, stanke, 7 s, BOM/format, pravi render i usporedba s trajanjem videa, ispravci + brzina + uredi.py makni, CLI). Lokalno 143 prošlo, 3 preskočena.
- Za Marka: ništa sad. Na pregledu M2 prenesi `reel_vN.srt` na YouTube (Studio → Titlovi → Prenesi datoteku).
- Sljedeće: M2.5b rječnik iz ispravaka.

## 2026-11-25 18:20 — M2.5b rječnik koji uči iz ispravaka
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `rjecnik.py`. Nakon svakog rendera Shofe usporedi ispravljeni tekst titlova s transkriptom i zapamti krivo čute riječi i imena (do 3 riječi: „Fertelmes → Fertelmeš", „esef → SF", „sunčani četiri m → Sunčani4M", „kutine → Kutine"). Kad isti ispravak vidi 2× (u jednom ili više videa), postaje aktivan: `plan.py` ga sam primijeni na novi edit.json (`[rječnik: …]` u transcript.txt), a ispravljeno ime ide i u whisperov upit (≤ 200 tokena, osnovni rjecnik.txt prvi).
- Ne uči gramatiku (padeži „klime → klima", kratke riječi „je → sam"), preformulirano, brojeve („tristo → 300"), veliko slovo na početku rečenice ni izbačene poluglasove. Ako netko vrati automatski ispravak na staro, sljedeći render ga isključi. Ponovljeni render istog videa ne broji dvaput.
- Naredbe: `popis`, `nauci`, `primijeni`, `dodaj "Ime"` / `dodaj "krivo" "točno"`, `zaboravi`; `plan.py --bez-rjecnika`. Naučeno se čuva u `%LOCALAPPDATA%\Shofe\rjecnik.json` (ponovna instalacija ga ne briše). Odluka i izvori u ODLUKE.md. Verzija 0.11.0.
- Provjera očima: kadrovi reela u kojem je whisper čuo „kutine." i „sunčanon" — nakon plana s rječnikom titlovi pišu „KUTINE." i „SUNČANOM PUTU!".
- Testovi: novi `tests/test_rjecnik.py` (28: 14 slučajeva što se uči a što ne, brojanje po projektima, vraćanje ispravka, primjena s interpunkcijom i velikim slovom, granica tokena, naredbe, cijeli put render → nauči → novi plan → SRT). `tests/conftest.py`: testovi nikad ne pišu u pravi rječnik.
- Za Marka: ništa sad. Na pregledu M2: ispravi ime u dva videa i pogledaj da ga treći napiše sam („pokaži rječnik").
- Sljedeće: M2.5c engleski prijevod titlova.

## 2026-11-25 20:35 — M2.5c engleski prijevod titlova
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `prijevod.py`. Prvo pokretanje napravi `prijevod_en.json` (svaki titl: vrijeme, najviše znakova, hrvatski tekst, prazno `en`); Claude upiše prijevode; drugo pokretanje provjeri i napiše `reel_vN.en.srt` (`--format oba` i `.en.vtt`) s istim vremenima kao hrvatski SRT. Pravila za Claudea u SKILL.md: prirodan govorni engleski, titl prevodi ono što se tada govori, imena (Sunčani4M, SF klima, Kutina) ostaju, `€300`.
- Pamćenje po hrvatskom tekstu titla: nakon novih rezova prevodi se samo novo/promijenjeno, stare verzije rade bez ponovnog prevođenja; malo promijenjen titl preuzme stari prijevod uz napomenu „provjeri". Kad projekt ima prijevod, `render.py` sam napiše `<video>.en.srt` ili javi koliko titlova treba prevesti. `--jezik de` za druge jezike.
- Provjere: 2 × 42 znaka (dulje = greška), prijelom ne iza the/and/of…, ručni prelom „|", upozorenje za > 20 znakova/s i neprevedeno. `titlovi.py`: zajednički odabir verzije (`pick`) i prijelom za bilo koji jezik. Odluka i izvori u ODLUKE.md (lokalni strojni prijevod odbačen za sada). Verzija 0.12.0.
- Provjera očima: engleski SRT ucrtan na kadar gotovog videa na 7,5 s — „Step two: take out the filter / and wash it in lukewarm water." točno dok se govori „skinite filter i…", dva ravnomjerna retka.
- Testovi: novi `tests/test_prijevod.py` (4: prijelom i provjere, pamćenje kroz rezove i napomene, cijeli put render → prijevod → makni → render sam napiše .en.srt → ispravak teksta, drugi jezik i greške). Lokalno 175 prošlo, 3 preskočena.
- Za Marka: ništa sad. Na pregledu M2 reci „napravi i engleske titlove" i prenesi `.en.srt` na YouTube kao drugi jezik.
- Sljedeće: M2.6 izvoz u DaVinci (FCPXML).

## 2026-11-25 23:30 — M2.6 izvoz u DaVinci (FCPXML)
- Živa specifikacija pročitana: bez promjena. Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `davinci.py`; `render.py` uz svaki video sam napiše `reel_vN.fcpxml` (uz `reel_vN.srt`). FCPXML 1.10 za DaVinci Resolve 18+ (i besplatni): File > Import > Timeline, pa File > Import > Subtitle. Timeline koristi **originalne snimke** s istim rezovima (rez preko spoja dva klipa → dva kadra), stvarni broj sličica svake snimke (29,97 / 30) i vremenski kod, isto kadriranje (vodoravna snimka popuni 9:16 i pomakne se kao `--crop-x`), zumove kao Zoom, glazbu na zasebnoj traci (glasnoća izmjerena kao u renderu) i oznake (stil, naslov, zumovi). Zvuk i boja neobrađeni. `brzina` ide kao timeMap.
- `prepare.py` sada pamti kadriranje po klipu u `project.json`. Ako originala više nema, timeline koristi `source.mp4`; `--izvor priprema` to bira ručno. `davinci.py --verzija N / --trenutno / --ispis`. Odluka i izvori u ODLUKE.md. Verzija 0.13.0.
- Provjera (DaVinci nemam): XML valjan po Appleovu DTD-u 1.10; kadrovi = rezovi iz rendera (±1 sličica), ukupno = trajanje videa; slika i zvuk složeni iz originala po XML-u jednaki su Shofeovim (zvuk korelacija > 0,8; slika razlika < 2/255, krivi smjer pomaka bi dao 125/255). Očima: kadrovi iz originala po XML-u uz Shofeove kadrove na 3,5 s (vodoravni klip, crop-x 0.3, zum 116 %) i 9 s — isti izrez, Shofeov ima samo toplu boju i titlove.
- Usput otkriveno: zvuk u `source.mp4` kasni ~21 ms za originalom (AAC u pripremi); u DaVinciju je sinkronizacija čak točnija. Nije vidljivo, ali zabilježeno.
- Testovi: novi `tests/test_davinci.py` (6). Lokalno 181 prošlo, 3 preskočena (prije DTD testova). `lxml` dodan u requirements-dev.
- Za Marka (na pregledu M2): otvori `reel_vN.fcpxml` u DaVinciju — jedina nesigurnost je kadriranje vodoravnih snimki (mjerna jedinica pozicije u FCPXML-u nije službeno opisana); ako je krivo, `--izvor priprema` uvijek radi.
- Sljedeće: M2.7 Pregled M2 (demo + issue).

## 2026-11-26 00:40 — M2.7 pregled M2 (demo + issue)
- Živa specifikacija pročitana: bez promjena u zahtjevima (samo procjena trajanja i rečenica o tjednoj probi na laptopu). Issue #7 (Pregled M1) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `tests/make_demo_m2.py` napravi demo u `demo/` iz probnog reela „SF klima" (2 klipa, espeak glas, na slici vremenski kod izvornog klipa): `M2_naredbe.mp4` (88 s, 5,3 MB: automatski plan → „zadrži drugi pokušaj uvoda + izreži dio o cijeni" → „makni od 0:10,5 do 0:13,8" → „skrati na 20 s, filter ostaje"; prije svakog koraka kartica s naredbom, odgovorom alata i trajanjem), `M2_engleski.mp4` (zadnja verzija + engleski SRT), `M2_verzije.png` (popis verzija, usporedba, Claudeove ocjene misli), `M2_davinci.png` (timeline nacrtan iz `reel_v4.fcpxml`: 7 kadrova iz originala, vremenski kod, zumovi, glazba, oznake).
- Stari M1 demo maknut iz `demo/` (ostaje u povijesti, poveznica u `demo/README.md`); issue #7 sada pokazuje na tu trajnu poveznicu.
- Provjera očima: kartice, kadrovi svake verzije (vremenski kod izvornog klipa vidljivo skače na mjestima rezova), engleski titlovi točno uz govor, slika timelinea.
- Proizvod nepromijenjen (verzija ostaje 0.13.0). Testovi: novi `tests/test_demo_m2.py` (3); lokalno 184 prošlo, 3 preskočena.
- Za Marka: issue „Pregled M2" — pravi reel s naredbama (cilj 9 od 10 naredbi po sadržaju), titlovi (≤ 2 ispravka), DaVinci uvoz; i dalje otvoreno iz #7 (dulja snimka, testne snimke, laptop).
- Sljedeće: M3.1 kandidati za isječke.

## 2026-11-26 02:30 — M3.1 kandidati za isječke
- Živa specifikacija pročitana: bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `isjecci.py` → `isjecci.json` + `isjecci.txt`. Shofe isproba svaki niz cijelih misli od 20–60 s (trajanje kad se izrežu pauze), ocijeni ga 0–10 (početak, zaokruženost, sadržaj iz Claudeovih trenutaka, energija; 25–45 s idealno) i predloži 10 najboljih bez preklapanja. Isječak nikad ne počinje rečenicom kojoj treba ona prije („A…", „To…", „Zato…"), a gubi bodove za pozdrav/odjavu, dugu stanku ili promjenu teme u sredini i misao koja se nastavlja iza kraja.
- Claude zatim ocijeni svaki kandidat (1–10 + jedna rečenica zašto, naslov i hook za dobre), može pomaknuti granice citatom (`dodaj --umjesto K3`) ili dodati svoj; `provjeri` poreda po Claudeovoj ocjeni i javi što fali. Marko: `odobri`, `odbaci` (s napomenom), `vrati`, `novi` (još kandidata bez preklapanja s postojećima i odbačenima). SKILL.md i README dopunjeni; render odabranih isječaka u 9:16 je M3.2–M3.3 (do tada SKILL.md opisuje ručni put preko `uredi.py zadrzi` + `render.py --izlaz`). Odluka i izvori (Spotify, PodReels, OpusClip) u ODLUKE.md. Verzija 0.14.0.
- Provjera: izmišljeni dio epizode Sunčani4M (8 blokova: 4 prirodna isječka, čavrljanje, lutanje, nedovršena priča, odjava) → predložena točno 4 dobra bloka, svaki cijeli od prve do zadnje rečenice, s temama iz analize i bez njih; svi nizovi iz loših blokova ≥ 2,5 boda ispod najboljeg. Sat snimke: ~5 600 nizova ocijenjeno za ~2 s.
- Testovi: novi `tests/test_isjecci.py` (14). Lokalno 198 prošlo, 3 preskočena (prije dodavanja dokumentacije; isjecci + verzija ponovno prošli nakon).
- Za Marka: ništa sad. Kad budeš imao dulju snimku (vidi #7), reci „napravi isječke iz ove epizode" i javi koliko od 10 bi objavio — to je cilj iz specifikacije (≥ 5).
- Sljedeće: M3.2 kadar 9:16 prati govornika (detekcija lica).

## 2026-11-26 04:40 — M3.2 kadar 9:16 prati govornika
- Živa specifikacija pročitana: bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `kadar.py`. Za vodoravnu snimku u 9:16 (i 4:5, 1:1) Shofe nađe lica u originalnim klipovima (YuNet u OpenCV-u, na procesoru), iz `govornici.json` i pokreta usana zaključi tko kada govori i ponovno složi `source.mp4` s kadrom koji prati govornika (ffmpeg `sendcmd` mijenja crop po sličici). Vremena se ne mijenjaju, pa transkript, govornici, analiza i edit.json ostaju valjani. Bez govornika radi samo po usnama.
- Ponašanje: na drugog govornika rez (ne švenk), kadar najmanje 1,5 s, rez 0,15 s prije prve riječi, kamera miruje dok se lice samo njiše, a ide glatko za licem kad se osoba pomakne; glas izvan kadra ne mijenja kadar; bez lica ostaje `--crop-x`. `--analiza` (samo kadar.json), `--vrati` (natrag na nepomični kadar). DaVinci timeline dobije rez na svakoj promjeni osobe, svaki dio sa svojim položajem.
- `prepare.py`: priprema klipa i spajanje izdvojeni u `norm_clip`/`concat` (koristi ih i kadar.py). `doctor.py` provjerava OpenCV. Nova ovisnost opencv-python-headless (Apache-2.0); model YuNet (MIT, 230 kB) u `shofe-montaza/models/`. Odluka i izvori u ODLUKE.md. Verzija 0.15.0.
- Provjera očima: sintetski razgovor dvije nacrtane osobe (A lijevo, B desno, usta po stvarnom glasu, glas C izvan kadra) → kadrovi na 2 / 7 / 11 / 16,7 / 21,3 / 26 s pokazuju A, B, A, B, B (C govori, kadar ostaje), A; lice na sredini 9:16.
- Testovi: novi `tests/test_kadar.py` (9: kadrovi i rupe, crop iz položaja lica, naredbe za ffmpeg bez švenka na rezu, spajanje govornika i usana, miruje/prati, cijeli put s govornicima i samo s usnama, DaVinci slika iz originala = source.mp4, `--vrati`, uspravni klip i klip bez lica) + `tests/make_kadar_klip.py`.
- Za Marka: ništa sad. Kad pošalješ vodoravnu snimku razgovora (vidi #7), reci „napravi reel 9:16, kadar neka prati onoga tko priča" i javi je li kadar ikad na krivoj osobi.
- Sljedeće: M3.3 render odabranih isječaka u seriji.

## 2026-11-26 06:40 — M3.3 render odabranih isječaka u seriji
- Živa specifikacija pročitana: bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `isjecci.py render` (+ `serija.py`). Svi odobreni isječci (ili `render K1,K3`) montiraju se jedan za drugim u `isjecci/K1_<naslov>.mp4` sa stilom, titlovima i Claudeovim hookom, uz `.srt`, `.fcpxml` (DaVinci) i `.edit.json`, plus `isjecci/pregled.png` (prva sekunda s hookom i sredina svakog isječka). Svaki isječak je kopija glavnog edit.json (ispravljena imena, poštapalice, ponovljeni pokušaji, stil, glazba) sa svime izvan isječka izrezanim; rezovi naredbama glavnog videa se ne prenose (javi se napomena). Glavni edit.json i verzije ostaju netaknuti.
- Po isječku: vlastiti `stil`, `naglasi`, `zoom`, `glazba`…, vlastiti `izrezi`; `--stil` za cijelu seriju, `--kadar 1,15` slike kadrova, `--brzo`, `--kvaliteta visoka`. Bez hooka = greška (osim `--bez-hooka`). Novi naslov → stari video tog isječka se zamijeni.
- `render.py` prepisan u funkciju `render(proj, edit, izlaz=…)` (naredbeni redak isti); izlaz smije biti u podmapi, FCPXML ide uz video. Odluka i izvori u ODLUKE.md. Verzija 0.16.0.
- Provjera očima: probna epizoda (testni video s brojačem sekundi) → K1/K2/K3 na `pregled.png` počinju točno na 16 / 143 / 115 s snimke, hook čitljiv na vrhu, titlovi dolje, K2 u stilu udarno. 3 isječka (75 s videa, 540×960) za 28 s.
- Testovi: novi `tests/test_serija.py` (5: rezovi i napomene isječka, imena datoteka, greške bez odobrenih/bez hooka/krivi stil, serija od 2 isječka — trajanje, titlovi = točno riječi isječka, glavni projekt netaknut — i promjena naslova + kadrovi).
- Za Marka: ništa sad. Kad budeš imao dulju snimku (vidi #7): „napravi isječke", odaberi, pa „napravi odabrane isječke" i pogledaj `isjecci/pregled.png`.
- Sljedeće: M3.4 tekstovi za objavu po mreži + naslovna sličica.


## 2026-11-26 09:00 — M3.4a tekstovi za objavu po mreži
- Živa specifikacija pročitana: bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- M3.4 podijeljen: M3.4a tekstovi (ovaj krug), M3.4b naslovna sličica (sljedeći).
- Novo: `objava.py`. Za reel koji gledaš (`reel_vN`), sve renderirane isječke ili `K1,K3` napravi `objava.json` s onim što se u videu stvarno čuje (iz `.srt`), hookom, naslovom i razlogom isječka. Claude piše poseban tekst za Instagram (prvi redak kao hook, korist, poziv, 3–5 hashtagova), TikTok (kraće, pitanje, ključne riječi) i YouTube (naslov ≤ ~60 znakova, kratki opis); Shofe provjeri pravila mreža (IG/TikTok najviše 5 hashtagova, duljine, YouTube bez < >, zamjenski tekst) i upozori na broj koji se ne čuje u videu, isti opis na dvije mreže, dug prvi redak, hashtag s kvačicama. Gotov tekst za kopiranje: `<video>.objava.txt` uz video + `objava.txt` u projektu. Uspravni video do 3 min → sve tri mreže (YouTube Short), 16:9 → samo YouTube; `--mreze` bira.
- Serije: `objava.py serija "SF klima" --hashtagovi … --potpis … --napomena …` pamti Markov potpis, do 3 stalna hashtaga i ton u `%LOCALAPPDATA%/Shofe` (vrijedi za sve projekte); `--serija` ih dodaje u projektu. `isjecci.py render` na kraju predloži tekstove. SKILL.md i README dopunjeni; odluka i izvori u ODLUKE.md. Verzija 0.17.0.
- Provjera: probni reel „čišćenje klime" (pravi render) + serija SF klima → tekstovi za sve tri mreže s potpisom i 5 hashtagova; upozorenje na „broj 2" nestalo nakon dodavanja rednih brojeva („Prvi korak… Drugi korak").
- Testovi: novi `tests/test_objava.py` (10). Lokalno 222 prošlo, 3 preskočena.
- Za Marka: kad objavljuješ, reci „napiši tekstove za objavu" i javi koliko si morao mijenjati (cilj: samo sitnice). Za svaku seriju (SF klima, Sunčani put, Sunčano AJMO!, Sunčani4M) reci jednom potpis i stalne hashtagove.
- Sljedeće: M3.4b naslovna sličica.

## 2026-11-26 10:10 — M3.4b naslovna sličica
- Živa specifikacija pročitana: bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `naslovna.py`. Za video koji gledaš, sve isječke ili `K1,K3` ocijeni kadrove gotovog videa svakih 0,5 s (iz `source.mp4`, bez titlova, s bojom stila): veličina i oštrina lica, otvorene oči (u odnosu na isto lice drugdje u videu), svjetlo, lice prema kameri, ne uz rub, + mali bonus u Claudeovim najjačim trenucima. Napravi uz video `…naslovna_9x16.jpg` (1080×1920; lice i tekst u sredini 3:4 koju Instagram pokazuje na profilu, tekst izvan gornjih 14 % i donjih 35 % gdje su gumbi), `…naslovna_16x9.jpg` (1280×720; iz originalne vodoravne snimke krupno lice osobe koju je pokazivao uspravni kadar, tekst sa strane; iz uspravne snimke osoba desno i mutna pozadina), `…naslovna_kandidati.jpg` (6 najboljih kadrova s ocjenom i razlogom) i `…naslovna_pregled.jpg`.
- Tekst piše Claude (2–5 riječi, `*riječ*` u boji isticanja stila, font stila); prijelom poštuje pravopis (jednoslovni prijedlog ne ostaje na kraju retka) i bira manje redaka ako su slova tek malo manja. `--kadar N`, `--vrijeme 0:12`, `--bez-teksta`; izbor kadra i tekst pamte se u `naslovna.json`. Upozorenja: dug tekst, tekst preko druge osobe, lice izvan 3:4, nema lica, zatvorene oči. `objava.py` u `.objava.txt` navodi sličice; `isjecci.py render` predlaže naslovne. SKILL.md (Claude mora pogledati pregled i kandidate) i README dopunjeni.
- Nova ovisnost Pillow (MIT-CMU), `doctor.py` je provjerava. `requirements-dev.txt` sad ima i OpenCV i Pillow: do sada CI nije instalirao OpenCV pa su se testovi kadra (M3.2) na GitHubu preskakali. Odluka i izvori u ODLUKE.md. Verzija 0.18.0.
- Provjera očima: probni uspravni klip (5 dijelova: malo lice, zatvorene oči, najbolje, mutno, tamno) → izabran kadar iz najboljeg dijela, kandidati s točnim razlozima; vodoravni razgovor dvije osobe → 16:9 krupno lice govornika, tekst „ŠTO RENAULT 4 KRIJE?" s druge strane, 9:16 tekst unutar 3:4.
- Testovi: novi `tests/test_naslovna.py` (10) + `tests/make_naslovna_klip.py`.
- Za Marka: kad imaš gotov reel, reci „napravi naslovnu sličicu" i javi bi li je objavio (ili koji kadar/tekst bi promijenio). Oči i izraz lica Shofe procjenjuje približno; Claude zato uvijek pogleda kandidate.
- Sljedeće: M3.5 Pregled M3 (demo + issue).

## 2026-11-26 13:40 — M3.5 Pregled M3 (demo + issue)
- Živa specifikacija pročitana (rev 13): bez promjena. Issues #7 i #18 (pregledi M1 i M2) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `tests/make_demo_m3.py` → `demo/`. Probna epizoda Sunčani4M (3 min iz `isjecci_razgovor.json`, dva nacrtana voditelja u vodoravnom kadru, dva sintetska glasa espeak-ng, usta po glasu, vrijeme snimke na slici) prolazi cijeli put M3 kao na laptopu: prepare 9:16 → govornici (iz scenarija, modeli nisu u sandboxu) → analiza + Claudeove teme i trenuci → `kadar.py` → `isjecci.py` → Claudeove ocjene → odobri K1–K3, odbaci K4 → `isjecci.py render` → serija Sunčani4M + `objava.py` → `naslovna.py`.
  - `M3_isjecci.mp4` (112 s, 4,5 MB): kandidati s ocjenama + tri gotova isječka (stilovi čisto, podcast, kino).
  - `M3_kadar.mp4` (29 s, 1,3 MB): vodoravna snimka s okvirom izreza uz gotov 9:16 kadar.
  - `M3_objava.png`: naslovne 9:16 i 16:9 + tekstovi za IG/TikTok/YouTube za K1; `M3_naslovna.jpg`: kandidati za naslovnu.
  - M2 demo maknut iz `demo/` (ostaje u povijesti, link u `demo/README.md`).
- Provjera očima: Shofe je predložio točno 4 dobra dijela epizode (čavrljanje, lutanje, nedovršena priča i odjava nisu predloženi); svaki isječak od prve do zadnje rečenice; kadar.py napravio 21 kadar, svaki na govorniku iz scenarija (pogledano očima na 5 mjesta: lice na sredini, rez bez švenka); naslovne s licem i tekstom u sigurnoj zoni; tekstovi s potpisom serije i ≤ 5 hashtagova.
- Primijećeno: stil Udarno stavlja riječ u sredinu kadra, a kod uspravnog kadra lica to je točno preko usta → dodano u M5.8 (riječ ispod lica kad kadar.py zna gdje je lice). Za demo isječak K1 zato u stilu Čisto.
- Testovi: novi `tests/test_demo_m3.py` (4: Claudeove ocjene pokrivaju sve dijelove epizode, tekstovi po pravilima mreža, okviri izreza, vrijeme). Lokalno 236 prošlo, 3 preskočena.
- Za Marka: issue „Pregled M3" — demo, instalacija 0.18.0, isječci iz prave epizode, tekstovi i naslovne. Najvažnije: koliko od 10 predloženih isječaka bi objavio (cilj ≥ 5) i je li kadar ikad na krivoj osobi.
- Sljedeće: M4.1 sinkronizacija više izvora po zvuku.

## 2026-11-26 14:30 — M4.1 sinkronizacija više izvora po zvuku
- Živa specifikacija pročitana (rev 13): bez promjena. Issues #7, #18 i #25 (pregledi M1–M3) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `sinkro.py`. Mapa epizode (2–3 kamere + možda zasebni zvuk) → `sinkro.json`: za svaki izvor `pomak` (gdje mu je 0 s na crti glavnog izvora; negativno = krenuo prije), `brzina` (drift sata kamere), `od`/`do` na crti, sigurnost. Glavni = zasebni zvuk (inače najdulji video), `--glavni` bira drugi. Uz to `sinkro.txt`, `sinkro.png` (glasnoća svih izvora na zajedničkoj crti) i `sinkro_provjera.mp4` (10 s mozaik svih kamera sa zvukom glavnog, uz svaku sliku vrijeme u datoteci; `--provjera 12:30` za drugi trenutak). Snimka koja nije iz iste epizode → „nije pronađen" + upute; ručno `--pomak ime=s`.
- Kako: ovojnica glasnoće cijele snimke (grubo, FFT korelacija) → GCC-PHAT u 3–16 prozora od 8 s (fino, < 1 ms) → pravac kroz prozore = pomak + drift. Zvuk se čita u vremenu datoteke (`first_pts=0`), pa ni zvuk koji kamera počne snimati iza slike ni AAC kašnjenje ne kvare sinkronizaciju. Bez novih ovisnosti. Odluka i izvori u ODLUKE.md. Verzija 0.19.0.
- Provjera: probna epizoda (`tests/make_sinkro.py`: zasebni zvuk 110 s, kamera 1 krenula 7,3 s prije, mutni mikrofon s jekom; kamera 2 krenula 9,6 s poslije, „mobitel" zvuk, sat +150 ppm, zvuk 0,2 s iza slike; nepovezani žamor) → pomaci točni na < 1 ms, drift 148 ppm, žamor „nije pronađen"; na `sinkro.png` vrhovi se poklapaju; u mozaiku obje kamere bljesnu u istoj sličici kad se čuje pljesak. Sintetska snimka od 60 min: pomak < 1 ms, drift 80 i −300 ppm točno, ~1–2 s računanja po izvoru.
- Testovi: novi `tests/test_sinkro.py` (12: pomak −10…+10 s, drift, nepovezan i prekratak izvor, kratki isječak usred snimke, preračun vremena, cijeli put s mozaikom, drugi glavni + ručni pomak, greške).
- Za Marka: kad snimiš epizodu, daj Claudeu mapu sa svim snimkama i reci „sinkroniziraj kamere i zvuk"; pogledaj `sinkro_provjera.mp4` (usne prate glas?). Koje kamere i mikrofon koristiš u Renaultu 4 i dolazi li zvuk zasebno, još je otvoreno pitanje (SPEC); zadano: 2–3 videa + možda zasebni zvuk.
- Sljedeće: M4.2 tko govori → koja kamera.

## 2026-11-26 17:14 — M4.2 tko govori → koja kamera (režija podcasta)
- Živa specifikacija pročitana (rev 13): bez promjena. Issues #7, #18 i #25 (pregledi M1–M3) još bez Markova odgovora; otvorenih PR-ova nema.
- Novo: `rezija.py` (nakon `sinkro.py`, u istom projektu). Prvo pokretanje složi `source.mp4` cijele epizode u širokom kadru sa zvukom glavnog izvora (16:9, 30 fps) + `project.json` → transcribe.py i govornici.py rade na tom projektu → drugo pokretanje: u 8 prozora po kameri YuNet nađe lica i po usnama prepozna tko je na kojoj kameri (jedno lice = krupni kadar te osobe, dvoje+ = široki kadar), pa montira program kao režiser i ponovno složi `source.mp4`. Vrijeme se ne mijenja pa transkript, govornici i edit.json vrijede; dalje je to običan projekt (render, titlovi, isječci).
- Pravila: krupni kadar onoga tko govori (rez 0,2 s prije prve riječi); široki kadar kad dvoje pričaju u isti glas, kod brze izmjene, za gosta bez svoje kamere i nakon 3 s tišine; kadar ≥ 2 s; u monologu umetak širokog kadra svakih 30 s (`--umetci nikad|rijetko|povremeno|cesto`); kamera koja ne snima se ne bira; uspravni mobitel se reže oko lica. Ručno `--kamere "kamera1.mp4=Marko,kamera3.mp4=siroki"` (pamti se), `--min-kadar`, `--analiza`. Uz to `rezija.txt` i `rezija.png` (sličice kamera s ulogom, tko kad govori, traka programa u bojama kamera). Odluka i izvori u ODLUKE.md. Verzija 0.20.0.
- Provjera očima: probna epizoda (`tests/make_rezija.py`: zasebni zvuk, široka kamera s dvoje, krupni A, krupni B s uspravnog mobitela koji se gasi na 45 s, gost C izvan kadra) → uloge točne, 13 kadrova, svaka rečenica na pravoj kameri, C i kraj B (kamera ugašena) u širokom kadru; na `rezija.png` i sličicama iz `source.mp4` boje kamera odgovaraju.
- Testovi: novi `tests/test_rezija.py` (11: izmjena govornika i najkraći kadar, preklapanje i brza izmjena, umetci, bez širokog kadra, gost/tišina/kamera koja ne snima, bez govornika i crno, ručne kamere, prozori, cijeli put s tri kamere i bojama u gotovom videu, ručno + samo analiza).
- Novi zadatak M4.2b: DaVinci timeline podcasta s originalnim kamerama i isječci 9:16 iz krupnih kadrova (sad DaVinci dobije gotov program, a isječci se rade iz 16:9 programa).
- Za Marka: kad snimiš epizodu: „sinkroniziraj kamere i zvuk", pa „montiraj epizodu, kamera neka prati onoga tko priča". Javi je li ikad kamera na krivoj osobi i odgovara li ti koliko često uskače široki kadar.
- Sljedeće: M4.2b podcast u DaVinci s originalnim kamerama + isječci iz krupnih kadrova.

## 2026-11-26 18:27 — M4.2b1 DaVinci timeline podcasta s originalnim kamerama
- Živa specifikacija pročitana (rev 13): bez promjena. Issues #7, #18 i #25 (pregledi M1–M3) još bez Markova odgovora; otvorenih PR-ova nema.
- M4.2b podijeljen: M4.2b1 DaVinci timeline (ovaj krug), M4.2b2 isječci 9:16 iz krupnih kadrova originalnih kamera (sljedeći).
- Novo u `davinci.py`: za podcast projekt (`rezija.py`) timeline više nije `source.mp4` nego originalne kamere. V1 = program kakav je Shofe montirao, kadar po kadar iz originalne kamere (vrijeme iz `sinkro.json` za svaki kadar posebno, pa i drift sata; isti izrez, i za uspravni mobitel; zumovi stila; bez zvuka kamere). Iznad svakog kadra ostale kamere u istom trenutku, svaka uvijek na svojoj traci, **isključene** — u DaVinciju klik + D i kamera je promijenjena. Ispod zvuk glavnog snimača (uloga dialogue), glazba traku niže. Bez `sinkro.json`/`rezija.json` ili bez neke snimke → `source.mp4` kao prije, s napomenom. Radi sam uz svaki render. Pravi multicam (mc-clip) namjerno ne: DaVinci ga iz FCPXML-a ne uvozi pouzdano (ODLUKE.md). Usput: 15 fps snimke više nisu u FCPXML-u opisane kao 30 fps. Verzija 0.21.0.
- Provjera: probna epizoda (zasebni zvuk + široka + krupni A + uspravni mobitel B koji se gasi na 45 s) → FCPXML prolazi Appleov DTD; slika složena iz originala po FCPXML-u = Shofeov program (pogledano očima na 6 kadrova, razlika najviše 1 sličica kamere od 15 fps); zvuk na traci ispod = zvuk programa; kamera B nakon 45 s nije ni u programu ni iznad.
- Testovi: novi `tests/test_davinci_podcast.py` (4: valjan XML i trake, ista slika i zvuk kao program, kamera koja ne snima + nestali original + `--izvor priprema`, dijeljenje reza na promjeni kamere bez videa).
- Za Marka: kad otvoriš epizodu u DaVinciju (File > Import > Timeline), javi jesu li kamere na trakama iznad sive (isključene) i čuje li se samo glavni zvuk. To ne mogu provjeriti bez pravog DaVincija.
- Sljedeće: M4.2b2 isječci 9:16 iz podcasta iz krupnih kadrova kamera.
