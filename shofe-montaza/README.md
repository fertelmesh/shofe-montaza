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

Za vertikalne isječke iz vodoravne snimke razgovora prvo neka kadar prati govornika (vidi niže), pa tek onda isječci. Kod podcasta s više kamera (Sunčani4M) to ne treba: isječci su sami uspravni iz kamera (vidi „Podcast").

## Tekstovi za objavu

Za gotov reel ili isječke reci `napiši tekstove za objavu` (ili `opis za Instagram`, `naslov za YouTube`). Claude napiše poseban tekst za svaku mrežu:

- **Instagram**: prvi redak koji uvuče (to se vidi prije „više"), kratki savjet iz videa, poziv (spremi, pošalji, komentiraj) i 3–5 hashtagova
- **TikTok**: kraće, s riječima koje ljudi traže, često pitanje za komentare
- **YouTube**: naslov do ~60 znakova (tema na početku) i kratki opis; za uspravni video do 3 min to je Short

Shofe provjeri pravila mreža (Instagram i TikTok dopuštaju najviše 5 hashtagova, YouTube naslov do 100 znakova…) i upozori na broj ili cijenu koja se ne čuje u videu, da ništa ne bude izmišljeno. Gotovo je u `reel_v3.objava.txt` (ili `isjecci/K1_….objava.txt`) uz video: tekst za svaku mrežu između crta, samo kopiraš. Sve zajedno je u `shofe_projekt/objava.txt`. Shofe ništa ne objavljuje sam.

**Serije**: reci jednom `za SF klimu uvijek dodaj #sfklima i #kutina, a na kraju napiši „SF klima Kutina — montaža i servis"` i Claude to zapamti kao seriju (vrijedi u svim budućim projektima, i nakon ponovne instalacije). Isto za Sunčani put, Sunčano AJMO! i Sunčani4M, s napomenom o tonu („opuštenije", „uvijek pozovi na poruku za ponudu").

## Naslovna sličica

Reci `napravi naslovnu sličicu` (ili `thumbnail za K1`, `cover za reel`). Shofe pregleda video svakih pola sekunde i izabere najbolji kadar: lice veliko, oštro, otvorene oči, dobro osvijetljeno, okrenuto prema kameri. Claude napiše kratki tekst (2–5 riječi, ključna riječ u boji stila), pogleda rezultat i napravi:

- `reel_v3.naslovna_9x16.jpg` — za Instagram, TikTok i YouTube Shorts; lice i tekst su u sredini koju Instagram pokazuje na tvom profilu (3:4), daleko od gumba aplikacija
- `reel_v3.naslovna_16x9.jpg` — za YouTube; iz vodoravne snimke uzme širi kadar s krupnim licem, a tekst stavi sa strane
- `reel_v3.naslovna_kandidati.jpg` — 6 najboljih kadrova s ocjenom; reci `uzmi treći kadar` ili `naslovna iz 0:12`
- `reel_v3.naslovna_pregled.jpg` — obje sličice na jednoj slici (crvene crtice = što Instagram odreže na profilu)

Možeš reći i `drugi tekst na naslovnoj: …` (kadar ostaje) ili `naslovna bez teksta`. Za isječke: `napravi naslovne za sve isječke`. Shofe ništa ne objavljuje sam: na Instagramu i TikToku izabereš „Uredi naslovnicu → iz galerije", na YouTubeu u Studiju „Sličica → Prenesi".

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

**Špica i poglavlja u DaVinciju.** Timeline epizode ima **špicu na istom mjestu** kao Shofeov video: uvodnu (i iza najave), odjavnu na kraju. Tvoj intro/outro je ondje kao original (zvuk neobrađen), a generirana kartica je u mapi projekta `spica/` (ne briši je). **Poglavlja** (ista kao u opisu za YouTube) su oznake u timelineu, a uz timeline dobiješ i `reel_vN.poglavlja.edl` — tako ih DaVinci upiše kao poglavlja u izvezeni video:

1. U Media Poolu desni klik na timeline > **Timelines > Import > Timeline Markers from EDL** → `reel_vN.poglavlja.edl` (dobiješ zelene oznake s imenima poglavlja).
2. Na stranici **Deliver** (format MP4 ili QuickTime) uključi **Chapters from Markers** i odaberi boju **Green**.

Ako ti zelene oznake sjednu sat vremena iza videa, timeline u DaVinciju počinje od 01:00:00:00 — javi Shofeu.

**Podcast u DaVinciju.** Za epizodu Sunčani4M timeline nije gotov video nego tvoje **originalne kamere**:

- **V1** — program kakav je Shofe montirao: na svakom kadru originalna snimka kamere koju je Shofe izabrao (isti izrez, i za uspravni mobitel), bez zvuka kamere.
- **V2, V3, V4…** — iznad svakog kadra ostale kamere u istom trenutku, svaka kamera uvijek na svojoj traci. **Isključene su** (sive). Ako želiš drugu kameru na nekom mjestu, klikni taj komad i pritisni **D** (Enable Clip) — on prekrije kadar ispod. Ili ga razreži (B) pa uključi samo dio.
- **A1** — zvuk glavnog snimača (ili glavne kamere) ispod cijele epizode; glazba, ako je ima, ispod njega.
- Postavke projekta: 1920×1080, 30 fps. Ako se ipak pojavi i zvuk kamera, utišan je (−96 dB) — možeš ga pojačati ako želiš zvuk prostora.

**Uspravni isječak epizode u DaVinciju.** I `isjecci/K1.fcpxml` je iz **originalnih kamera** (postavke projekta 1080×1920, 30 fps):

- **V1** — kadar po kadar kamera onoga tko govori, isto uokvirena kao u Shofeovu isječku (i zumovi).
- **Podijeljen kadar** (gore/dolje) su dva komada: gornja osoba na **V1**, donja na **V2**, svaka izrezana na svoju polovicu (Inspector > Cropping), s tamnom crtom između.
- **V3** — Shofeova gotova uspravna slika (bez titlova), **isključena**. Ako ti podijeljen kadar u DaVinciju izgleda krivo (npr. obje osobe preko cijelog kadra), klikni komad na V3 i pritisni **D** — to je točno slika iz Shofea.
- **A1** — zvuk glavnog snimača. Titlovi: File > Import > Subtitle > `K1.srt`.
- Ne briši mapu `isjecci/izvor_9x16/` (V3 je iz nje; ako originalne kamere premjestiš, cijeli timeline je iz nje).

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

## Podcast: više kamera i zasebni zvuk

Kad epizodu snimaš s 2–3 kamere i možda zasebnim snimačem zvuka, Shofe ih sam poravna po zvuku — bez klapne i bez ručnog pomicanja. Kamere smiju krenuti u različito vrijeme. Reci npr.:

- `ovo su snimke epizode 12, sinkroniziraj kamere i zvuk` (i daj mapu sa snimkama)
- `kamera 3 nije dobro sjela, počinje otprilike 12 sekundi prije zvuka`

Glavna vremenska crta je zasebni zvuk (ako ga ima), inače najdulja kamera. Shofe za svaku kameru izmjeri gdje počinje (na tisućinku sekunde) i koliko joj sat žuri ili kasni (kamere znaju odlutati i desetinku-dvije na sat; Shofe to ispravi). Dobiješ `sinkro_provjera.mp4` — 10 sekundi svih kamera jedna uz drugu sa zvukom: usne moraju pratiti glas — i `sinkro.png`, gdje se vrhovi glasnoće svih izvora moraju poklapati. Snimka koja nije iz iste epizode ili nema zvuka bit će označena za provjeru. Za sat snimke treba oko minutu (najviše traje čitanje zvuka iz videa).

### Kamera na onoga tko govori

Nakon sinkronizacije reci npr.:

- `montiraj epizodu, kamera neka prati onoga tko priča`
- `kamera 2 snima Ivana` (ako Shofe krivo pogodi)
- `manje širokih kadrova` / `više širokih kadrova` / `brži rezovi`

Shofe prvo složi epizodu u širokom kadru, prepozna tko govori (transkript + govornici), pa sam pogleda svaku kameru: kamera s jednim licem je krupni kadar te osobe (prepozna je po usnama dok govori), kamera s dvoje-troje ljudi je široki kadar. Onda montira kao režiser: dok netko govori, vidi se njegova kamera; kad pričate u isti glas ili se brzo dobacujete, široki kadar; gost bez svoje kamere i dulja tišina također idu u široki kadar; kratko „aha" ne prebacuje kameru, a svaki kadar traje barem 2 sekunde. U dugom monologu svakih 30-ak sekundi na tren uskoči široki kadar. Kamera koja je u tom trenutku ugašena se ne bira. Zvuk je uvijek onaj najbolji (zasebni snimač). Dobiješ `rezija.png` (koja kamera kad) i gotov 16:9 video epizode, na kojem dalje radi sve ostalo: rezanje, titlovi, isječci, DaVinci. Timeline za DaVinci je iz originalnih kamera, s ostalim kamerama na trakama iznad (vidi „Podcast u DaVinciju").

**Isječci iz epizode (9:16).** Kad iz epizode napraviš isječke (`napravi odabrane isječke`), Shofe ih ne reže iz 16:9 epizode nego ih ponovno složi iz originalnih kamera, uspravno: dok netko govori, cijeli kadar je njegovo lice iz njegove kamere (mobitel snimljen uspravno ide kakav jest); ako nema svoju kameru, Shofe izreže njegovo lice iz širokog kadra. Kad pričate u isti glas ili se brzo dobacujete, kadar se podijeli: gore jedan, dolje drugi. Kad govori gost kojeg nijedna kamera ne snima, vidite se vas dvojica kako slušate. Zvuk, titlovi, hook i rezovi isti su kao inače; samo dok je kadar podijeljen, titlovi stoje na sredini, na spoju gornjeg i donjeg dijela, da ne prekriju usta onoga dolje. Naslovna sličica takvog isječka (`napravi naslovne za isječke`) uzima lice iz kamere govornika, radije kadar s jednim licem nego podijeljen, a 16:9 za YouTube iz originalne kamere te osobe. Ako ipak želiš vodoravne isječke (npr. za YouTube), reci `isječke vodoravno` (`--format 16:9`). Za svaki isječak u mapi `isjecci/izvor_9x16/` ostaje njegov uspravni izvor; ne briši ga ako ćeš isječak otvarati u DaVinciju.

### Nastupi bendova: pjesma se ne reže

Kad u autu svira bend, Shofe pjesmu pronađe sam (prvi put skine mali model od 6 MB) i nikad je ne reže iznutra: pauze između strofa, instrumentalni dijelovi i pljesak na kraju ostaju, nema titlova preko pjesme, a zvuk pjesme ne prolazi kroz čišćenje šuma i kompresor za govor (oni pojedu činele i bas) nego kroz blagu obradu za glazbu. Pozadinska glazba šuti dok bend svira. Radio koji svira ispod razgovora i kratki džinglovi nisu pjesme. Reci npr.:

- `u epizodi svira bend` / `gdje su pjesme?` — dobiješ popis i `nastupi.png` (zeleno = pjesma)
- `pjesma počinje na 12:28, ne na 12:30` / `ono na 40:00 nije pjesma` / `prva pjesma je „Kutina" od benda X`
- `makni drugu pjesmu` / `vrati pjesmu` / `ostavi samo pjesmu` (npr. za zaseban video pjesme)
- `pjesma je preglasna` / `prva pjesma neka bude malo glasnija od razgovora` / `sve pjesme malo tiše`

Naredba „makni 3:10–3:20" koja pada usred pjesme ne reže pjesmu (Shofe javi da pjesma ostaje cijela); dio koji pokriva cijelu pjesmu makne je cijelu. Ako stvarno želiš izrezati dio pjesme (npr. solo), reci to izričito: `izreži solo iz pjesme od 3:10 do 3:40`. „Skrati na N minuta" skraćuje samo razgovor, a isječci razgovora za mreže nikad ne idu preko pjesme (pjesma ima svoj isječak, vidi dolje).

Kamera za vrijeme pjesme (podcast): Shofe ne prati „govornika" (pjevanje nije razgovor) nego režira kao koncert — pjesma počne i završi u **širokom kadru**, a između se široki kadar izmjenjuje s vašim kamerama, **sporo** (prosječno 8 sekundi po kadru, nikad kraće od 4). Shofe izmjeri tempo pjesme i reže **na udarac, na početku takta**, pa rezovi idu u ritmu. Nakon što Shofe nađe pjesme, Claude još jednom pokrene režiju epizode. Reci npr. `sporiji rezovi u pjesmi` ili `cijela pjesma u širokom kadru`. U DaVinciju svaka pjesma ima oznaku cijelom duljinom („Pjesma P1: naziv"), a zvuk pjesme je na **svojoj traci** ispod govora (A1 govor, A2 pjesma), pa pjesmu možeš obraditi kao glazbu, a razgovor kao govor.

