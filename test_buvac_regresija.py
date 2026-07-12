"""
test_buvac_regresija.py — GARANCIJA da ugrađeni Buvač primjer daje
IDENTIČNE rezultate poslije bilo kakvih izmjena koda.

Referentne vrijednosti su snimljene prije uvođenja dinamičke ekonomije
(cijene zona iz fajla, podesivi koeficijenti transporta/dizanja) i
moraju se poklapati na < 1e-12 relativno. Ako ovaj test padne — izmjena
je promijenila ponašanje za Buvač i to treba svjesno odobriti (i tada
regenerisati referencu), a ne ignorisati.

Pokretanje:  py test_buvac_regresija.py
"""

from __future__ import annotations

import sys

import numpy as np

REFERENCA = {
 "mc_prihvaceno": 177,
 "tacke": [
  None,
  {
   "f": 3.162995634877525,
   "V": 2857958.817364851,
   "eko": 17970.19495306114,
   "c1": 3224540.647967546,
   "c2": 5797200.421064152,
   "zone": "Z-1-5.10,Z-1-5.13,Z-1-5.14,Z-1-5.15,Z-1-5.17,Z-1-6.3,Z-1-6.8,Z-4-1.2,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  {
   "f": 2.53283785508634,
   "V": 2627336.9533861727,
   "eko": 13748.986725188475,
   "c1": 2872499.671954179,
   "c2": 3768369.834924345,
   "zone": "Z-1-3.13,Z-1-3.15,Z-1-4.2,Z-1-4.3,Z-1-4.4,Z-1-4.5,Z-1-4.6,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  None,
  None,
  {
   "f": 2.970930545308654,
   "V": 2343158.0423843614,
   "eko": 17106.535789374077,
   "c1": 2594486.946007175,
   "c2": 4349766.318808779,
   "zone": "Z-1-5.10,Z-1-5.13,Z-1-5.14,Z-1-5.15,Z-1-5.17,Z-1-6.3,Z-4-1.2,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  {
   "f": 2.755441271406931,
   "V": 2591610.834237121,
   "eko": 14618.10592512563,
   "c1": 3420639.449211926,
   "c2": 3705773.896945257,
   "zone": "Z-1-3.17,Z-1-3.18,Z-1-3.19,Z-1-3.20,Z-1-3.21,Z-1-4.9,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  {
   "f": 2.563051075908682,
   "V": 2491725.9101772103,
   "eko": 24926.43839348819,
   "c1": 2301057.066948183,
   "c2": 4060437.269607568,
   "zone": "Z-1-4.17,Z-1-4.18,Z-1-4.22,Z-1-4.23,Z-1-4.26,Z-4-1.5,Z-4-1.6,Z-4-1.8,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  {
   "f": 2.476573464912239,
   "V": 2598406.45369237,
   "eko": 13849.361589020427,
   "c1": 2752250.6642100224,
   "c2": 3669044.448472193,
   "zone": "Z-1-3.19,Z-1-3.22,Z-1-4.10,Z-1-4.11,Z-1-4.15,Z-1-4.16,",
   "petlji": 1,
   "uzeti_deo": ""
  },
  {
   "f": 2.7497557312109,
   "V": 2583603.7078483896,
   "eko": 16351.545257538666,
   "c1": 3727175.8544071186,
   "c2": 3360751.7031691843,
   "zone": "Z-3.6,Z-3.7,Z-3.17,Z-3.18,Z-3.28,Z-3.29,",
   "petlji": 1,
   "uzeti_deo": ""
  }
 ]
}


def main():
    from loaders import (ucitaj_teren, ucitaj_ekonomske_zone,
                         ucitaj_centar_masa, ucitaj_granice_zone)
    from geometrija_v2 import Teren
    from pipeline_v2 import KontekstV2, proracun_tacke, monte_carlo_tacke

    ts = ucitaj_teren("podaci/001-Teren-3-Buvac.txt")
    teren = Teren.iz_tacaka(ts.vertices)
    dobre, lose = ucitaj_ekonomske_zone("podaci/001EkonomskeZoneBuvac.txt")
    cm = ucitaj_centar_masa("podaci/001CentarMasaBuvac.txt")
    gr = ucitaj_granice_zone("podaci/001GranicaZonaBuvac.txt")

    # NAPOMENA: bez eksplicitnih ekonomskih koeficijenata — defaulti
    # moraju reproducirati MATLAB original bit-za-bit
    ctx = KontekstV2(teren=teren, zona_x=gr.x_poly, zona_y=gr.y_poly,
                     dobre_zone=dobre, centar_masa=cm, mnv=140.0,
                     donja_granica_zapremine=100_000,
                     gornja_granica_zapremine=39_000_000,
                     uslov_distance=2000.0, rezolucija=160, rafiniranje=1,
                     lose_zone=lose)

    mc = monte_carlo_tacke(300, teren, gr.x_poly, gr.y_poly, centar_masa=cm,
                           uslov_distance=2000.0, lose_zone=lose, seed=42)
    P = mc.prihvacene
    assert len(P) == REFERENCA["mc_prihvaceno"], \
        f"MC prihvaćeno {len(P)} != {REFERENCA['mc_prihvaceno']}"

    max_rel, palo = 0.0, 0
    for i, stari in enumerate(REFERENCA["tacke"]):
        x, y = float(P[i, 0]), float(P[i, 1])
        r = proracun_tacke(f"p{i}", x, y, ctx, mod="fiksno",
                           wz_fiksno=float(teren.z(x, y)) + 40.0,
                           k_fiksno=100)
        if stari is None:
            if r is not None:
                print(f"  ✗ tačka {i}: sada dopustiva, prije nije")
                palo += 1
            continue
        if r is None:
            print(f"  ✗ tačka {i}: sada nedopustiva, prije jeste")
            palo += 1
            continue
        novo = {"f": r.f_vrednost, "V": r.zapremina, "eko": r.c3,
                "c1": r.c1, "c2": r.c2}
        for kljuc, vr in novo.items():
            rel = abs(vr - stari[kljuc]) / max(abs(stari[kljuc]), 1e-12)
            max_rel = max(max_rel, rel)
            if rel >= 1e-12:
                print(f"  ✗ tačka {i} {kljuc}: {vr!r} != {stari[kljuc]!r}")
                palo += 1
        if r.zone != stari["zone"] or r.broj_petlji != stari["petlji"] \
                or r.uzeti_deo != stari["uzeti_deo"]:
            print(f"  ✗ tačka {i}: zone/petlje/deo razlika")
            palo += 1

    print("=" * 60)
    if palo == 0:
        print(f"BUVAČ REGRESIJA: svih {len(REFERENCA['tacke'])} tačaka "
              f"IDENTIČNO (max rel. razlika {max_rel:.2e})")
    else:
        print(f"BUVAČ REGRESIJA: {palo} PROVJERA PALO — ponašanje za "
              f"Buvač je promijenjeno!")
    print("=" * 60)
    sys.exit(0 if palo == 0 else 1)


if __name__ == "__main__":
    main()
