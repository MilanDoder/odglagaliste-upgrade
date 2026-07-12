"""
test_nova_lokacija.py — dokaz da aplikacija radi za BILO KOJU lokaciju.

Pravi kompletnu sintetičku lokaciju u klijentskom formatu (teren, granica
interesne zone, centar masa, ekonomske zone sa PROIZVOLJNIM nazivima i
cijenama iz fajla, dodatni parametri sa ekonomskim koeficijentima),
učitava je ISTIM loaderima kao aplikacija i pušta pipeline.

Provjerava se:
  1. Loader prihvata proizvoljne nazive zona ("PARCELA-12", "LIVADA A"...)
     i klasifikuje: "ZABRANJENA-*" i "K-*" → loše, ostalo → dobre.
  2. Cijena zemljišta = cijena_iz_fajla [valuta/m²] × zahvaćena površina
     (Buvač nazivi i dalje idu kroz MATLAB formule — vidi
     test_buvac_regresija.py).
  3. Ekonomski koeficijenti iz fajla parametara (4. i 5. broj) ulaze u
     funkciju cilja: c1 = dist_km·kt·V, c2 = V·h·kd.
  4. Kupa koja zahvata zabranjenu zonu se odbacuje.

Pokretanje:  py test_nova_lokacija.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

PROSLO = PALO = 0


def ok(uslov: bool, poruka: str):
    global PROSLO, PALO
    if uslov:
        PROSLO += 1
        print(f"  ✓ {poruka}")
    else:
        PALO += 1
        print(f"  ✗ {poruka}")


def _poligon_str(xs, ys):
    return (",".join(f"{v:.2f}" for v in xs),
            ",".join(f"{v:.2f}" for v in ys))


def napravi_lokaciju(d: Path):
    """Sintetička lokacija 'Livada': ravan teren 1×1 km na koti 300 m."""
    # teren: mreža 60×60, blagi nagib
    xs, ys = np.meshgrid(np.linspace(0, 1000, 60), np.linspace(0, 1000, 60))
    zs = 300.0 + 0.01 * xs
    with open(d / "teren.txt", "w") as f:
        for x, y, z in zip(xs.ravel(), ys.ravel(), zs.ravel()):
            f.write(f"{x:.2f},{y:.2f},{z:.2f}\n")

    # granica interesne zone: bbox min/max pa poligon (kvadrat 100..900)
    with open(d / "granica.txt", "w") as f:
        f.write("100,100,290\n900,900,320\n")
        for x, y in [(100, 100), (900, 100), (900, 900), (100, 900),
                     (100, 100)]:
            f.write(f"{x},{y},300\n")

    with open(d / "cm.txt", "w") as f:
        f.write("500,950\n")

    # ekonomske zone — KLIJENTSKI nazivi i cijene po m² u fajlu
    with open(d / "zone.txt", "w") as f:
        gx, gy = _poligon_str([100, 550, 550, 100], [100, 100, 900, 900])
        f.write(f"PARCELA-12\n2.5\n360000\n{gx}\n{gy}\n")          # 2.5/m²
        gx, gy = _poligon_str([550, 900, 900, 550], [100, 100, 620, 620])
        f.write(f"LIVADA A\n0.7\n182000\n{gx}\n{gy}\n")            # 0.7/m²
        gx, gy = _poligon_str([550, 900, 900, 550], [640, 640, 900, 900])
        f.write(f"ZABRANJENA-3\n0\n91000\n{gx}\n{gy}\n")           # zabranjena
        gx, gy = _poligon_str([0, 40, 40, 0], [0, 0, 40, 40])
        f.write(f"K-7\n0\n1600\n{gx}\n{gy}\n")                     # zabranjena

    # parametri: mv, generacije, distanca + NOVO: transport, dizanje
    with open(d / "par.txt", "w") as f:
        f.write("%% mv\n300\n%% generacije\n3\n%% distanca\n5000\n"
                "%% cijena transporta [valuta/(m3*km)]\n1.5\n"
                "%% cijena dizanja [valuta/(m3*m)]\n0.05\n")


def main():
    from loaders import (ucitaj_teren, ucitaj_ekonomske_zone,
                         ucitaj_centar_masa, ucitaj_granice_zone,
                         ucitaj_dodatne_parametre)
    from geometrija_v2 import Teren
    from ekonomija import cijena_zone
    from pipeline_v2 import KontekstV2, proracun_tacke

    d = Path(tempfile.mkdtemp())
    napravi_lokaciju(d)

    print("[1] loaderi — klijentski format")
    ts = ucitaj_teren(d / "teren.txt")
    teren = Teren.iz_tacaka(ts.vertices)
    dobre, lose = ucitaj_ekonomske_zone(d / "zone.txt")
    cm = ucitaj_centar_masa(d / "cm.txt")
    gr = ucitaj_granice_zone(d / "granica.txt")
    par = ucitaj_dodatne_parametre(d / "par.txt")
    ok(len(dobre) == 2 and {z.naziv for z in dobre} ==
       {"PARCELA-12", "LIVADA A"}, "proizvoljni nazivi dobrih zona prihvaćeni")
    ok(len(lose) == 2 and {z.naziv for z in lose} ==
       {"ZABRANJENA-3", "K-7"},
       "ZABRANJENA-* i K-* klasifikovane kao zabranjene")
    ok(par.cijena_transporta == 1.5 and par.cijena_dizanja == 0.05,
       "ekonomski koeficijenti pročitani iz fajla parametara")

    print("[2] cijena zemljišta iz fajla (valuta/m² × površina)")
    ok(cijena_zone("PARCELA-12", 10_000.0, 2.5) == 25_000.0,
       "nepoznat naziv → cijena iz fajla")
    ok(cijena_zone("Z-3.1", 10_000.0, 99.0) ==
       cijena_zone("Z-3.1", 10_000.0),
       "Buvač naziv → MATLAB formula (cijena iz fajla se ignoriše)")
    ok(cijena_zone("NEPOZNATA", 10_000.0, None) == 0.0,
       "bez formule i bez cijene → 0")

    print("[3] pipeline na novoj lokaciji")
    ctx = KontekstV2(teren=teren, zona_x=gr.x_poly, zona_y=gr.y_poly,
                     dobre_zone=dobre, centar_masa=cm,
                     mnv=float(par.nadmorska_visina),
                     donja_granica_zapremine=1000,
                     gornja_granica_zapremine=39_000_000,
                     uslov_distance=float(par.uslov_distance),
                     rezolucija=160, rafiniranje=1, lose_zone=lose,
                     cijena_transporta=float(par.cijena_transporta),
                     cijena_dizanja=float(par.cijena_dizanja))
    r = proracun_tacke("t1", 330, 400, ctx, mod="fiksno",
                       wz_fiksno=float(teren.z(330, 400)) + 30, k_fiksno=60)
    ok(r is not None, "tačka u PARCELA-12 dopustiva")
    if r:
        ok("PARCELA-12" in r.zone, f"zona prepoznata ({r.zone})")
        ok(r.c3 > 0, f"cijena zemljišta iz fajla > 0 ({r.c3:,.0f})")
        # c1 = dist_km · kt · V ;  c2 = V · h · kd
        dist_km = r.distanca / 1000.0
        ok(abs(r.c1 - dist_km * 1.5 * r.zapremina) / r.c1 < 1e-9,
           "c1 koristi transport=1.5 iz fajla")
        h = r.wz - float(par.nadmorska_visina)
        ok(abs(r.c2 - r.zapremina * h * 0.05) / max(r.c2, 1) < 1e-9,
           "c2 koristi dizanje=0.05 iz fajla")

    print("[4] zabranjena zona odbija kupu")
    r2 = proracun_tacke("t2", 725, 770, ctx, mod="fiksno",
                        wz_fiksno=float(teren.z(725, 770)) + 30, k_fiksno=60)
    ok(r2 is None, "tačka u ZABRANJENA-3 nedopustiva")

    print("=" * 60)
    print(f"UKUPNO: {PROSLO} prošlo, {PALO} palo")
    print("=" * 60)
    sys.exit(0 if PALO == 0 else 1)


if __name__ == "__main__":
    main()