Glasnoću pjesme Shofe namjesti sam: izmjeri koliko je glasan razgovor, a koliko svaka pjesma, i pjesmu pojača ili stiša tako da bude **jednako glasna kao razgovor** (bend u autu zna biti puno glasniji od vas). Pjesma pritom zadrži svoje tiše i glasnije dijelove — ne „pumpa". Cijeli video je na −14 LUFS, kao što traže mreže. Pri renderu napiše npr. „Glasnoća P1: u snimci 5,4 LU glasnija od govora → stišana". Ako ti se ne sviđa, reci npr. `pjesma neka bude malo glasnija` (2 LU) ili točno `pjesma 1 glasnija za 3`.

**Isječak iz pjesme.** Kad tražiš isječke za mreže, Shofe iz svake pjesme sam predloži jedan: **najbolji refren, 30–60 sekundi**. Pronađe dio pjesme koji se najčešće ponavlja i najjači je (refren), isječak krene točno na udarac na kojem refren počinje, traje cijele taktove i završi na kraju refrena ili na kraju pjesme s pljeskom. Najčešće je to zadnji, dupli refren. Isječak iz pjesme nema titlova, a zvuk je obrađen za glazbu. Claude pjesmu ne čuje, pa o njoj odlučuje tvoje uho. Reci npr.:

