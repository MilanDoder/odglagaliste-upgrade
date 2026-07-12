"""
ekonomija.py  –  Korak 3a: ekonomski proračun

Zamjenjuje MATLAB funkcije:
  proracunEkonomskeCene.m                   → ekonomska_cijena()
  proracunEkonomskeCeneSaKoeficijentom.m    → cijena_zone()
  distancaOdCentraMasa.m                    → distanca_od_centra_masa()

Sve formule su direktno prenesene iz MATLAB koda.
Nema globalnih varijabli — podaci se prosleđuju eksplicitno.
"""

from __future__ import annotations

import numpy as np
from matplotlib.path import Path as MplPath

from geometry import Surface, inpolygon


# ---------------------------------------------------------------------------
# Koeficijenti cijena  (hardkodirani u proracunEkonomskeCeneSaKoeficijentom.m)
# Izvučeni ovdje u jednu konstantnu strukturu — lako mijenjati
# ---------------------------------------------------------------------------

# Bazne cijene po m²
CENA1 = 0.5    # skupo  (Z-4)
CENA2 = 0.3    # srednje (Z-1-7, Z-5)
CENA3 = 0.15   # jeftino (Z-1-1..6, Z-3)

# Koeficijenti (multiplikatori za kategorije rizika/troška)
K1  = 0.505
K2  = 0.252
K3  = 0.126
K4  = 0.084
K51 = 0.016
K52 = 0.005
K53 = 0.011

# Mapa: prefiks zone → formula  (lambda prima površinu, vraća cijenu)
# Direktno odgovara if-elseif lancu u MATLAB kodu
ZONA_FORMULA: dict[str, object] = {
    "Z-1-1": lambda p: CENA3 * p * (1 + K4),
    "Z-1-2": lambda p: CENA3 * p * (1 + K4),
    "Z-1-3": lambda p: CENA3 * p * (1 + K4),
    "Z-1-4": lambda p: CENA3 * p * (1 + K52),
    "Z-1-5": lambda p: CENA3 * p * (1 + K52),
    "Z-1-6": lambda p: CENA3 * p * (1 + K51),
    "Z-1-7": lambda p: CENA2 * p * (1 + K53),
    "Z-3":   lambda p: CENA3 * p * (1 + K4 + K3),
    "Z-4-1": lambda p: CENA1 * p * (1 + K2),
    "Z-4-2": lambda p: CENA1 * p * (1 + K2 + K4),
    "Z-5":   lambda p: CENA2 * p * (1 + K1 + K4),
    "K-5":   lambda p: CENA2 * p * (1 + K1 + K4),
}


def cijena_zone(naziv: str, povrsina: float,
                cena_m2: float | None = None) -> float:
    """Računa ekonomsku cijenu jedne zone.

    Prioritet:
      1. Buvač nazivi (Z-1-*, Z-3, Z-4-*, Z-5, K-5) → hardkodirana
         MATLAB formula — NEPROMIJENJENO, garantuje iste rezultate
         za ugrađeni Buvač primjer.
      2. Ostali nazivi → cijena iz fajla zona: cena_m2 [valuta/m²] ×
         površina — omogućava bilo koju lokaciju sa klijentskim
         cjenovnikom.
      3. Bez formule i bez cijene → 0 (zemljište bez troška).

    Args:
        naziv:    naziv zone, npr. "Z-1-1.5" ili "PARCELA-12"
        povrsina: zahvaćena površina u m²
        cena_m2:  cijena po m² iz fajla zona (2. linija bloka zone)
    """
    for prefiks, formula in ZONA_FORMULA.items():
        if naziv.startswith(prefiks):
            return float(formula(povrsina))
    if cena_m2 is not None and np.isfinite(cena_m2) and cena_m2 > 0:
        return float(cena_m2) * float(povrsina)
    return 0.0


def _presjeciste_poligona_xy(
    tacke_xy: np.ndarray,
    zona_x: np.ndarray,
    zona_y: np.ndarray,
) -> float:
    """Računa površinu presječišta skupa tačaka sa zonskim poligonom.

    Koristi masku tačaka umjesto scipy/shapely presječišta poligona —
    efikasno za konturne provjere.

    Napomena: Za precizno presječište poligona potrebna bi bila shapely.
    Ovde koristimo konzervativnu aproksimaciju: površina kao ConvexHull
    tačaka koje su unutar zone.
    """
    if len(tacke_xy) == 0:
        return 0.0

    maska = inpolygon(tacke_xy[:, 0], tacke_xy[:, 1], zona_x, zona_y)
    unutra = tacke_xy[maska]

    if len(unutra) < 3:
        return 0.0

    # Površina ConvexHull tačaka unutar zone — aproksimacija
    try:
        from scipy.spatial import ConvexHull
        hull = ConvexHull(unutra)
        return hull.volume   # u 2D: volume = površina
    except Exception:
        return 0.0


