# Demo — pregled M4 (podcast Sunčani4M)

Sve je napravljeno iz **probne epizode 12** (3 min): Marko i Ivan u Renaultu 4, na stražnjem sjedalu bend Kutina koji usred vožnje zasvira pjesmu. Snimaju **tri kamere i diktafon**, svaki uključen u drugom trenutku: široka GoPro kamera 4,2 s prije diktafona, kamera na Marku 2,5 s poslije, Ivanov mobitel uspravno 6,1 s poslije (i ugasi se prije kraja). Na slici svake kamere piše koja je i vrijeme **u toj datoteci**. Glasovi i bend su sintetski, ne tvoje snimke. Teme, opis epizode i ocjene isječaka napisao je Claude kao što bi na tvom laptopu; sve ostalo (sinkronizacija, režija, pjesma, špice, poglavlja, MP3, DaVinci, isječci) je Shofe. Pravu kvalitetu provjeri na svojoj epizodi (upute u issueu „Pregled M4").

| Datoteka | Što pokazuje |
|---|---|
| `M4_epizoda.mp4` | Korak po korak: sinkronizacija po zvuku (pomaci točni), mozaik **tri kamere + program** (narančasti okvir = kamera u programu: kamera prati onoga tko govori, brza izmjena → široki kadar), pjesma (široki kadar, sporiji rezovi na takt), pa dijelovi **gotove epizode**: najava → uvodna špica → dobrodošlica, početak pjesme, nakon pjesme, odjavna špica. Dolje lijevo je poglavlje u kojem si (kao na YouTubeu). |
| `M4_isjecci.mp4` | Dva uspravna isječka iz epizode, iz **originalnih kamera**: razgovor (svatko iz svoje kamere, podijeljen kadar kad se brzo izmjenjuju) i pjesma (cijeli bend u kadru, rez na takt, bez titlova). |
| `M4_paket.png` | Sve ostalo za objavu: generirana uvodna i odjavna špica, MP3 za Spotify/Apple s poglavljima, YouTube opis s poglavljima, tekst za podcast platforme s brojem epizode, i **DaVinci timeline** kako ga Resolve otvori (program iz originalnih kamera na V1, ostale kamere iznad, pjesma na svojoj traci, zelene oznake poglavlja). |

Ranije: [demo M3](https://github.com/fertelmesh/shofe-montaza/tree/a6504b8/demo) (isječci za mreže, kadar 9:16, objava, naslovne), [demo M2](https://github.com/fertelmesh/shofe-montaza/tree/8e13791/demo) (naredbe, engleski titlovi, verzije, DaVinci), [demo M1](https://github.com/fertelmesh/shofe-montaza/tree/d322cb95f66afc3efe74ee8e4a33de2c4f3063a0/demo) (reel, 5 stilova, karta videa).

Ponovno napraviti: `python tests/make_demo_m4.py` (treba ffmpeg, espeak-ng, OpenCV, Pillow i Playwright s Chromiumom; ~15 min). Ranije: `python tests/make_demo_m3.py`, `python tests/make_demo_m2.py`, `python tests/make_demo.py`.