- `isječak pjesme neka krene od drugog refrena` / `isječak pjesme od 12:40 do 13:25`
- `nađi ponovo refren prve pjesme`

U `pregled.html` pjesme su na vremenskoj crti (zeleno; tamnije = refren, narančasti okvir = isječak), a ispod je popis pjesama s gumbom ▶ koji pusti isječak iz pjesme.

Kod podcasta je isječak pjesme **uspravan (9:16) i u ritmu**: počne i završi na **bendu** iz širokog kadra, a između se izmjenjuju vaše krupne kamere, rez je točno na udarac na početku takta (prosječno svakih 6 s, malo brže nego u epizodi jer je isječak za mreže). Kad u širokom kadru svi ne stanu u uski uspravni kadar, Shofe pokaže **cijeli bend u širini**, malo iznad sredine, a iznad i ispod je ista slika zamućena i potamnjena — nitko nije odrezan. Za vrijeme pjesme kadar se ne dijeli i ne prati onoga tko pjeva. Ako želiš cijelu pjesmu na bendu, reci `cijela pjesma u širokom kadru`. U DaVinciju je bend na dvije trake: V2 cijeli bend, V1 ista kamera kao pozadina (ondje nije zamućena — ako želiš kao u Shofeu, na V1 dodaj efekt Gaussian Blur).

