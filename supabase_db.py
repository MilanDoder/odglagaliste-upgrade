"""
supabase_db.py — trajno skladište za korisnike, prijave, pokušaje i zahtjeve.

Aktivira se ako u App Secrets postoji [supabase] sekcija:

    [supabase]
    url = "https://<projekat>.supabase.co"
    service_key = "<SERVICE_ROLE ključ>"

Ako sekcije nema, aktivan() vraća False i aplikacija pada nazad na
lokalne CSV/YAML fajlove (vidi auth.py). SERVICE_ROLE ključ se koristi
SAMO na serveru (Streamlit backend) i zaobilazi RLS — nikada ga ne
stavljati u frontend ni u git.

Sve funkcije su bezbjedne na grešku: ako upis/čitanje padne (npr. mreža),
vraćaju prazno / tiho ignorišu, da nikad ne obore aplikaciju.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

try:
    from supabase import Client, create_client
except Exception:            # biblioteka nije instalirana
    create_client = None


def aktivan() -> bool:
    """Da li je Supabase konfigurisan (ima secrets i biblioteku)."""
    if create_client is None:
        return False
    try:
        s = st.secrets.get("supabase")
        return bool(s and s.get("url") and s.get("service_key"))
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _klijent() -> "Client | None":
    if not aktivan():
        return None
    s = st.secrets["supabase"]
    try:
        return create_client(s["url"], s["service_key"])
    except Exception as e:
        st.warning(f"Supabase konekcija nije uspjela: {e}")
        return None


# ----------------------------------------------------------------------------
# KORISNICI
# ----------------------------------------------------------------------------
def ucitaj_korisnike() -> dict:
    """Vrati sve korisnike u obliku koji traži streamlit-authenticator:
        {"usernames": {username: {email, first_name, last_name,
                                  password, roles, logged_in,
                                  failed_login_attempts}}}
    """
    c = _klijent()
    if c is None:
        return {"usernames": {}}
    try:
        red = c.table("korisnici").select("*").execute().data or []
    except Exception as e:
        st.warning(f"Supabase: čitanje korisnika nije uspjelo: {e}")
        return {"usernames": {}}
    usernames = {}
    for r in red:
        usernames[r["username"]] = {
            "email": r.get("email", ""),
            "first_name": r.get("first_name", ""),
            "last_name": r.get("last_name", ""),
            "password": r["password"],
            "roles": r.get("roles") or ["viewer"],
            "logged_in": False,
            "failed_login_attempts": 0,
        }
    return {"usernames": usernames}


def sacuvaj_korisnika(username: str, podaci: dict) -> bool:
    """Upiši/ažuriraj korisnika (upsert). password mora već biti bcrypt heš."""
    c = _klijent()
    if c is None:
        return False
    try:
        c.table("korisnici").upsert({
            "username": username,
            "email": podaci.get("email"),
            "first_name": podaci.get("first_name"),
            "last_name": podaci.get("last_name"),
            "password": podaci["password"],
            "roles": podaci.get("roles") or ["viewer"],
        }).execute()
        return True
    except Exception as e:
        st.warning(f"Supabase: upis korisnika nije uspio: {e}")
        return False


# ----------------------------------------------------------------------------
# PRIJAVE / POKUŠAJI / ZAHTJEVI
# ----------------------------------------------------------------------------
def zapisi_prijavu(username: str, ime: str):
    c = _klijent()
    if c is None:
        return
    try:
        c.table("prijave").insert({"username": username, "ime": ime}).execute()
    except Exception:
        pass


def zapisi_pokusaj(username: str | None, uspjeh: bool, razlog: str = ""):
    c = _klijent()
    if c is None:
        return
    try:
        c.table("pokusaji").insert({
            "username": username, "uspjeh": uspjeh, "razlog": razlog,
        }).execute()
    except Exception:
        pass


def zapisi_zahtjev(username: str, metoda: str, parametri: dict,
                   trajanje_s: float, rezultat: str = ""):
    c = _klijent()
    if c is None:
        return
    try:
        c.table("zahtjevi").insert({
            "username": username, "metoda": metoda,
            "parametri": parametri, "trajanje_s": round(float(trajanje_s), 3),
            "rezultat": rezultat,
        }).execute()
    except Exception:
        pass


# ----------------------------------------------------------------------------
# KVOTA — kupljena dodatna testiranja (tabela kvota_dodatak)
# ----------------------------------------------------------------------------
def dodaj_kvotu(username: str, datum: str, broj: int | None) -> bool:
    """Zabilježi kupovinu za dan `datum` (ISO). broj=None → neograničeno
    do kraja tog dana. Vraća True ako je upis uspio."""
    c = _klijent()
    if c is None:
        return False
    try:
        c.table("kvota_dodatak").insert({
            "username": username, "datum": datum,
            "broj": None if broj is None else int(broj),
        }).execute()
        return True
    except Exception as e:
        st.warning(f"Supabase: upis kupovine nije uspio: {e}")
        return False


def kvota_dodatak(username: str, datum: str) -> tuple[int, bool]:
    """(zbir kupljenih testiranja, ima li 'neograničeno') za dan `datum`.
    Baca izuzetak ako upit padne — pozivalac pada na sesijski fallback."""
    c = _klijent()
    if c is None:
        raise RuntimeError("Supabase klijent nije dostupan")
    redovi = (c.table("kvota_dodatak")
              .select("broj")
              .eq("username", username)
              .eq("datum", datum)
              .execute().data or [])
    neogr = any(r.get("broj") is None for r in redovi)
    suma = sum(int(r["broj"]) for r in redovi if r.get("broj") is not None)
    return suma, neogr


def broj_zahtjeva_danas(username: str, danas: str, metode: list[str]) -> int:
    """Koliko je zahtjeva iz `metode` korisnik pokrenuo na dan `danas`
    (ISO datum, UTC). Koristi ga naplata.py za dnevnu kvotu.

    Baca izuzetak ako upit padne — pozivalac (naplata.broj_danas) tada
    pada nazad na lokalni CSV.
    """
    c = _klijent()
    if c is None:
        raise RuntimeError("Supabase klijent nije dostupan")
    od = f"{danas}T00:00:00+00:00"
    do = f"{danas}T23:59:59.999999+00:00"
    redovi = (c.table("zahtjevi")
              .select("username, metoda, vrijeme")
              .eq("username", username)
              .in_("metoda", list(metode))
              .gte("vrijeme", od)
              .lte("vrijeme", do)
              .execute().data or [])
    return len(redovi)


def procitaj_kvota_dodatak(username: str, datum: str) -> dict:
    """Kupljeni dodatak za dan: {"dodatno": int, "neograniceno": bool}.
    Baca izuzetak ako upit padne (pozivalac odlučuje o fallbacku)."""
    c = _klijent()
    if c is None:
        raise RuntimeError("Supabase klijent nije dostupan")
    red = (c.table("kvota_dodatak").select("dodatno, neograniceno")
           .eq("username", username).eq("datum", datum)
           .limit(1).execute().data or [])
    if not red:
        return {"dodatno": 0, "neograniceno": False}
    return {"dodatno": int(red[0].get("dodatno") or 0),
            "neograniceno": bool(red[0].get("neograniceno"))}


def upisi_kvota_dodatak(username: str, datum: str,
                        dodatno_plus: int = 0,
                        neograniceno: bool | None = None) -> bool:
    """Uveća `dodatno` za `dodatno_plus` i/ili postavi `neograniceno`
    za (username, datum). Vraća True ako je upis uspio."""
    c = _klijent()
    if c is None:
        return False
    try:
        tren = {"dodatno": 0, "neograniceno": False}
        try:
            tren = procitaj_kvota_dodatak(username, datum)
        except Exception:
            pass
        podaci = {
            "username": username, "datum": datum,
            "dodatno": tren["dodatno"] + int(dodatno_plus),
            "neograniceno": (tren["neograniceno"]
                             if neograniceno is None else bool(neograniceno)),
        }
        c.table("kvota_dodatak").upsert(podaci).execute()
        return True
    except Exception as e:
        st.warning(f"Supabase: upis kvota_dodatak nije uspio: {e}")
        return False


def veza_radi() -> tuple[bool, str]:
    """Stvarno testira konekciju (lagani upit). Vraća (radi, poruka)."""
    if not aktivan():
        return False, "Supabase nije konfigurisan ([supabase] u secrets)."
    c = _klijent()
    if c is None:
        return False, "Konekcija nije uspostavljena (provjeri url/ključ)."
    try:
        c.table("korisnici").select("username").limit(1).execute()
        return True, "Konekcija ispravna."
    except Exception as e:
        return False, f"Baza dostupna? Greška: {e}"


def _ucitaj_tabelu(naziv: str, limit: int = 500):
    """Vrati posljednjih `limit` redova tabele kao listu dict-ova (novije prvo)."""
    c = _klijent()
    if c is None:
        return []
    try:
        return (c.table(naziv).select("*")
                .order("vrijeme", desc=True).limit(limit)
                .execute().data or [])
    except Exception as e:
        st.warning(f"Supabase: čitanje '{naziv}' nije uspjelo: {e}")
        return []


def ucitaj_prijave(limit: int = 500):
    return _ucitaj_tabelu("prijave", limit)


def ucitaj_pokusaje(limit: int = 500):
    return _ucitaj_tabelu("pokusaji", limit)


def ucitaj_zahtjeve(limit: int = 500):
    return _ucitaj_tabelu("zahtjevi", limit)