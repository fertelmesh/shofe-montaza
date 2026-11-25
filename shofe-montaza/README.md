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

## Verzije

Svaki render je nova verzija: `reel_v1.mp4`, `reel_v2.mp4`... u mapi `shofe_projekt`. Ništa se ne briše, a originalni klipovi se nikad ne diraju. Možeš reći:

- `pokaži verzije` — popis s datumom, trajanjem, stilom i jednim retkom što se promijenilo prema prethodnoj
- `vrati verziju 2` ili `vrati kako je bilo u prvoj verziji` — montaža se vrati na tu verziju; video te verzije već postoji, pa nema čekanja na render. Novije verzije ostaju, a i ovo se može poništiti („ipak ne").
- `što se promijenilo od verzije 2?` ili `usporedi verziju 1 i 3` — koje su rečenice otišle ili se vratile (s vremenom u videu i zašto), promijenjeni stil, titlovi, boje, naslov i ispravci teksta
- `nazovi verziju 3 „za Instagram"` — da je poslije lakše nađeš

Nakon „vrati verziju 2" vremena u sljedećim naredbama čitaju se iz `reel_v2`, jer tu verziju gledaš.

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

U `rjecnik.txt` su imena koja transkripcija mora pisati točno (Sunčani put, SF klima, Kutina...). Dodaj svoje, jedno po retku.

## Glazba

Koristi samo glazbu za koju imaš prava; Instagram i TikTok mogu utišati reel s tuđom glazbom. Glazba se sama stišava ispod glasa.

## Fontovi

Montserrat i Anton, oba pod SIL Open Font License (u mapi `fonts/`), smiju se slobodno koristiti i u komercijalnim videima.
