"""
test_analiza_delova.py — testovi analize delova presjeka (više petlji).

Scenario: ravan teren z = 100 sa grebenom visine 60 m po liniji x = 500 —
greben dijeli footprint kupe na dva dela (A lijevo, B desno), kao kada
rijeka/greben presiječe odlagalište na Buvču.

Provjerava se:
  1. analiza_delova: suma zapremina delova = ukupna zapremina presjeka;
     oznake A, B po opadajućoj zapremini; svaki deo ima konture i centar.
  2. _evaluiraj/proracun_tacke: kada zona pokriva sve → uzima se A;
     kada zona pokriva samo desno → A odbačen (zona), uzima se B;
     kada nijedan deo ne dostiže V_min → tačka nedopustiva (None).
  3. Red tabele ima istu dužinu kao ZAGLAVLJE i sadrži Uzeti_deo/Delovi.

Pokretanje:  py test_analiza_delova.py
"""

from __future__ import annotations

import sys

import numpy as np

from geometrija_v2 import Kupa, Teren, analiza_delova, presek_kupe_i_terena
from pipeline_v2 import KontekstV2, RezultatTackeV2, proracun_tacke

PROSLO = PALO = 0


def ok(uslov: bool, poruka: str):
    global PROSLO, PALO
    if uslov:
        PROSLO += 1
        print(f"  ✓ {poruka}")
    else:
        PALO += 1
        print(f"  ✗ {poruka}")


def teren_sa_grebenom() -> Teren:
    xs, ys = np.meshgrid(np.linspace(0, 1000, 80),
                         np.linspace(0, 1000, 80))
    z = np.full_like(xs, 100.0) + 60 * np.exp(-((xs - 500) / 20) ** 2)
    return Teren.iz_tacaka(np.column_stack([xs.ravel(), ys.ravel(),
                                            z.ravel()]))


def ctx_za(teren: Teren, zona: np.ndarray, v_min: float = 1000.0,
           cm=(100.0, 500.0)) -> KontekstV2:
    return KontekstV2(teren=teren, zona_x=zona[:, 0], zona_y=zona[:, 1],
                      dobre_zone=[], centar_masa=np.asarray(cm, float),
                      mnv=100.0, donja_granica_zapremine=v_min,
                      gornja_granica_zapremine=39_000_000.0,
                      rezolucija=192, rafiniranje=1)


def main():
    teren = teren_sa_grebenom()
    kupa = Kupa(wx=470, wy=500, wz=140, k=60, ugao=37, profil="matlab")

    print("[1] analiza_delova — podjela i bilans zapremine")
    rez = presek_kupe_i_terena(kupa, teren, rezolucija=192, rafiniranje=1)
    delovi = analiza_delova(kupa, teren, rezolucija=192, rafiniranje=1)
    ok(rez.broj_petlji >= 2, f"presjek ima više petlji ({rez.broj_petlji})")
    ok(len(delovi) == 2, f"dva povezana dela ({len(delovi)})")
    suma = sum(d.zapremina for d in delovi)
    ok(abs(suma - rez.zapremina) / rez.zapremina < 1e-6,
       f"suma delova = ukupna zapremina ({suma:,.0f} m³)")
    ok(delovi[0].oznaka == "A" and delovi[1].oznaka == "B",
       "oznake A, B po opadajućoj zapremini")
    ok(delovi[0].zapremina > delovi[1].zapremina, "A je veći deo")
    ok(all(d.konture for d in delovi), "svaki deo ima svoje konture")
    ok(all(len(d.centar) == 3 for d in delovi),
       "svaki deo ima centar (x, y, z) za oznaku na prikazu")

    print("[2] izbor dela — zona pokriva SVE → uzima se A")
    zona_sve = np.array([[0, 0], [1000, 0], [1000, 1000], [0, 1000],
                         [0, 0]], float)
    r = proracun_tacke("t_sve", 470, 500, ctx_za(teren, zona_sve),
                       mod="fiksno", wz_fiksno=140, k_fiksno=60)
    ok(r is not None, "tačka dopustiva")
    ok(r.uzeti_deo == "A", f"uzet deo A (uzet: {r.uzeti_deo})")
    ok(len(r.delovi) == 2, "sačuvana analiza oba dela")
    ok(r.broj_petlji >= 2, "Petlji = ukupan broj petlji presjeka")
    ok("UZET" in r.delovi_opis and "✗" in r.delovi_opis,
       f"opis delova za tabelu: {r.delovi_opis}")

    print("[3] izbor dela — zona samo DESNO → A odbačen (zona), uzima se B")
    zona_desno = np.array([[512, 0], [1000, 0], [1000, 1000], [512, 1000],
                           [512, 0]], float)
    r2 = proracun_tacke("t_desno", 470, 500,
                        ctx_za(teren, zona_desno, cm=(900.0, 500.0)),
                        mod="fiksno", wz_fiksno=140, k_fiksno=60)
    ok(r2 is not None, "tačka dopustiva preko dela B")
    ok(r2.uzeti_deo == "B", f"uzet deo B (uzet: {r2.uzeti_deo})")
    deo_a = next(d for d in r2.delovi if d["oznaka"] == "A")
    ok(not deo_a["uzet"] and deo_a["razlog"] == "zona",
       f"A odbačen sa razlogom 'zona' (razlog: {deo_a['razlog']!r})")
    ok(r2.zapremina < deo_a["zapremina"],
       "zapremina rezultata je zapremina dela B (manja od A)")
    ok(len(r2.konture) == len(next(d for d in r2.delovi
                                   if d["oznaka"] == "B")["konture"]),
       "konture rezultata = konture uzetog dela (za DXF/prikaz)")

    print("[4] nijedan deo ne dostiže V_min → tačka nedopustiva")
    r3 = proracun_tacke("t_vmin", 470, 500,
                        ctx_za(teren, zona_sve, v_min=5_000_000.0),
                        mod="fiksno", wz_fiksno=140, k_fiksno=60)
    ok(r3 is None, "rezultat je None")

    print("[5] tabela — red i zaglavlje")
    red = r.kao_red()
    ok(len(red) == len(RezultatTackeV2.ZAGLAVLJE),
       f"dužina reda = dužina zaglavlja ({len(red)})")
    i_uzeti = RezultatTackeV2.ZAGLAVLJE.index("Uzeti_deo")
    i_delovi = RezultatTackeV2.ZAGLAVLJE.index("Delovi")
    ok(red[i_uzeti] == "A", "kolona Uzeti_deo popunjena")
    ok("m³" in red[i_delovi], "kolona Delovi popunjena")

    print("[6] jednodelan presjek — ponašanje kao prije")
    kupa1 = Kupa(wx=200, wy=500, wz=140, k=60, ugao=37)  # daleko od grebena
    rez1 = presek_kupe_i_terena(kupa1, teren, rezolucija=192, rafiniranje=1)
    r4 = proracun_tacke("t_jedan", 200, 500, ctx_za(teren, zona_sve),
                        mod="fiksno", wz_fiksno=140, k_fiksno=60)
    ok(rez1.broj_petlji == 1, "presjek ima jednu petlju")
    ok(r4 is not None and r4.uzeti_deo == "" and not r4.delovi,
       "uzeti_deo prazan, delovi prazni (klasična ocjena)")

    print("=" * 60)
    print(f"UKUPNO: {PROSLO} prošlo, {PALO} palo")
    print("=" * 60)
    sys.exit(0 if PALO == 0 else 1)


if __name__ == "__main__":
    main()
