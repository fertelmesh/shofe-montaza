"""Pomoćne funkcije demo skripte za pregled M2 (tests/make_demo_m2.py); sam demo se ne renderira u CI-ju."""
import make_demo_m2 as demo


def test_prijevod_pokriva_sve_recenice():
    hr = [t for t, _ in demo.SKUP["recenice"]]
    # prekinuti pokušaj uvoda nikad nije u gotovom videu, ostale rečenice moraju imati prijevod
    nedostaje = [t for t in hr if t not in demo.EN and t != "Danas vam pokazujem tri"]
    assert not nedostaje
    assert all(len(en) <= 84 for en in demo.EN.values())  # 2 retka × 42 znaka


def test_vremena():
    assert demo.t_str("00:43.17") == "0:43,2"
    assert demo.t_str("01:05.04") == "1:05,0"
    assert demo.mmss(10.5) == "0:10,5"
    assert abs(demo.sek("1001/1875s") - 0.533867) < 1e-5
    assert demo.sek("0s") == 0
    assert demo.tc(1001 / 1875, 30000 / 1001) == "00:00:00:16"
    assert demo.tc(3600 + 61.5, 30) == "01:01:01:15"


def test_kartica_escape():
    body = demo.kartica(0, "KORAK", "Makni <b> & „ovo“", [demo.ln("van", demo.q("a < b"))], "verzija 2",
                        ("0:43,2", "0:32,6"))
    assert "&lt;b&gt; &amp;" in body and "a &lt; b" in body and "0:43,2 → 0:32,6" in body
