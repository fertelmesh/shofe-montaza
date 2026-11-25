# ROADMAP

Agent uzima prvi neodrađeni zadatak odozgo. Oznake: `[čeka Marka]`, `[blokirano: razlog]`. Prevelik zadatak → podijeli ga ovdje na podzadatke.
Markovi zahtjevi iz GitHub issues idu na vrh, u odjeljak „Hitno".

## Hitno (Markovi zahtjevi)

(prazno)

## M1 Temelj

- [x] M1.1 Shofe v1: prepare, transcribe, plan, render, 5 stilova, glazba, hook, 4 formata
- [x] M1.2 pytest testovi + probne snimke (sintetski govor, mock transkript)
- [x] M1.3 CI: GitHub Actions na Linuxu i Windowsu (pytest) + dimni test prave transkripcije (whisper tiny); popraviti sve što na Windowsu padne (#1)
- [x] M1.4 `requirements.txt` za proizvod, `VERSION`, verzija u `doctor.py`; install.ps1 instalira iz `requirements.txt` (#2)
- [x] M1.5 Karta videa v1: `analyze.py` → `analiza.json` (tišine, glasnoća po odsječku, tempo govora, mutni/tamni kadrovi, promjene scene); SKILL.md: Claude iz transkripta dopisuje teme i najjače trenutke (#3)
- [x] M1.6 Govornici (diarizacija) na CPU-u, permisivna licenca; istraži opcije, zapiši u ODLUKE.md; test na sintetskom dvoglasju (#4)
- [x] M1.7 Pregled karte videa kao jedna lokalna HTML stranica (teme, govornici, trenuci, tišine na vremenskoj crti) (#5)
- [x] M1.8 Pregled M1: demo + issue za Marka (#6)

## M2 Montaža po naredbi

- [x] M2.1 `uredi.py`: naredbe po vremenu u vremenu gotovog videa („makni 1:20–1:45", „zadrži samo 0:10–0:40") → izmjene edit.json (#9)
- [x] M2.2 Naredbe po sadržaju: Claude u transkriptu nađe dio, alat ga izreže/zadrži po riječima; testni skup od 10 naredbi s očekivanim rezultatom (#PR)
- [ ] M2.3 „Skrati na N sekundi": rangiranje odsječaka po važnosti, zadržava zaokružene misli
- [ ] M2.4 Verzije: popis verzija, „vrati verziju N", usporedba što se promijenilo
- [ ] M2.5 Titlovi: izvoz SRT (i VTT), rječnik se sam nadopunjuje iz Markovih ispravaka, engleski prijevod (opcija)
- [ ] M2.6 Izvoz u DaVinci: FCPXML timeline s originalnim klipovima i istim rezovima + SRT; validacija XML-a u testu; upute u README
- [ ] M2.7 Pregled M2: demo + issue

## M3 Isječci za mreže

- [ ] M3.1 Kandidati za isječke iz dulje snimke: heuristike (jak početak, zaokružena misao, 20–60 s) + Claudeova ocjena → `isjecci.json` s ocjenom i razlogom
- [ ] M3.2 Kadar 9:16 prati govornika: detekcija lica (permisivna licenca), zaglađeni pomak, test na vodoravnom klipu s dvije osobe
- [ ] M3.3 Render odabranih isječaka u seriji, svaki sa stilom, titlovima i hookom
- [ ] M3.4 Tekstovi za objavu po mreži + naslovna sličica (kadar + tekst)
- [ ] M3.5 Pregled M3: demo + issue

## M4 Podcast Sunčani4M

- [ ] M4.1 Sinkronizacija više izvora po zvuku (unakrsna korelacija), test sa sintetskim pomakom ±10 s
- [ ] M4.2 Tko govori → koja kamera; pravila (najkraći kadar, široki kadar kad pričaju svi)
- [ ] M4.3 Nastupi bendova: prepoznavanje glazbe, nikad ne rezati unutar pjesme, mix za glazbu
- [ ] M4.4 Intro/outro/špice, poglavlja za YouTube, MP3 za podcast platforme (−16 LUFS), opis epizode
- [ ] M4.5 Pregled M4: demo + issue

## M5 Efekti i grafika (vidi EFEKTI.md)

- [ ] M5.1 Sustav efekata u edit.json (`efekti: [{tip, od, do, parametri}]`) + ffmpeg efekti: zumovi (guranje, trzaj, pad, vertigo), zamrzni + oznaka, film/retro
- [ ] M5.2 Prijelazi (iris, rolete, vrata…) i CC0 zvučni efekti s pravilima glasnoće
- [ ] M5.3 Claude bira efekte po tekstu: pravila u SKILL.md + `efekti.py predlozi`
- [ ] M5.4 HyperFrames integracija: render odsječka s pozadinskim videom i umetanje natrag; provjera na Windowsu u CI-ju
- [ ] M5.5 10 HTML predložaka (kartica, ključna rečenica, brojač, graf, popis, prije/poslije, komentar, mobitel, citat, poziv na akciju)
- [ ] M5.6 Galerija efekata (jedan render sa svim efektima)
- [ ] M5.7 Izdvajanje osobe (permisivni model): tekst iza osobe, zamjena pozadine, klon
- [ ] M5.8 Novi stilovi montaže i titlova + „stil iz uzorka"
- [ ] M5.9 Pregled M5: demo + issue

## M6 Sučelje i objava

- [ ] M6.1 Lokalna stranica: projekti, pregled videa s valnim oblikom i tišinama, kartice isječaka (odobri/odbij), naredbe
- [ ] M6.2 Objava i zakazivanje `[čeka Marka]`: samo uz Markovo izričito odobrenje za svaku uslugu
