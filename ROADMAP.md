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
- [x] M2.2 Naredbe po sadržaju: Claude u transkriptu nađe dio, alat ga izreže/zadrži po riječima; testni skup od 10 naredbi s očekivanim rezultatom (#10)
- [x] M2.3 „Skrati na N sekundi": rangiranje odsječaka po važnosti, zadržava zaokružene misli (#11)
- [x] M2.4 Verzije: popis verzija, „vrati verziju N", usporedba što se promijenilo (#12)
- M2.5 Titlovi (podijeljeno):
  - [x] M2.5a Izvoz SRT (uz svaki render) i VTT: fraze, 2 × 42 znaka, 0,83–7 s, ispravljeni tekst, vrijeme gotovog videa (#13)
  - [x] M2.5b Rječnik se sam nadopunjuje iz Markovih/Claudeovih ispravaka teksta (edit.json `tekst` vs transkript) (#14)
  - [x] M2.5c Engleski prijevod titlova (opcija): Claude prevodi po titlovima, `reel_vN.en.srt` (#15)
- [x] M2.6 Izvoz u DaVinci: FCPXML timeline s originalnim klipovima i istim rezovima + SRT; validacija XML-a u testu; upute u README (#16)
- [x] M2.7 Pregled M2: demo + issue (#17)

## M3 Isječci za mreže

- [x] M3.1 Kandidati za isječke iz dulje snimke: heuristike (jak početak, zaokružena misao, 20–60 s) + Claudeova ocjena → `isjecci.json` s ocjenom i razlogom (#19)
- [x] M3.2 Kadar 9:16 prati govornika: detekcija lica (permisivna licenca), zaglađeni pomak, test na vodoravnom klipu s dvije osobe (#20)
- [x] M3.3 Render odabranih isječaka u seriji, svaki sa stilom, titlovima i hookom (#21)
- M3.4 Tekstovi za objavu po mreži + naslovna sličica (podijeljeno):
  - [x] M3.4a Tekstovi za objavu: naslov, opis i hashtagovi posebno za Instagram, TikTok i YouTube, provjera pravila mreža, serije s potpisom (#22)
  - [x] M3.4b Naslovna sličica: najbolji kadar (lice, oštrina, otvorene oči) + tekst, 9:16 (sigurna zona 3:4 za Instagram mrežu) i 16:9 za YouTube (#23)
- [x] M3.5 Pregled M3: demo + issue (#24)

## M4 Podcast Sunčani4M

- [x] M4.1 Sinkronizacija više izvora po zvuku (unakrsna korelacija), test sa sintetskim pomakom ±10 s (#26)
- [x] M4.2 Tko govori → koja kamera; pravila (najkraći kadar, široki kadar kad pričaju svi) (#27)
- M4.2b Podcast dalje (podijeljeno):
  - [x] M4.2b1 DaVinci timeline podcasta: program iz originalnih kamera, ostale kamere na trakama iznad (isključene), glavni zvuk ispod (#28)
  - [x] M4.2b2 Isječci 9:16 iz podcasta: iz krupnih kadrova originalnih kamera (ne iz 16:9 programa), široki kadar → izrez po govorniku, podijeljen kadar za dvoje (#29)
  - M4.2b3 Uspravni isječci podcasta, dorada (podijeljeno):
    - [x] M4.2b3a Titlovi na spoju podijeljenog kadra; naslovna sličica uspravnog isječka iz kamere govornika (9:16 iz uspravnog izvora, radije jedno lice; 16:9 iz originalne kamere te osobe) (#32)
    - [x] M4.2b3b DaVinci 9:16 timeline uspravnog isječka iz originalnih kamera (sad iz uspravnog izvora): izrez po kadru, podijeljen kadar kao dvije trake (transform) (#33)
- M4.3 Nastupi bendova (podijeljeno):
  - [x] M4.3a Prepoznavanje pjesama (`nastupi.py`), pjesma kao nedjeljiv komad u plan/render/uredi/skrati/isječcima, bez titlova, glazbeni lanac zvuka umjesto govornog, pozadinska glazba šuti (#31)
  - M4.3b Pjesma dalje (podijeljeno):
    - [x] M4.3b1 Glasnoća pjesme naspram govora: mjerenje po dijelu (EBU R128), stalno pojačanje pjesme, video −14 LUFS bez dinamičkog loudnorma, `nastupi.py glasnoca` (#34)
    - [x] M4.3b2 Režija za vrijeme pjesme (široki kadar, sporiji rezovi na takt, `ritam.py`) + oznake pjesama u DaVinciju (marker + zvuk pjesme na vlastitoj traci) (#35)
    - [x] M4.3b3 Pjesme u pregled.html + isječak iz pjesme (najbolji refren 30–60 s) (#39)
    - [x] M4.3b4 Uspravni (9:16) isječak pjesme iz podcasta: režija u ritmu (bend/široki kadar izrezan, rez na takt) umjesto praćenja „govornika" za vrijeme pjevanja (#40)
- M4.4 Epizoda do kraja (podijeljeno):
  - [x] M4.4a Poglavlja za YouTube (teme + pjesme u vremenu gotovog videa, pravila YouTubea) + MP3 za podcast platforme (−16 LUFS, ID3 poglavlja) (#41)
  - [x] M4.4b Opis epizode: YouTube opis s poglavljima i tekst za podcast platforme (`objava.py` za epizodu) (#42)
  - [x] M4.4c Intro/outro/špice (Markove datoteke ili generirana špica), poglavlja i MP3 se pomaknu za intro (#43)
  - [x] M4.4d Poglavlja kao oznake u DaVinci timelineu (FCPXML chapter-marker + EDL sa zelenim oznakama za „Chapters from Markers") + špice u DaVinci timelineu (uvodna iza najave, odjavna) (#45)
- [x] M4.5 Pregled M4: demo + issue (uključiti provjeru u DaVinciju: špica na mjestu, uvoz `reel_vN.poglavlja.edl`, Deliver „Chapters from Markers") (#47)

## M5 Efekti i grafika (vidi EFEKTI.md)

- [x] M5.1 Sustav efekata u edit.json (`efekti: [{tip, od, do, parametri}]`) + ffmpeg efekti: zumovi (guranje, trzaj, pad, vertigo), zamrzni + oznaka, film/retro (#48)
- M5.2 Prijelazi i zvučni efekti (podijeljeno):
  - [x] M5.2a Prijelazi na rezovima: iris (oko lica), rolete, vrata, brisanje, klizanje, zamah, pretapanje, kroz crno/bijelo, prolaz, pikseli; centrirani na rezu s ručkama, trajanje videa isto; `efekti.py rezovi` (#49)
  - [x] M5.2b Zvučni efekti (vlastita biblioteka, CC0) s pravilima glasnoće: zvuk uz prijelaze, trzaj, zamrzni, vertigo, film; samostalan zvuk; nikad glasniji od glasa (#PR)
  - [ ] M5.2c Prijelazi dalje: manje memorije po prijelazu (~0,3 GB kod 1080×1920), prijelazi u DaVinci timelineu (FCPXML transition, ako ih Resolve uvozi)
- [ ] M5.3 Claude bira efekte po tekstu: pravila u SKILL.md + `efekti.py predlozi`
- [ ] M5.4 HyperFrames integracija: render odsječka s pozadinskim videom i umetanje natrag; provjera na Windowsu u CI-ju
- [ ] M5.5 10 HTML predložaka (kartica, ključna rečenica, brojač, graf, popis, prije/poslije, komentar, mobitel, citat, poziv na akciju)
- [ ] M5.6 Galerija efekata (jedan render sa svim efektima)
- [ ] M5.7 Izdvajanje osobe (permisivni model): tekst iza osobe, zamjena pozadine, klon
- [ ] M5.8 Novi stilovi montaže i titlova + „stil iz uzorka"; titlovi stila Udarno (riječ u sredini kadra) ne smiju prekriti usta — kad je lice u sredini, riječ ide ispod lica (primijećeno u demu M3)
- [ ] M5.9 Pregled M5: demo + issue

## M6 Sučelje i objava

- [ ] M6.1 Lokalna stranica: projekti, pregled videa s valnim oblikom i tišinama, kartice isječaka (odobri/odbij), naredbe
- [ ] M6.2 Objava i zakazivanje `[čeka Marka]`: samo uz Markovo izričito odobrenje za svaku uslugu