def ekonomska_cijena(
    intersect_surface: Surface,
    dobre_zone: list,
) -> tuple[float, str]:
    """Računa ukupnu ekonomsku cijenu kupe na osnovu presječišnih zona.

    MATLAB ekvivalent: proracunEkonomskeCene(SurfaceIntersection)

    Algoritam:
    1. Uzmi XY tačke presječišta kupe i terena
    2. Za svaku dobru ekonomsku zonu provjeri presječište
    3. Saberi cijene svih zona koje se sijeku sa kupom

    Args:
        intersect_surface: presječišna površina (kupa ∩ teren)
        dobre_zone:        lista EkonomskaZona objekata

    Returns:
        (ukupna_cijena, string_zona)  — npr. (12345.6, "Z-1-1.3,Z-3.7,")
    """
    if intersect_surface is None or intersect_surface.vertices.shape[0] == 0:
        return 0.0, ""

    x_int = intersect_surface.vertices[:, 0]
    y_int = intersect_surface.vertices[:, 1]
    tacke_int = np.column_stack([x_int, y_int])

    ukupna_cijena = 0.0
    zone_lista: list[str] = []

    for zona in dobre_zone:
        # Provjeri da li ijedna presječišna tačka pada u ovu zonu
        maska = inpolygon(x_int, y_int, zona.x_data, zona.y_data)
        if not np.any(maska):
            continue

        # Ima presječišta — dodaj cijenu te zone
        eko_vrednost = cijena_zone(zona.naziv, zona.povrsina)
        ukupna_cijena += eko_vrednost
        zone_lista.append(zona.naziv)

    zone_str = ",".join(zone_lista) + ("," if zone_lista else "")
    return ukupna_cijena, zone_str


# ---------------------------------------------------------------------------
# Distanca od centra masa  (zamjenjuje distancaOdCentraMasa.m)
# ---------------------------------------------------------------------------

def distanca_od_centra_masa(
    x: float, y: float,
    centar_masa: np.ndarray,
) -> float:
    """Računa euklidsku distancu tačke od centra masa u XY ravni.

    MATLAB ekvivalent:
        distancaTacke = [x, y];
        X = [centarMasa(1:2); distancaTacke];
        distanca = pdist(X, 'euclidean');

    Args:
        x, y:        koordinate tačke
        centar_masa: array [X, Y, Z] centra masa (Z se ignoriše)

    Returns:
        Euklidska distanca u metrima
    """
    cm_x, cm_y = float(centar_masa[0]), float(centar_masa[1])
    return float(np.sqrt((x - cm_x) ** 2 + (y - cm_y) ** 2))


# ---------------------------------------------------------------------------
# Troškovne komponente  (c1, c2, c3 iz post-procesiranja u MATLAB)
# ---------------------------------------------------------------------------

def racunaj_troskove(
    zapremina: float,
    distanca: float,
    wz: float,
    ekonomska_cena: float,
    mnv: float = None,
    cijena_transporta: float = 0.8,
    cijena_dizanja: float = 1.6 * 1.2 / (0.08 * 1000.0),
) -> tuple[float, float, float]:
    """Računa tri troškovne komponente za jedan rezultat GA.

    MATLAB ekvivalent (iz IzvrsniKodBuvac.m post-procesiranje):
        c1 = zapreminaK * (d1/1000) * 0.8
        c2 = zapreminaK * (((wz - mnv) / 0.08 * 1.6) / 1000) * 1.2
        c3 = getEkonomskaVrednostZemljista()

    NAPOMENA: U originalnom MATLAB kodu stajalo je (wz - 90) gdje je 90
    bila zakucana nadmorska visina baze Buvac kopa. Ovdje koristimo mnv
    (nadmorska visina baze) iz DodatniUlazniParametri — ispravno za
    bilo koji teren.

    Args:
        zapremina:      zapremina kupe u m³
        distanca:       distanca od centra masa u m
        wz:             visina vrha kupe (Z koordinata)
        ekonomska_cena: cijena zemljišta iz ekonomska_cijena()
        mnv:            nadmorska visina baze kupe (iz DodatniParametri)
                        Ako None, koristi se 0 (neutralno)

    Returns:
        (c1, c2, c3)
        c1 = transportni trošak (zapremina × distanca)
        c2 = trošak iskapanja   (zapremina × visinska razlika)
        c3 = vrijednost zemljišta (ekonomska cijena)
    """
    referentna_visina = mnv if mnv is not None else 0.0
    c1 = zapremina * (distanca / 1000) * cijena_transporta
    # napisano tako da je za default BIT-identično MATLAB originalu,
    # a za proizvoljan koeficijent: c2 = V · (wz − mnv) · cijena_dizanja
    c2 = zapremina * (((wz - referentna_visina) / 0.08 * 1.6) / 1000) \
         * (cijena_dizanja / (1.6 / (0.08 * 1000.0)))
    c3 = ekonomska_cena
    return c1, c2, c3
