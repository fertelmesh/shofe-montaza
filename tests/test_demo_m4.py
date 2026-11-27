"""Pomoćne funkcije i podaci demo skripte za pregled M4 (tests/make_demo_m4.py); sam demo se ne renderira u CI-ju."""
import re

import make_demo_m4 as demo


def test_scenarij_i_claudeove_ocjene():
    oznake = [b["oznaka"] for b in demo.EPIZODA]
    assert oznake.count("pjesma") == 1 and oznake[0] == "najava"
    assert set(demo.OCJENE) == set(oznake)
    for b in demo.EPIZODA:
        if b["oznaka"] not in ("najava", "pjesma"):
            assert b["tema"] and b["sazetak"] and b["recenice"]
            assert all(g in "AB" and txt and 0 < p <= 2 for g, txt, p in b["recenice"])
    assert set(demo.ODOBRI) <= set(demo.OCJENE)
    assert all(demo.OCJENE[o]["ocjena"] >= 7 and demo.OCJENE[o]["hook"] for o in demo.ODOBRI)


def test_opis_epizode_po_pravilima_platformi():
    yt, pod = demo.YOUTUBE, demo.PODCAST
    vrijeme = re.compile(r"\b\d{1,2}:\d{2}\b")
    assert not vrijeme.search(yt["opis"]) and not vrijeme.search(pod["opis"])     # poglavlja dodaje Shofe
    assert len(yt["hashtagovi"]) <= 3 and all(h.startswith("#") for h in yt["hashtagovi"])
    assert len(pod["naslov"]) <= 150 and "Sunčani4M" not in pod["naslov"] and "12" not in pod["naslov"]
    assert "#" not in pod["opis"] and pod["broj"].isdigit()


def test_kamere_krenule_u_razlicito_vrijeme():
    pomaci = [k["pomak"] for k in demo.KAMERE.values()]
    assert len(set(pomaci)) == len(pomaci) and min(pomaci) < 0 < max(pomaci)
    mob = demo.KAMERE["VID_20261127_ivan.mp4"]
    assert mob["h"] > mob["w"] and mob["kraj"] < 0                       # uspravni mobitel, ugasio se prije kraja
    assert sum(len(k["osobe"]) > 1 for k in demo.KAMERE.values()) == 1    # samo jedna široka kamera


def test_aktivna_kamera_u_mozaiku():
    imena = list(demo.KAMERE)
    kadrovi = [{"od": 0.0, "do": 5.0, "kamera": imena[0]}, {"od": 5.0, "do": 9.0, "kamera": imena[2]},
               {"od": 9.0, "do": 20.0, "kamera": imena[1]}]
    assert demo.aktivne(kadrovi, 4.0, 10.0, imena) == [(0.0, 1.0, 0), (1.0, 5.0, 2), (5.0, 6.0, 1)]
    assert demo.aktivne(kadrovi, 30.0, 40.0, imena) == []


def test_blok_isjecka_i_vrijeme():
    blokovi = [("a", 0.0, 10.0), ("b", 10.5, 30.0)]
    assert demo.blok_isjecka({"od": 9.0, "do": 29.0}, blokovi) == "b"
    assert demo.mmss(103.64) == "1:43.6" and demo.mmss(5.0) == "0:05.0"
