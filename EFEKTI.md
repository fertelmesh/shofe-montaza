# Efekti i grafika (modul 5)

Živa verzija: https://claude.ai/artifact/9KmeLGipJyisdkUQqCEU85

Uzor: konkurentski paket studio.aiprofit.rs ima 85 efekata, 9 stilova montaže i 20 stilova titlova. Ne kopiramo ih (ni imena ni izgled); pokrivamo iste skupine s ~30 dobrih vlastitih efekata.

| Skupina | Njihovi primjeri | Naš pristup | Težina | Vrijednost |
|---|---|---|---|---|
| Kamera i rezovi | Digital Zoom, Zoom-Through Cut, Camera Cuts, Vertigo, Freeze and Label | ffmpeg, proširenje postojećeg zuma | Mala | Visoka |
| Tekst u kadru | Type Wall, Headline Wall, Sticky Text, Letter Stamp, Neon Sign, Hook Stack | HTML predlošci | Srednja | Visoka |
| Brojke i dokaz | Chart Grow, Stat Stack, Odometer, Before and After, Checklist, Receipt Print | HTML predlošci s podacima | Srednja | Visoka (SF klima) |
| Prijelazi | Wipe Set, Page Roll, Iris Card, Grid Snap | ffmpeg xfade + HTML | Mala | Srednja |
| Film i retro | Film Cut, Film Gate, Paper Cut, Split Grade, Doodle Boil | ffmpeg filteri + teksture | Mala | Srednja |
| Mobitel i sučelje | Phone Mockup, Comment Bubble, Comment Flow, Prompt Box, Feed Flick | HTML predlošci | Srednja | Srednja |
| Izdvajanje osobe | Green Screen, Room Swap, Clone, Frame Break, Knockout Tiles | Lokalna AI maska + slojevi | Velika | Visoka |
| 3D i svjetlo | Shatter 3D, Spatial Glass, God Rays, Orbit | three.js u HTML-u | Velika | Niska–srednja |
| Zvuk | Pravila zvuka, uparivanje zvukova | CC0 biblioteka + pravila u stilu | Mala | Visoka |
| GIF-ovi | GIF Finder (Giphy, Tenor) | API pretraga | Srednja | Niska (licence upitne) |

## Tehnička odluka

ffmpeg ostaje za rezove, zvuk, zum i boju. Grafika = HTML predlošci koje renderira **HyperFrames** (HeyGen, Apache-2.0, bez naknada; GSAP, CSS, Lottie, three.js; Node.js 22+). Remotion odbačen: besplatan samo do 3 osobe.

Kako: render.py napravi izrezani video; za svaki efekt HyperFrames renderira samo taj odsječak od 2–4 s (pozadinski video + grafika), ffmpeg ga umeće natrag. Tako render ostaje brz.

Izdvajanje osobe: Robust Video Matting je GPL-3.0 → ne koristimo dok Marko ne odluči o prodaji; tražiti permisivni model (npr. MediaPipe, Apache-2.0) i zapisati u ODLUKE.md.

## Faze (unutar M5)

1. Kamera, prijelazi, zvuk (samo ffmpeg): zumovi (guranje, trzaj, pad, vertigo), zamrzni kadar + oznaka, prijelazi (iris, rolete, vrata), film/retro, CC0 zvučni efekti; Claude bira efekte po tekstu.
2. HTML grafika: 10 predložaka (kartica, ključna rečenica, brojač, graf, popis, prije/poslije, komentar, mobitel, citat, poziv na akciju) + galerija efekata.
3. Izdvajanje osobe: tekst iza osobe, zamjena pozadine, klon.
4. Stilovi: više stilova montaže i titlova; „stil iz uzorka" (Marko pošalje reel, Claude složi stil).
5. Dodaci (kasnije): 3D, GIF pretraga.

## Provjera

Testni komplet (kad Marko doda prave klipove): savjet SF klima, isječak Sunčani4M, najava Sunčano AJMO!, snimka bez lica, dulji YouTube video. Kontrolna lista: lice nije prekriveno, tekst čitljiv na mobitelu, č ć š ž đ ispravni, efekt ne traje dulje od rečenice, zvuk efekta tiši od glasa. Brzina: reel 30 s bez efekata < 3 min na laptopu; svaki HTML efekt + najviše 30 s.
