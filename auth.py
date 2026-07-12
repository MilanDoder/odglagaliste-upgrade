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


def _ucitaj_konfig() -> dict:
    # 1) lokalni YAML fajl (razvoj)
    if KONFIG.exists():
        with open(KONFIG, encoding="utf-8") as f:
            return yaml.load(f, Loader=SafeLoader)
    # 2) Streamlit Secrets (Cloud) — sekcija [auth_config] u App Secrets
    try:
        if "auth_config" in st.secrets:
            # st.secrets vraća ugniježđene AttrDict-ove → u obične dict-ove
            import json
            return json.loads(json.dumps(dict(st.secrets["auth_config"])))
    except Exception:
        pass
    st.error(
        "Nedostaje konfiguracija prijave. Lokalno: kopiraj "
        "`auth_config.example.yaml` u `auth_config.yaml`. Na Streamlit "
        "Cloud: dodaj `[auth_config]` sekciju u App Secrets (vidi PRIJAVA.md)."
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


def prikazi_evidenciju(korisnik: str):
    """Sidebar: tekući korisnik; za admina i tabela svih prijava + preuzimanje."""
    konfig = _ucitaj_konfig()
    ime = (konfig["credentials"]["usernames"]
           .get(korisnik, {}).get("first_name", korisnik))
    st.sidebar.caption(f"Prijavljen: **{ime}** (`{korisnik}`)")

    if not _je_admin(korisnik, konfig):
        return
    with st.sidebar.expander("📋 Evidencija prijava (admin)"):
        if not EVIDENCIJA.exists():
            st.write("Još nema zabilježenih prijava.")
            return
        import pandas as pd
        df = pd.read_csv(EVIDENCIJA)
        ukupno = len(df)
        po_korisniku = (df.groupby("korisnik").size()
                        .sort_values(ascending=False))
        st.write(f"Ukupno prijava: **{ukupno}**")
        st.dataframe(po_korisniku.rename("broj"), use_container_width=True)
        st.caption("Posljednjih 20:")
        st.dataframe(df.tail(20).iloc[::-1], use_container_width=True,
                     hide_index=True)
        st.download_button("Preuzmi prijave.csv", EVIDENCIJA.read_bytes(),
                           file_name="prijave.csv", mime="text/csv")
