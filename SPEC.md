# Shofe — specifikacija aplikacije

Živa verzija (Marko je može mijenjati, njegove izmjene imaju prednost): https://claude.ai/artifact/3B2YyRJL3v9jnydfsvAaSr
Plan efekata: `EFEKTI.md` i https://claude.ai/artifact/9KmeLGipJyisdkUQqCEU85

## Cilj

Shofe je jedan alat koji od sirove snimke napravi gotov sadržaj za objavu: Marko snima i kaže što želi, a Shofe analizira, montira, titluje, dodaje efekte i reže isječke za mreže. Sve radi na Markovom Windows računalu, a zapovijeda se običnim riječima na hrvatskom (kroz Claude, kasnije i kroz lokalno sučelje).

Za što se koristi:

- **Reelovi:** SF klima savjeti, Sunčani put, Sunčano AJMO!, osobni reelovi.
- **Sunčani4M podcast:** cijela epizoda iz više kamera snimljenih u Renaultu 4, uključujući nastupe bendova u autu.
- **Isječci:** 5–10 kratkih videa za Instagram, TikTok i YouTube Shorts iz svake epizode ili duljeg videa.
- **Dulji YouTube videi** u 16:9.

## Put snimke

Snimke (mobitel, Insta360 izvoz, kamere, zasebni zvuk) → 1 Uvoz i priprema → 2 Analiza videa → jedan od tri izlaza:
- Reel ili YouTube video (3 montaža po naredbi, 4 titlovi, 5 efekti)
- Podcast Sunčani4M (6, plus 4 i 5)
- Isječci za mreže (7, plus 3, 4, 5)

→ 8 Tekstovi i naslovna slika → 9 Objava (kasnije). Uz svaki gotov video: 10 Izvoz u DaVinci.

Analiza je temelj: montaža po naredbi, podcast i isječci rade samo onoliko dobro koliko Shofe razumije što se u videu govori i tko govori.

## Moduli

Svaki modul ima kriterij „Gotovo kad". Modul je gotov tek kad to vrijedi na testnim snimkama. Brojke su ciljevi.

### 1. Uvoz i priprema
- Radi: klipovi s mobitela, izvezeni Insta360 videi, kamere i zasebni zvuk; okretanje, HDR u obične boje, kadriranje, spajanje.
- Gotovo kad: svaki testni klip učita se bez ručnog rada.

### 2. Analiza videa
- Radi: transkript s vremenom svake riječi, tko govori, teme s vremenima, najjači trenuci (hook, poanta, smijeh), tišine, mutni ili loši kadrovi, razina zvuka.
- Rezultat je „karta videa" koju čita Claude, a Marko vidi kao pregledni popis.
- Gotovo kad: za epizodu od 60 min karta je gotova za najviše 20 min, a govornik je točan u 9 od 10 rečenica.

### 3. Montaža po naredbi
- Radi: automatski makne pauze, poluglasove i ponovljene pokušaje; izvršava naredbe po sadržaju i po vremenu: „izreži dio gdje pričam o cijeni", „makni od 1:20 do 1:45", „skrati na 60 sekundi", „zadrži drugi pokušaj".
- Svaka promjena je nova verzija; „vrati kako je bilo" uvijek radi.
- Gotovo kad: 9 od 10 naredbi po sadržaju pogodi pravi dio na testnim snimkama.

### 4. Titlovi
- Radi: stilovi, karaoke, naglasci, ispravci pravopisa i imena preko rječnika; SRT datoteka za YouTube; po želji engleski prijevod.
- Gotovo kad: na testnom reelu Marko ispravlja najviše 2 riječi.

### 5. Efekti i grafika
- Radi prema `EFEKTI.md`: zumovi, prijelazi, zvučni efekti, HTML grafika, izdvajanje osobe.
- Gotovo kad: galerija efekata prođe Markov pregled.

