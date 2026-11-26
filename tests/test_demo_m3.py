"""Pomoćne funkcije i podaci demo skripte za pregled M3 (tests/make_demo_m3.py); sam demo se ne renderira u CI-ju."""
import make_demo_m3 as demo


def test_claude_ocijeni_svaki_blok_epizode():
    oznake = {b["oznaka"] for b in demo.RAZGOVOR["blokovi"]}
    assert set(demo.CLAUDE) == oznake
    dobri = {b["oznaka"] for b in demo.RAZGOVOR["blokovi"] if b["dobar"]}
    assert all(demo.CLAUDE[o]["ocjena"] >= 7 and demo.CLAUDE[o]["hook"] for o in dobri)
    assert all(demo.CLAUDE[o]["ocjena"] <= 3 for o in oznake - dobri)
    assert set(demo.ODOBRI) <= dobri and not set(demo.ODOBRI) & set(demo.ODBACI)


def test_tekstovi_po_pravilima_mreza():
    for o in demo.ODOBRI:
        m = demo.OBJAVA[o]
        assert set(m) == {"instagram", "tiktok", "youtube"}
        for mreza, t in m.items():
            assert len(t["hashtagovi"]) <= 3                # + 2 stalna hashtaga serije = najviše 5
            assert all(h.startswith("#") and h.isascii() for h in t["hashtagovi"])
        assert len(m["youtube"]["naslov"]) <= 60 and "<" not in m["youtube"]["opis"]
        assert 2 <= len(demo.NASLOVNA[o].split()) <= 5


def test_okviri_kadra():
    kadrovi = [{"od": 0.0, "do": 3.7, "crop_x": 0.0}, {"od": 3.7, "do": 5.5, "crop_x": 1.0},
               {"od": 5.5, "do": 9.0, "crop_x": 0.5}]
    o = demo.okviri_kadra(kadrovi, 3.0, 6.0)
    w = round(demo.VH * 9 / 16 * demo.OW / demo.VW)
    assert [(a, b) for a, b, _, _ in o] == [(0.0, 0.7), (0.7, 2.5), (2.5, 3.0)]
    assert o[0][2] == 0 and o[1][2] == demo.OW - w and abs(o[2][2] - (demo.OW - w) / 2) <= 1
    assert all(x[3] == w for x in o)
    assert demo.okviri_kadra(kadrovi, 10, 12) == []


def test_blok_isjecka_i_vrijeme():
    blokovi = [("a", 0.0, 10.0), ("b", 10.5, 30.0), ("c", 31.0, 50.0)]
    assert demo.blok_isjecka({"od": 9.0, "do": 29.0}, blokovi) == "b"
    assert demo.blok_isjecka({"od": 25.0, "do": 49.0}, blokovi) == "c"
    assert demo.mmss(0) == "0:00" and demo.mmss(117.9) == "1:57"
