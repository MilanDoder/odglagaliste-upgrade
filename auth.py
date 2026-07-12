"""
auth.py — prijava korisnika (streamlit-authenticator) + evidencija logina.

Korisnici i lozinke stoje u auth_config.yaml (lozinke se heširaju
automatski pri prvom pokretanju). Svaka uspješna prijava se upisuje u
prijave.csv, pa se u aplikaciji (admin) može vidjeti ko se i kada logovao.

Upotreba u app_v2.py:

    from auth import zahtijevaj_prijavu, prikazi_evidenciju
    autentikator, korisnik = zahtijevaj_prijavu()   # zaustavlja app dok se ne prijavi
    ...                                             # ostatak aplikacije
    autentikator.logout("Odjava", "sidebar")        # dugme za odjavu

Napomene:
  * auth_config.yaml NE commitovati sa pravim lozinkama u javni repo —
    na Streamlit Cloud koristiti privatni repo ili secrets.
  * cookie omogućava „zapamti me" (bez ponovne prijave `expiry_days` dana).
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

KONFIG = Path(__file__).with_name("auth_config.yaml")
EVIDENCIJA = Path(__file__).with_name("prijave.csv")


def _normalizuj(konfig: dict) -> dict | None:
    """Iz raznih rasporeda izvuče {'credentials':..., 'cookie':...}."""
    if not isinstance(konfig, dict):
        return None
    # skini omotač auth_config ako postoji
    if "auth_config" in konfig and isinstance(konfig["auth_config"], dict):
        konfig = konfig["auth_config"]

    creds = konfig.get("credentials")
    cookie = konfig.get("cookie")

    # cookie polja mogu biti direktno u konfig (bez [cookie] podsekcije)
    if cookie is None and "name" in konfig and "key" in konfig:
        cookie = {"name": konfig["name"], "key": konfig["key"],
                  "expiry_days": konfig.get("expiry_days", 30)}

    if creds and cookie and "name" in cookie and "key" in cookie:
        # osiguraj expiry_days
        cookie.setdefault("expiry_days", 30)
        return {"credentials": creds, "cookie": cookie}
    return None


def _ucitaj_konfig() -> dict:
    import json

    def _u(x):
        try:
            return json.loads(json.dumps(x, default=lambda o: dict(o)))
        except Exception:
            return dict(x) if hasattr(x, "keys") else x

    # 1) lokalni YAML fajl (razvoj)
    if KONFIG.exists():
        with open(KONFIG, encoding="utf-8") as f:
            k = _normalizuj(yaml.load(f, Loader=SafeLoader))
            if k:
                return k

    # 2) Streamlit Secrets (Cloud) — probaj sve razumne rasporede
    prisutni_kljucevi = []
    try:
        prisutni_kljucevi = list(st.secrets.keys())
    except Exception:
        pass

    try:
        cijeli = _u(st.secrets)          # cijeli secrets kao obican dict
        for kandidat in (cijeli,
                         cijeli.get("auth_config"),
                         cijeli.get("auth")):
            k = _normalizuj(kandidat) if kandidat else None
            if k:
                return k
    except Exception as e:
        st.error(f"Greška pri čitanju App Secrets: {e}")
        st.stop()

    # 3) nije nađeno — DIJAGNOSTIKA umjesto slijepe poruke
    st.error(
        "Prijava: konfiguracija nije pronađena u App Secrets.\n\n"
        f"Ključevi koje app trenutno vidi u secrets-ima: "
        f"**{prisutni_kljucevi or 'NIŠTA (secrets prazni ili nisu sačuvani)'}**\n\n"
        "Očekujem sekciju `[auth_config]` sa `name`, `key`, `expiry_days` i "
        "`[auth_config.credentials.usernames.<ime>]` nalozima. Provjeri da su "
        "secrets **sačuvani** (Manage app → Settings → Secrets → Save) i da si "
        "poslije uradio **Reboot app**."
    )
    st.stop()


def _upisi_prijavu(korisnik: str, ime: str):
    """Dodaj red u prijave.csv (jednom po sesiji, na uspješnu prijavu)."""
    if st.session_state.get("_prijava_upisana"):
        return
    novi = not EVIDENCIJA.exists()
    try:
        with open(EVIDENCIJA, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if novi:
                w.writerow(["vrijeme_utc", "korisnik", "ime"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        korisnik, ime])
        st.session_state["_prijava_upisana"] = True
    except OSError:
        pass  # na read-only FS (npr. neki hosting) evidencija se preskače


def zahtijevaj_prijavu(naslov: str = "🔒 Optimizacija odlagališta — prijava"):
    """Renderuje login; zaustavlja izvršavanje dok korisnik nije prijavljen.

    Vraća (authenticator, username) kada je prijava uspješna.
    """
    konfig = _ucitaj_konfig()
    autentikator = stauth.Authenticate(
        konfig["credentials"],
        konfig["cookie"]["name"],
        konfig["cookie"]["key"],
        konfig["cookie"]["expiry_days"],
    )

    # od v0.4.x login upisuje status direktno u st.session_state
    autentikator.login(location="main", key="Login")

    status = st.session_state.get("authentication_status")
    if status is False:
        st.error("Pogrešno korisničko ime ili lozinka.")
        st.stop()
    if status is None:
        st.info("Unesite korisničko ime i lozinku za pristup aplikaciji.")
        st.stop()

    # prijavljen
    korisnik = st.session_state.get("username", "?")
    ime = st.session_state.get("name", korisnik)
    _upisi_prijavu(korisnik, ime)
    return autentikator, korisnik


def _je_admin(korisnik: str, konfig: dict) -> bool:
    role = (konfig["credentials"]["usernames"]
            .get(korisnik, {}).get("roles", []) or [])
    return "admin" in role


def _prikazi_evidenciju_tabela(konfig: dict):
    """Tabela svih prijava + preuzimanje (samo za admina, na profilnoj strani)."""
    st.subheader("📋 Evidencija prijava")
    if not EVIDENCIJA.exists():
        st.info("Još nema zabilježenih prijava.")
        return
    import pandas as pd
    df = pd.read_csv(EVIDENCIJA)
    c1, c2 = st.columns(2)
    c1.metric("Ukupno prijava", len(df))
    c2.metric("Različitih korisnika", df["korisnik"].nunique())
    po_korisniku = (df.groupby("korisnik").size()
                    .sort_values(ascending=False).rename("broj prijava"))
    st.write("**Po korisniku:**")
    st.dataframe(po_korisniku, use_container_width=True)
    st.write("**Posljednjih 50 prijava:**")
    st.dataframe(df.tail(50).iloc[::-1], use_container_width=True,
                 hide_index=True)
    st.download_button("⬇️ Preuzmi prijave.csv", EVIDENCIJA.read_bytes(),
                       file_name="prijave.csv", mime="text/csv")


def navbar(autentikator, korisnik: str):
    """Gornja traka poravnata desno: ime prijavljenog korisnika
    (dugme → profil) i dugme Odjava, jedno pored drugog.
    """
    konfig = _ucitaj_konfig()
    podaci = konfig["credentials"]["usernames"].get(korisnik, {})
    ime = podaci.get("first_name", korisnik)
    role = (podaci.get("roles") or ["korisnik"])[0]

    # skupi razmak na vrhu + kompaktna dugmad da liči na navbar
    st.markdown(
        "<style>"
        ".block-container{padding-top:2.2rem;}"
        "div.stButton>button{padding:4px 14px;border-radius:8px;"
        "font-size:0.85rem;font-weight:600;}"
        "</style>", unsafe_allow_html=True)

    # lijeva prazna zona gura traku skroz desno; ime i Odjava u istom redu
    _, kol_ime, kol_odjava = st.columns([6, 1.1, 1.1])
    with kol_ime:
        if st.button(f"👤 {ime}", use_container_width=True,
                     key="nav_profil",
                     help=f"{korisnik} · {role} — otvori moj profil"):
            st.session_state["_prikazi_profil"] = True
            st.rerun()
    with kol_odjava:
        autentikator.logout("Odjava", "main", key="logout_navbar",
                            use_container_width=True)
    st.divider()


def stranica_profila(korisnik: str) -> bool:
    """Profilna stranica korisnika. Vraća True ako je prikazana (tada
    aplikacija ne treba da renderuje glavni sadržaj).

    Sadrži funkcije specifične za korisnika; admin ovdje vidi evidenciju
    prijava svih korisnika.
    """
    if not st.session_state.get("_prikazi_profil"):
        return False

    konfig = _ucitaj_konfig()
    podaci = konfig["credentials"]["usernames"].get(korisnik, {})
    ime = f"{podaci.get('first_name','')} {podaci.get('last_name','')}".strip()
    role = (podaci.get("roles") or ["korisnik"])[0]

    if st.button("← Nazad na aplikaciju"):
        st.session_state["_prikazi_profil"] = False
        st.rerun()

    st.title(f"👤 Moj profil — {ime or korisnik}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Korisničko ime", korisnik)
    c2.metric("Rola", role)
    c3.metric("E-mail", podaci.get("email", "—"))
    st.divider()

    if _je_admin(korisnik, konfig):
        _prikazi_evidenciju_tabela(konfig)
    else:
        st.info("Za ovu rolu trenutno nema dodatnih funkcija na profilu.")
    return True