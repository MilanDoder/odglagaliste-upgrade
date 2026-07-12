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