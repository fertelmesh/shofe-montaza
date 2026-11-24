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

Svaka verzija se sprema kao `reel_v1.mp4`, `reel_v2.mp4`... u mapi `shofe_projekt`. Originalni klipovi se nikad ne diraju.

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
