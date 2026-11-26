# Shofe montaža

Ti snimaš, Claude montira. Ubaciš sirove klipove s mobitela, napišeš "montiraj ovo" i dobiješ gotov reel: izrezane pauze, poštapalice i loše pokušaje, titlove na hrvatskom riječ po riječ, zumove, korekciju boje, naslov na početku i glazbu koja se sama stiša kad pričaš.

Sve radi na tvom računalu: transkripcija je besplatna i bez interneta (nakon prvog skidanja modela).

## Instalacija (Windows, jednom)

1. Raspakiraj mapu bilo gdje.
2. Dvoklik na **INSTALIRAJ.bat**. Instalira Python (ako ga nema), ffmpeg i transkripciju, i kopira skill u `%USERPROFILE%\.claude\skills\shofe-montaza`.
3. Zatvori i ponovno otvori Claude desktop.

Treba ti Claude desktop s plaćenim planom (Pro je dovoljan) i Code dio aplikacije.

**Nova verzija Shofea:** raspakiraj novu mapu i opet dvoklik na **INSTALIRAJ.bat** — prepisat će stari skill i nadograditi pakete. Koju verziju imaš piše u prvom retku provjere (ili reci Claudeu „koja je verzija Shofea"). Ako na kraju instalacije piše crveno „Nešto nedostaje", zatvori prozor i pokreni INSTALIRAJ.bat još jednom.

## Korištenje

U Claude desktopu otvori **Code**, odaberi mapu u kojoj su klipovi i napiši npr.:

- `montiraj ovo` (Claude sam bira stil)
- `montiraj klipove 1-3 u stilu podcast, hook neka bude "Zašto klima smrdi"`
- `napravi YouTube video 16:9 iz ovih snimki, stil čisto`
- `dodaj glazbu C:/Glazba/ljeto.mp3`

Prvi put transkripcija skida model (~1,6 GB), pa traje nekoliko minuta. Poslije reel od minute traje 1-3 minute.

Ispravci se traže običnim riječima, novi render traje oko minutu:
"povećaj titlove", "titlovi gore", "bez zumova", "toplije boje", "malo brže", "makni dio o cijeni", "promijeni naslov u ...", "plava boja", "glazba tiša", "probaj stil udarno".

Možeš reći i **vremena iz gotovog videa** — onako kako ih vidiš dok ga gledaš:

- `makni od 1:20 do 1:45` ili `izreži 0:05-0:08 i 1:10-1:12`
- `zadrži samo 0:10-0:40`
- `što je na 1:20?`
- `vrati kako je bilo` (poništi zadnju naredbu, može i više puta)

Vremena se uvijek čitaju iz zadnjeg videa koji si dobio, pa možeš reći nekoliko naredbi zaredom dok gledaš isti video. Rez nikad ne pada usred riječi: Claude ti javi koje su riječi otišle i koliko je video sad dug.

Možeš reći i **što** želiš maknuti ili zadržati, bez vremena — Claude to pronađe u tekstu snimke:

- `izreži dio gdje pričam o cijeni` ili `makni rečenicu o suboti`
- `zadrži drugi pokušaj uvoda` (vraća pokušaj koji je Shofe izbacio, a zadnji makne)
- `zadrži samo savjet o filteru`
- `makni cijenu, ali ostavi rečenicu o tisuću eura`
- `vrati dio o održavanju`

Claude ti kaže točno koje su rečenice otišle ili se vratile i koliko je video sad dug. Ako isto spominješ na dva mjesta, pita te koje misliš. Režu se samo riječi koje stvarno postoje u snimci, pa nema krivih rezova od nagađanja.

Možeš tražiti i **trajanje**:

- `skrati na 60 sekundi`, `neka bude ispod minute`, `treba mi verzija od 30 s`
- `skrati za 15 sekundi`
- `skrati na 45, ali ostavi dio o garanciji`

Shofe izbacuje cijele misli, nikad pola rečenice: pitanje ostaje sa svojim odgovorom, „Drugo, ugradnja." s onim što najavljuje, a rečenica koja počinje s „A…", „Zato…", „To…" ne ostaje bez one prije. Claude ocijeni koliko je svaka misao važna za taj video (i pazi na ono što si rekao da je glavno), a Shofe izračuna koja kombinacija stane u zadano vrijeme. Gotovi video je uvijek najviše toliko dug, obično tik ispod. Dijelove koji su već izrezani ne vraća.

## Isječci za mreže

Iz dulje snimke (epizoda podcasta, dulji YouTube video) Shofe predloži kratke isječke od 20 do 60 sekundi:

- `napravi isječke iz ove epizode` ili `predloži 10 klipova za Instagram i TikTok`
- `daj još isječaka` (novi se ne preklapaju s onima koje već imaš ni s odbačenima)
- `uzmi K1 i K3`, `K2 ne, preduga je uvodna priča`

Shofe isproba svaki niz cijelih misli koji traje 20–60 s i ocijeni ga: počinje li jako (pitanje, broj, obraćanje gledatelju, prijelaz s pauzom), završava li zaokruženo (kraj rečenice, misao ne ide dalje, nema pozdrava ni promjene teme u sredini), koliko je sadržajan i živ. Isječak nikad ne počinje rečenicom kojoj treba ona prije („A onda…", „To je zato…"). Zatim Claude pročita svaki prijedlog i da mu ocjenu 1–10 s jednom rečenicom zašto, plus naslov i hook za one dobre. Dobiješ popis od najboljeg prema slabijem; cijeli tekst svakog isječka je u `shofe_projekt/isjecci.txt`.

Kad odabereš, reci `napravi odabrane isječke` (ili `napravi K1 i K3`, `K2 u stilu udarno`). Shofe ih montira jedan za drugim u mapu `shofe_projekt/isjecci/`:

- `K1_najveca-greska-kod-klime.mp4` — isti stil, titlovi i zvuk kao tvoj reel, s Claudeovim hookom u prvim sekundama; pauze, poštapalice i ispravci imena iz glavnog projekta vrijede i ovdje
- uz svaki: `.srt` (titlovi za YouTube), `.fcpxml` (DaVinci) i `pregled.png` (prva sekunda i sredina svakog isječka na jednoj slici, za brzi pogled)
- glavni video i njegove verzije ostaju netaknuti; ako promijeniš naslov ili stil i ponovno napraviš isječak, stari se zamijeni

Za vertikalne isječke iz vodoravne snimke razgovora prvo neka kadar prati govornika (vidi niže), pa tek onda isječci.

## Tekstovi za objavu

Za gotov reel ili isječke reci `napiši tekstove za objavu` (ili `opis za Instagram`, `naslov za YouTube`). Claude napiše poseban tekst za svaku mrežu:

- **Instagram**: prvi redak koji uvuče (to se vidi prije „više"), kratki savjet iz videa, poziv (spremi, pošalji, komentiraj) i 3–5 hashtagova
- **TikTok**: kraće, s riječima koje ljudi traže, često pitanje za komentare
- **YouTube**: naslov do ~60 znakova (tema na početku) i kratki opis; za uspravni video do 3 min to je Short

Shofe provjeri pravila mreža (Instagram i TikTok dopuštaju najviše 5 hashtagova, YouTube naslov do 100 znakova…) i upozori na broj ili cijenu koja se ne čuje u videu, da ništa ne bude izmišljeno. Gotovo je u `reel_v3.objava.txt` (ili `isjecci/K1_….objava.txt`) uz video: tekst za svaku mrežu između crta, samo kopiraš. Sve zajedno je u `shofe_projekt/objava.txt`. Shofe ništa ne objavljuje sam.

**Serije**: reci jednom `za SF klimu uvijek dodaj #sfklima i #kutina, a na kraju napiši „SF klima Kutina — montaža i servis"` i Claude to zapamti kao seriju (vrijedi u svim budućim projektima, i nakon ponovne instalacije). Isto za Sunčani put, Sunčano AJMO! i Sunčani4M, s napomenom o tonu („opuštenije", „uvijek pozovi na poruku za ponudu").

## Verzije

Svaki render je nova verzija: `reel_v1.mp4`, `reel_v2.mp4`... u mapi `shofe_projekt`. Ništa se ne briše, a originalni klipovi se nikad ne diraju. Možeš reći:

- `pokaži verzije` — popis s datumom, trajanjem, stilom i jednim retkom što se promijenilo prema prethodnoj
- `vrati verziju 2` ili `vrati kako je bilo u prvoj verziji` — montaža se vrati na tu verziju; video te verzije već postoji, pa nema čekanja na render. Novije verzije ostaju, a i ovo se može poništiti („ipak ne").
- `što se promijenilo od verzije 2?` ili `usporedi verziju 1 i 3` — koje su rečenice otišle ili se vratile (s vremenom u videu i zašto), promijenjeni stil, titlovi, boje, naslov i ispravci teksta
- `nazovi verziju 3 „za Instagram"` — da je poslije lakše nađeš

Nakon „vrati verziju 2" vremena u sljedećim naredbama čitaju se iz `reel_v2`, jer tu verziju gledaš.

## Titlovi za YouTube (SRT)

Uz svaki video Shofe sam napravi i datoteku titlova istog imena: `reel_v3.mp4` → `reel_v3.srt`. To su klasični titlovi za čitanje (cijele fraze, najviše dva retka), s ispravljenim imenima i pravopisom, točno u vremenu gotovog videa — i nakon rezova i ubrzanja.

- **YouTube:** u YouTube Studiju → Titlovi → Dodaj → Prenesi datoteku → „S vremenskim oznakama" → odaberi `.srt`. YouTube ih tada pokazuje kao prave titlove (gledatelj ih uključi/isključi), a pomažu i pretrazi.
- **Dulji YouTube video:** reci „bez titlova u videu" pa prenesi samo `.srt`, inače se vide dvaput.
- **VLC** ih sam učita jer imaju isto ime kao video; **DaVinci**: File > Import > Subtitle.
- Za web stranicu reci „napravi i VTT titlove"; za stariju verziju „titlovi za verziju 2".

### Engleski titlovi

Reci „napravi i engleske titlove" (ili „prevedi titlove na engleski"). Claude prevede svaki titl i Shofe napiše `reel_v3.en.srt` — isto vrijeme kao hrvatski, najviše dva retka, imena (Sunčani4M, SF klima, Kutina) ostaju kako jesu.

- Od tada **svaki novi render sam napravi i `.en.srt`**: Shofe pamti prijevode, pa nakon rezova Claude prevodi samo rečenice koje su nove ili promijenjene.
- **YouTube:** Studio → Titlovi → Dodaj jezik → engleski → Prenesi datoteku → `reel_v3.en.srt`. Gledatelj tada bira hrvatske ili engleske titlove.
- **VLC** ih nađe sam (Titlovi → Podnaslovna traka); prijevode možeš pročitati i ispraviti u `prijevod_en.json` u mapi projekta.
- Može i drugi jezik: „prevedi titlove na njemački" → `reel_v3.de.srt`.

## DaVinci Resolve

Uz svaki video Shofe napravi i **timeline za DaVinci**: `reel_v3.mp4` → `reel_v3.fcpxml` (+ `reel_v3.srt`). U njemu su tvoje **originalne snimke** s mobitela s istim rezovima kao u Shofeovu videu, isto kadriranje i zumovi, glazba na zasebnoj traci i oznake (stil, naslov, zumovi). Zvuk i boja su neobrađeni — to doradiš sam. Radi i s besplatnim DaVincijem (verzija 18 ili novija).

1. U DaVinciju otvori novi projekt (u postavkama projekta stavi 30 fps i rezoluciju videa, npr. 1080×1920 za reel).
2. **File > Import > Timeline** → odaberi `reel_v3.fcpxml` (ostavi uključeno „Automatically import source clips into media pool").
3. **File > Import > Subtitle** → `reel_v3.srt`, pa titlove povuci na timeline (počinju na 00:00).

- Ako si originalne snimke premjestio, DaVinci pita gdje su (Relink). Ako ih više nema, Shofe sam koristi pripremljeni `source.mp4`.
- Za stariju verziju reci „DaVinci za verziju 2".
- Ako u DaVinciju kadar vodoravne snimke nije isti kao u Shofeu, reci „DaVinci iz pripremljenog videa" (koristi već izrezani `source.mp4`).

## Karta videa

Prije montaže Shofe napravi „kartu videa" (`analiza.txt` u mapi `shofe_projekt`): gdje su tišine, koliko je glasno, koliko brzo pričaš, gdje su rezovi, i koji su dijelovi mutni, pretamni ili presvijetli. Claude zatim iz teksta dopiše teme i najjače trenutke (hook, poanta, smijeh, savjet). Pitaj npr.:

- `što je u ovom videu?` ili `koji su najjači trenuci?`
- `ima li mutnih ili tamnih dijelova?`

Kartu možeš i **vidjeti**: u mapi `shofe_projekt` je `pregled.html` — dvoklik i otvori se u pregledniku (radi bez interneta). Gore je video i popis najjačih trenutaka, ispod vremenska crta: glasnoća s tišinama, tko kad govori (u boji), teme, trenuci (veći krug = bolja ocjena) i loši kadrovi. Klik bilo gdje (trenutak, tema, rečenica u transkriptu, mjesto na crti) skoči na to mjesto u videu. Gumbi **+ / −** zumiraju crtu (ili Ctrl + kotačić miša), a u transkriptu možeš tražiti riječ. Možeš reći i `pokaži kartu videa`.

Za dulje snimke i podcast karta se radi uvijek; za kratki reel po potrebi.

## Tko govori

Kad u snimci govori više ljudi (podcast, intervju, gost u autu), Shofe prepozna tko govori i svaku rečenicu pripiše govorniku. Claude iz razgovora zaključi tko je tko (ili te pita) i upiše imena, pa u transkriptu piše `Marko: …`, `Ivan: …`. Pitaj npr.:

- `tko sve govori u ovoj epizodi i koliko?`
- `u snimci smo nas trojica, prvi je Marko, drugi Ivan`

Radi na procesoru, bez interneta (prvi put skine dva mala modela, ~36 MB), oko 7× brže od trajanja snimke. Ako znaš koliko vas govori, reci Claudeu — tada je točnije. Vrlo kratki odgovori („Da.", „Točno.") ponekad dobiju krivog govornika.

## Kadar prati govornika

Kad od vodoravne snimke (podcast, intervju, dvoje u autu) radiš reel ili isječak 9:16, Shofe može sam pomicati kadar na onoga tko govori. Reci npr.:

- `kadar neka prati onoga tko priča`
- `vrati kadar na sredinu`

Shofe nađe lica u originalnim snimkama, iz govornika i pokreta usana zaključi tko kada govori i ponovno složi video. Ponaša se kao montažer: na drugog govornika prelazi rezom (ne švenkom), kratko „da" ili smijeh ne mijenja kadar, kamera miruje dok se samo njišeš, a ide za tobom kad se pomakneš. Kad govori netko koga nema u slici, kadar ostaje gdje je. Najbolje radi nakon „tko govori" (vidi gore). Rezovi, titlovi i verzije ostaju isti, a i DaVinci timeline dobije rez na svakoj promjeni govornika. Radi na procesoru, bez interneta.

## Stilovi

| Stil | Za što |
|---|---|
| **suncani** | Energično: velika slova, trenutna riječ žuta, topla slika, česti zumovi |
| **podcast** | Isječci Sunčani4M: riječi se pojavljuju dok se izgovaraju, narančasto |
| **udarno** | Viralni hook: jedna ogromna riječ u sredini, agresivni zumovi, traka napretka |
| **cisto** | Savjeti i YouTube: mirni titlovi na tamnoj podlozi, bez zumova |
| **kino** | Priče i atmosfera: filmske boje, vinjeta, razmaknuta slova |

Novi stil: reci Claudeu "napravi mi stil kao suncani, ali plavi i s manjim slovima" i on će napraviti novu datoteku u `styles/`.

## Rječnik

Shofe pamti tvoje ispravke. Kad u titlovima ispraviš krivo čuto ime (ili ga Claude ispravi), nakon rendera to zapamti; kad isti ispravak vidi **dvaput** (u jednom ili više videa), sljedeći put ga radi sam i javi „Rječnik naučio: Fertelmes → Fertelmeš". Uči samo krivo čute riječi i imena (kvačice, velika slova imena, „esef → SF"), ne gramatiku ni preformulirane rečenice.

- Ako rječnik nešto krivo ispravi, samo vrati staru riječ u titlovima; Shofe to primijeti i više ne radi taj ispravak.
- Reci Claudeu: „pokaži rječnik" (što je naučio), „zapamti ime Ivan Horvat" (prije transkripcije gosta), „uvijek piši SF klima umjesto esef klima", „zaboravi ispravak X".
- `rjecnik.txt` u skillu je osnovni popis imena (Sunčani put, SF klima, Kutina...). Ono što Shofe nauči i što dodaš čuva se u `%LOCALAPPDATA%\Shofe\rjecnik.json`, pa ostaje i kad ponovno instaliraš Shofe.

## Glazba

Koristi samo glazbu za koju imaš prava; Instagram i TikTok mogu utišati reel s tuđom glazbom. Glazba se sama stišava ispod glasa.

## Fontovi

Montserrat i Anton, oba pod SIL Open Font License (u mapi `fonts/`), smiju se slobodno koristiti i u komercijalnim videima.
