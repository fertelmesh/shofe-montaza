# Demo — pregled M2 (Montaža po naredbi)

Sve je napravljeno iz probne snimke (sintetski glas, umjetna slika), ne iz tvojih klipova. Na slici je **vremenski kod izvornog klipa**, pa se vidi što je izrezano. Pravu kvalitetu provjeri na svojoj snimci (upute u issueu „Pregled M2").

| Datoteka | Što pokazuje |
|---|---|
| `M2_naredbe.mp4` | Probni reel „SF klima" (2 klipa, tri pokušaja uvoda, zabuna u cijeni). Prije svakog videa kartica: što je Marko rekao i što je Shofe napravio. 1) automatski plan izbaci loše pokušaje uvoda; 2) „zadrži drugi pokušaj uvoda, a izreži dio gdje pričam o cijeni"; 3) „makni od 0:10,5 do 0:13,8" (po vremenu, rez poravnat na cijele riječi); 4) „skrati na 20 sekundi, savjet o filteru mora ostati". Svaki korak je nova verzija. |
| `M2_engleski.mp4` | Zadnja verzija s Shofeovim titlovima i engleskim SRT-om (`reel_v4.en.srt`) kako ga prikazuje VLC/YouTube. |
| `M2_verzije.png` | Što Claude vidi kad kažeš „pokaži verzije", „što se promijenilo" i kako ocjenjuje misli za „skrati". |
| `M2_davinci.png` | Timeline iz `reel_v4.fcpxml` nacrtan iz XML-a (nije snimka DaVincija): 7 kadrova iz originalnih klipova, vremenski kod u originalu, zumovi, glazba na A2, oznake. |

Demo za M1 (reel, 5 stilova, karta videa) je u povijesti repozitorija: [demo M1](https://github.com/fertelmesh/shofe-montaza/tree/d322cb95f66afc3efe74ee8e4a33de2c4f3063a0/demo).

Ponovno napraviti: `python tests/make_demo_m2.py` (treba ffmpeg, espeak-ng i Playwright s Chromiumom). Demo M1: `python tests/make_demo.py`.