### Poglavlja za YouTube i MP3 za podcast

Kad Claude napravi kartu epizode, upiše i **teme** (npr. „Kako smo kupili Renault 4"). Iz njih Shofe sam složi **poglavlja za YouTube**: pri svakom renderu vodoravnog videa duljeg od 3 minute uz video dobiješ `reel_vN.poglavlja.txt` s redovima poput `00:00 Uvod`, `12:40 Pjesma: Bend – Ljeto`, `14:05 Kako smo kupili Renault 4` — samo ih zalijepi u opis videa na YouTubeu. Vremena su iz **gotovog** videa (nakon svih rezova), svaka pjesma je svoje poglavlje, prvo je uvijek 00:00 i nijedno nije kraće od 10 sekundi (to traži YouTube; kraći dio ide u susjedno poglavlje, a kratki razgovor iza pjesme u sljedeću temu, ne u pjesmu). Reci npr.:

- `poglavlja za YouTube` — dobiješ popis za kopiranje
- `preimenuj treće poglavlje u „Gost iz Zagreba"` / `spoji prva dva poglavlja` / `novo poglavlje na 23:10`

**MP3 za podcast platforme** (Spotify, Apple Podcasts…): reci `napravi MP3` (ili `napravi MP3, naslov „Gost iz Zagreba"`). Shofe iz gotove epizode napravi `reel_vN.mp3`: glasnoća **−16 LUFS** (što traže podcast platforme; video ostaje na −14 za mreže), vrhovi ispod −1 dB, 128 kbps stereo, a **poglavlja su upisana u MP3**, pa ih aplikacije za podcaste pokažu. Pjesme su jednako glasne kao u videu. Ako želiš, Shofe u MP3 stavi i naslovnu sliku (kvadratnu). Za sat epizode treba oko minutu. MP3 zatim sam učitaš na svoju podcast platformu — Shofe ništa ne objavljuje.

**Opis epizode** — reci `napiši opis epizode` (ili `tekst za YouTube i Spotify`). Claude napiše dva teksta, a Shofe ih provjeri i složi u `reel_vN.objava.txt`:

- **YouTube**: naslov, opis i hashtagovi; **poglavlja Shofe sam doda na kraj opisa** (iz gotovog videa, nikad ručno upisana vremena koja bi nakon nove montaže bila kriva).
- **Podcast platforme** (Spotify for Creators, Apple Podcasts…): naslov epizode, opis s poglavljima u obliku koji Spotify pretvori u poglavlja (svako barem 30 s) i **broj epizode zasebno** — Apple traži da broj i ime podcasta ne budu u naslovu epizode, nego u svom polju (Shofe upozori ako jesu). Bez hashtagova, jer ih podcast aplikacije ne koriste.

Ako je MP3 već napravljen s drugim naslovom, Shofe kaže kako ga ponovno napraviti s istim naslovom kao na platformama. Potpis serije (npr. `za Sunčani4M na kraju napiši „Slušaj nas svaki petak"`) dodaje se i na podcast tekst; za samo podcast reci `potpis samo za Spotify`.

### Uvodna i odjavna špica

Reci `dodaj špicu` i Shofe epizodi doda **uvodnu špicu** (kratka kartica: SUNČANI4M, naslov epizode i broj, preko mutnog kadra iz epizode) i **odjavnu špicu** (15 s: „Hvala što ste gledali!" i „Pretplati se" u gornjem dijelu — donji dio je prazan za YouTube završni zaslon, gdje dodaješ sljedeći video i gumb za pretplatu; YouTube ga dopušta u zadnjih 5–20 s). Prije rendera dobiješ sliku obje kartice.

Imaš li svoj intro ili outro video, reci `moj intro je C:\…\intro.mp4, zapamti ga` — Shofe ga zapamti za sve epizode, prilagodi veličini videa i izjednači mu glasnoću s epizodom. Ostalo što možeš reći:

- `špica iza najave na 0:25` — epizoda krene najjačim trenutkom, pa dođe špica (Shofe je stavi u stanku, na kraj rečenice)
- `špica s glazbom spica.mp3`, `naslov na špici „Bend iz Kutine"`, `epizoda 12`
- `bez odjavne špice`, `makni špicu`

Špica je samo u cijeloj epizodi, ne u isječcima. Titlovi, poglavlja, MP3 i naredbe poput „makni 5:00–5:10" sami se pomaknu za špicu — uvijek govoriš vremena iz videa koji gledaš. I DaVinci timeline ima špicu na istom mjestu (vidi „Špica i poglavlja u DaVinciju").

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