### 6. Podcast (Sunčani4M)
- Radi: sinkronizira više kamera i zasebni zvuk po zvuku; prebacuje kadar na onoga tko govori, a široki kadar kad pričaju svi; dodaje intro, outro i špice; složi poglavlja za YouTube; zasebna audio verzija (MP3) za podcast platforme.
- Nastupi bendova: pjesma se nikad ne reže po pauzama, zadržava se cijela izvedba, a zvuk se namješta za glazbu, ne za govor.
- Gotovo kad: epizoda od sat vremena iz 3 izvora postane gotova 16:9 epizoda + MP3 + poglavlja bez ručne sinkronizacije.

### 7. Isječci za mreže
- Radi: iz dulje snimke predloži 5–10 isječaka od 20–60 s, svaki s jakim početkom i zaokruženom mišlju, s ocjenom i jednom rečenicom zašto; kadriranje 9:16 prati onoga tko govori; svaki dobije stil, titlove i hook.
- Marko bira koje želi; ostale odbacuje ili traži nove.
- Gotovo kad: od 10 prijedloga barem 5 bi objavio bez izmjena.

### 8. Tekstovi i naslovna slika
- Radi: naslov, opis i hashtagove posebno za Instagram, TikTok i YouTube; naslovnu sličicu iz najboljeg kadra s tekstom.
- Gotovo kad: tekstove objavljuje uz najviše sitne izmjene.

### 9. Objavljivanje (kasnije)
- Radi: objava i zakazivanje na Instagram, TikTok, YouTube i Facebook. Gradi se tek kad sve ostalo radi, i samo s Markovim izričitim odobrenjem za svaku uslugu.

### 10. Izvoz u DaVinci
- Radi: uz svaki gotov video izvozi projekt za DaVinci Resolve: timeline (FCPXML) s istim rezovima, originalnim snimkama i oznakama efekata, plus titlove kao SRT. Radi s besplatnim DaVincijem, bez dodatka i bez skripti (Resolve 21.1 je izbacio Python skripte iz besplatne verzije).
- Zvuk i boja ostaju neobrađeni u timelineu, da ih Marko sam doradi.
- Gradi se u M2.
- Gotovo kad: testni reel otvori se u DaVinciju (File > Import > Timeline) i rezovi i titlovi stoje točno kao u Shofeovom videu.

### Sučelje
- Prvo: razgovor s Claudeom (Claude Code skill `shofe-montaza`).
- Zatim: lokalna stranica s projektima, pregledom videa s valnim oblikom zvuka i oznakama tišine, i karticama isječaka s gumbima odobri/odbij. Markova ranija ideja aplikacije za post-produkciju Sunčani4M (tri stupca: materijali, 9:16 pregled s valnim oblikom i oznakama tišine, AI kartice isječaka s tekstovima za mreže) postaje upravo ovo sučelje.

## Redoslijed izgradnje

M1 Temelj → M2 Montaža po naredbi (+ titlovi, DaVinci izvoz) → M3 Isječci za mreže (+ tekstovi) → M4 Podcast → M5 Efekti i grafika → M6 Sučelje i objava. Detalji u `ROADMAP.md`.

Na kraju svake prekretnice agent napravi demo i otvori pregled za Marka, pa nastavlja.

## Odluke koje je Marko donio (24.–25. 11. 2026.)

- Repozitorij: privatni `fertelmesh/shofe-montaza`.
- Ritam: agent radi stalno, krug svaka 2 sata, dok se ne napravi.
- Samostalnost: agent sam odlučuje prema istraživanju i sam spaja promjene kad testovi prođu.
- Rad na Windowsu; za sada samo za vlastitu upotrebu (ne prodaja).
- Bez dodatka za DaVinci; umjesto toga izvoz timelinea (modul 10).

## Otvorene odluke (agent radi sa zadanom vrijednošću dok Marko ne odgovori)

- Sučelje: kada lokalna stranica? Zadano: M6.
- Podcast snimanje: koje kamere i mikrofoni, u kojem obliku snimke? Zadano: 2–3 video datoteke + možda zasebni zvuk.
- Testne snimke: koje prave klipove smije staviti u `tests/real/`?
- Laptop: procesor, RAM, NVIDIA? Zadano: srednji laptop bez NVIDIA, sve mora raditi na procesoru.
- Prodaja: ostaje li samo za vlastitu upotrebu? Zadano: samo permisivne licence, da prodaja ostane moguća.
