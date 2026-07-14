"""
naplata.py — dnevna kvota besplatnih testiranja + placeholder za plaćanje.

Logika (bez stvarnog platnog sistema, spremno za kasniju integraciju):

  * svaki korisnik ima DNEVNI_BESPLATNI (5) besplatnih "testiranja" dnevno;
  * "testiranje" = pokretanje proračuna (metode u BILLABLE — GA/Fiksna kupa);
    Monte Carlo generisanje tačaka je priprema i NE troši kvotu;
  * kvota se obnavlja svaki dan (računa se po UTC datumu, isto kao evidencija);
  * admin i "paid"/"pretplatnik" role imaju neograničeno;
  * kad se kvota potroši → paywall() umjesto pokretanja.

Brojanje se izvodi iz postojeće `zahtjevi` evidencije (Supabase ili lokalni
zahtjevi.csv), pa nema nove tabele/migracije. Kad zakačiš pravi platni
sistem (Stripe/Paddle/…), dovoljno je:
  1) u paywall() zamijeniti "demo plaćanje" stvarnim checkout-om;
  2) po uspješnoj uplati postaviti trajni plan korisniku (npr. dodati rolu
     "paid" preko supabase_db.sacuvaj_korisnika) umjesto sesijske oznake.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

log = logging.getLogger("odlagaliste")

# ----------------------------------------------------------------------------
# PODEŠAVANJA
# ----------------------------------------------------------------------------
DNEVNI_BESPLATNI = 5                       # broj besplatnih testiranja dnevno
BILLABLE = {"Genetski algoritam", "Fiksna kupa"}   # šta troši kvotu
NEOGRANICENE_ROLE = {"admin", "paid", "pretplatnik"}
CIJENA_PO_TESTU = 1.0                      # informativno (demo cjenovnik)
VALUTA = "KM"

ZAHTJEVI = Path(__file__).with_name("zahtjevi.csv")   # lokalni fallback

try:
    import supabase_db as sdb
except Exception:
    sdb = None


def _sb() -> bool:
    return sdb is not None and sdb.aktivan()


def _danas_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _dodatak(korisnik: str) -> tuple[int, bool]:
    """(kupljena dodatna testiranja danas, ima li 'neograničeno' za danas).
    Iz Supabase-a ako je aktivan; inače sesijski fallback (demo bez baze)."""
    danas = _danas_utc()
    if _sb():
        try:
            return sdb.kvota_dodatak(korisnik, danas)
        except Exception:
            log.debug("čitanje kvota_dodatak palo", exc_info=True)
    suma = int(st.session_state.get("_dodatno_" + danas, 0))
    neogr = st.session_state.get("_placeno_do") == danas
    return suma, neogr


def _upisi_kupovinu(korisnik: str, broj: int | None) -> None:
    """Trajno zabilježi kupovinu (broj=None → neograničeno danas).
    U bazu ako je aktivna; inače u sesiju."""
    danas = _danas_utc()
    if _sb() and sdb.dodaj_kvotu(korisnik, danas, broj):
        return
    if broj is None:
        st.session_state["_placeno_do"] = danas
    else:
        kljuc = "_dodatno_" + danas
        st.session_state[kljuc] = int(st.session_state.get(kljuc, 0)) + int(broj)


# ----------------------------------------------------------------------------
# PLAN I KVOTA
# ----------------------------------------------------------------------------
def plan_korisnika(korisnik: str) -> str:
    """'neograniceno' (admin/paid ili plaćeno u ovoj sesiji) ili 'besplatno'."""
    try:
        from auth import sve_uloge
        if NEOGRANICENE_ROLE & set(sve_uloge(korisnik)):
            return "neograniceno"
    except Exception:
        log.debug("plan_korisnika: čitanje uloga palo", exc_info=True)
    # kupljeno "neograničeno danas" (baza; sesija kao fallback)
    if _dodatak(korisnik)[1]:
        return "neograniceno"
    return "besplatno"


def _broj_danas_lokalno(korisnik: str, danas: str) -> int:
    if not ZAHTJEVI.exists():
        return 0
    n = 0
    try:
        with open(ZAHTJEVI, encoding="utf-8") as f:
            for red in csv.DictReader(f):
                if (red.get("korisnik") == korisnik
                        and (red.get("vrijeme_utc", "")[:10] == danas)
                        and red.get("metoda") in BILLABLE):
                    n += 1
    except OSError:
        log.debug("čitanje zahtjevi.csv za kvotu nije uspjelo", exc_info=True)
    return n


def broj_danas(korisnik: str) -> int:
    """Koliko je billable testiranja korisnik pokrenuo danas (UTC)."""
    danas = _danas_utc()
    if _sb():
        try:
            return sdb.broj_zahtjeva_danas(korisnik, danas, sorted(BILLABLE))
        except Exception:
            log.debug("brojanje kvote iz Supabase-a palo", exc_info=True)
    return _broj_danas_lokalno(korisnik, danas)


def status(korisnik: str) -> dict:
    """Sažetak kvote: plan, iskorišćeno, limit, preostalo, može."""
    plan = plan_korisnika(korisnik)
    if plan == "neograniceno":
        return {"plan": plan, "limit": None,
                "iskorisceno": 0, "preostalo": None, "moze": True}
    isk = broj_danas(korisnik)
    limit = DNEVNI_BESPLATNI + _dodatak(korisnik)[0]
    preostalo = max(0, limit - isk)
    return {"plan": plan, "limit": limit, "iskorisceno": isk,
            "preostalo": preostalo, "moze": preostalo > 0}


def moze_pokrenuti(korisnik: str) -> bool:
    return status(korisnik)["moze"]


# ----------------------------------------------------------------------------
# PRIKAZ
# ----------------------------------------------------------------------------
def prikazi_kvotu(korisnik: str, gdje=None):
    """Kompaktan indikator preostale kvote (default: sidebar)."""
    cilj = gdje if gdje is not None else st.sidebar
    s = status(korisnik)
    if s["plan"] == "neograniceno":
        cilj.caption("♾️ Testiranja: **neograničeno**")
        return
    p, lim = s["preostalo"], s["limit"]
    ikona = "🟢" if p > 1 else ("🟡" if p == 1 else "🔴")
    cilj.caption(f"{ikona} Besplatno danas: **{p}/{lim}** "
                 "(obnavlja se sutra)")


def paywall(korisnik: str):
    """Poruka + (demo) opcije plaćanja kad je dnevna kvota potrošena.
    NE pokreće proračun. Vraća True ako je korisnik upravo 'platio' (demo)."""
    s = status(korisnik)
    st.warning(
        f"🔒 Iskoristio si svih **{s['limit']}** besplatnih testiranja za "
        "danas. Kvota se automatski obnavlja sutra (00:00 UTC).")

    st.markdown("#### Nastavi bez čekanja")
    st.info("💳 Stvarni platni sistem još nije povezan. Dugmad ispod "
            "simuliraju uspješnu uplatu radi testiranja toka.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"**Pojedinačno**\n\n{CIJENA_PO_TESTU:.0f} {VALUTA} po testiranju\n\n"
            "Plati koliko ti treba.")
        kolicina = st.number_input("Broj dodatnih testiranja", 1, 100, 5,
                                   key="pay_kolicina")
        st.caption(f"Ukupno: **{kolicina * CIJENA_PO_TESTU:.0f} {VALUTA}**")
        if st.button(f"💳 Plati (demo) — {int(kolicina)} testiranja",
                     type="primary", key="pay_poj"):
            # ——— OVDJE ide stvarni checkout (Stripe/Paddle/…) ———
            _upisi_kupovinu(korisnik, int(kolicina))
            log.debug("demo: +%d testiranja za %s", int(kolicina), korisnik)
            st.success(f"Dodato **{int(kolicina)}** testiranja (demo).")
            st.rerun()
    with c2:
        st.markdown(
            "**Neograničeno (dan)**\n\n"
            f"{DNEVNI_BESPLATNI * CIJENA_PO_TESTU:.0f} {VALUTA} — "
            "neograničeno testiranja do kraja dana.")
        if st.button("💳 Plati (demo) — neograničeno danas", key="pay_unl"):
            # Po stvarnoj uplati za TRAJNI plan: sdb.sacuvaj_korisnika(
            #   korisnik, {... "roles": [...,"paid"]}). Ovdje do kraja dana:
            _upisi_kupovinu(korisnik, None)
            log.debug("demo: neograničeno za %s", korisnik)
            st.success("Neograničeno do kraja dana (demo).")
            st.rerun()
    return False