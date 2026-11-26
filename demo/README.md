# Demo — pregled M3 (Isječci za mreže)

Sve je napravljeno iz probne epizode Sunčani4M (3 min, dva nacrtana voditelja u vodoravnom kadru, sintetski glasovi), ne iz tvojih snimki. Na slici je **vrijeme snimke**, pa se vidi iz kojeg dijela epizode je isječak. Ocjene, hookove i tekstove za objavu napisao je Claude kao što bi na tvom laptopu; sve ostalo (kandidati, kadar, montaža, titlovi, provjera pravila mreža, naslovne sličice) je Shofe. Pravu kvalitetu provjeri na svojoj snimci (upute u issueu „Pregled M3").

| Datoteka | Što pokazuje |
|---|---|
| `M3_isjecci.mp4` | „Napravi isječke iz ove epizode": 4 kandidata s Claudeovom ocjenom i Shofeovim bodovima (čavrljanje, lutanje, nedovršena priča i odjava nisu predloženi), Marko odobri K1–K3 i odbaci K4, pa sva tri gotova isječka 9:16 jedan za drugim — svaki sa svojim stilom (čisto, podcast, kino), hookom i titlovima. |
| `M3_kadar.mp4` | Lijevo vodoravna snimka s narančastim okvirom koji Shofe izreže, desno gotov 9:16 kadar. Uvodno čavrljanje (brze izmjene) i pitanje–odgovor o održavanju klime: kadar uvijek na onome tko govori, rez a ne švenk. |
| `M3_objava.png` | Za K1: naslovna sličica 9:16 (Reels/TikTok/Shorts) i 16:9 (YouTube, krupno lice iz vodoravne snimke) + tekstovi za Instagram, TikTok i YouTube sa stalnim potpisom i hashtagovima serije Sunčani4M (iz `K1_….objava.txt`). |
| `M3_naslovna.jpg` | 6 najboljih kadrova za naslovnu s ocjenom i razlogom — to Claude pogleda prije nego predloži sličicu. |

Ranije: [demo M2](https://github.com/fertelmesh/shofe-montaza/tree/8e13791/demo) (naredbe, engleski titlovi, verzije, DaVinci), [demo M1](https://github.com/fertelmesh/shofe-montaza/tree/d322cb95f66afc3efe74ee8e4a33de2c4f3063a0/demo) (reel, 5 stilova, karta videa).

Ponovno napraviti: `python tests/make_demo_m3.py` (treba ffmpeg, espeak-ng, OpenCV, Pillow i Playwright s Chromiumom; ~6 min). Ranije: `python tests/make_demo_m2.py`, `python tests/make_demo.py`.
