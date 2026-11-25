# Demo — pregled M1 (Temelj)

Sve je napravljeno iz probnih snimki (sintetski glas, umjetna slika), ne iz tvojih klipova. Služi da vidiš kako alat radi; pravu kvalitetu provjeri na svojoj snimci (upute u issueu „Pregled M1").

| Datoteka | Što pokazuje |
|---|---|
| `M1_reel.mp4` | Dva klipa (jedan vodoravni, jedan okomiti) → gotov reel 9:16, stil **suncani**: izrezan prekinuti pokušaj („Danas vam pokazujem kako…") i „eee", hook na početku, naglašene riječi, glazba koja se stiša ispod glasa. Sirovo 24 s → gotovo 15 s. |
| `M1_kadrovi.png` | Provjera izgleda prije rendera (tri kadra gotovog reela), isto što Claude gleda prije nego što montira. |
| `M1_stilovi.mp4` | Isti početak u svih 5 stilova: suncani, podcast, udarno, cisto, kino. |
| `M1_karta_videa.mp4` | Snimka zaslona „karte videa" (`pregled.html`) za probni razgovor od 55 s s tri glasa: klik na najjači trenutak, zum vremenske crte, klik na temu, pretraga transkripta. |
| `M1_karta_videa.png` | Cijela stranica karte videa: govornici u boji, teme, trenuci, tišine, rezovi, tamni dio. |

Napomene:
- Govornike je prepoznao pravi model (na procesoru). Jedna kratka rečenica („Točno tako.", < 1,5 s) dobila je krivog govornika — to je poznato ograničenje za vrlo kratke odgovore.
- Glas je robotski (espeak) jer je sintetski; s pravim glasom titlovi i govornici rade bolje.

Ponovno napraviti: `python tests/make_demo.py` (treba ffmpeg i Playwright s Chromiumom).
