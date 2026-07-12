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
ZAHTJEVI = Path(__file__).with_name("zahtjevi.csv")
REGISTROVANI = Path(__file__).with_name("registrovani.yaml")


def uloga_korisnika(korisnik: str) -> str:
    """Vraća prvu rolu korisnika ('admin'/'editor'/'viewer'/'guest'...)."""
    try:
        konfig = _ucitaj_konfig()
        role = (konfig["credentials"]["usernames"]
                .get(korisnik, {}).get("roles") or ["viewer"])
        return role[0]
    except Exception:
        return "viewer"


def je_gost(korisnik: str) -> bool:
    if st.session_state.get("_gost") or korisnik == "gost":
        return True
    return uloga_korisnika(korisnik) == "guest"


def zapisi_zahtjev(korisnik: str, metoda: str, parametri: dict,
                   trajanje_s: float, rezultat: str = ""):
    """Upiši jedan izvršeni zahtjev (MC/GA/…) u zahtjevi.csv za admin uvid."""
    novi = not ZAHTJEVI.exists()
    try:
        with open(ZAHTJEVI, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if novi:
                w.writerow(["vrijeme_utc", "korisnik", "metoda",
                            "parametri", "trajanje_s", "rezultat"])
            params = "; ".join(f"{k}={v}" for k, v in parametri.items())
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        korisnik, metoda, params, f"{trajanje_s:.2f}", rezultat])
    except OSError:
        pass


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


def _spoji_registrovane(konfig: dict) -> dict:
    """Dodaj u konfig korisnike registrovane preko forme (registrovani.yaml)
    i uvijek dostupan 'gost' nalog (rola guest)."""
    usernames = konfig.setdefault("credentials", {}).setdefault("usernames", {})
    # registrovani sa diska (perzistira lokalno; na Cloud-u efemerno)
    if REGISTROVANI.exists():
        try:
            reg = yaml.load(REGISTROVANI.read_text(encoding="utf-8"),
                            Loader=SafeLoader) or {}
            for u, d in (reg.get("usernames") or {}).items():
                usernames.setdefault(u, d)
        except Exception:
            pass
    return konfig


def _ucitaj_konfig() -> dict:
    return _spoji_registrovane(_ucitaj_konfig_sirovi())


def _ucitaj_konfig_sirovi() -> dict:
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
    # nova prijava → uvijek počni na aplikaciji, ne na profilu
    st.session_state["_prikazi_profil"] = False
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

    # --- GOST i REGISTRACIJA (samo dok korisnik nije prijavljen) ---
    if status is not True:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("👋 Uđi kao gost (demo — samo Buvac primjer)",
                         use_container_width=True):
                st.session_state["authentication_status"] = True
                st.session_state["username"] = "gost"
                st.session_state["name"] = "Gost"
                st.session_state["_gost"] = True
                st.rerun()
        with c2:
            with st.expander("📝 Registracija novog naloga"):
                try:
                    (email, uname, ime_reg) = autentikator.register_user(
                        location="main", key="Register",
                        fields={"Form name": "Registracija",
                                "Username": "Korisničko ime",
                                "Password": "Lozinka",
                                "Repeat password": "Ponovi lozinku",
                                "Register": "Registruj se"})
                    if uname:
                        _sacuvaj_registrovanog(uname, konfig)
                        st.success("Nalog kreiran — sada se prijavi gore.")
                except Exception as e:
                    st.warning(f"Registracija: {e}")

    if status is False:
        st.error("Pogrešno korisničko ime ili lozinka.")
        st.stop()
    if status is None:
        st.info("Prijavi se, uđi kao gost ili registruj novi nalog.")
        st.stop()

    # prijavljen
    korisnik = st.session_state.get("username", "?")
    ime = st.session_state.get("name", korisnik)
    # _gost tačno odražava trenutnog korisnika (čisti stari guest flag
    # kad se npr. poslije gosta prijavi admin)
    st.session_state["_gost"] = (korisnik == "gost")
    _upisi_prijavu(korisnik, ime)
    return autentikator, korisnik


def _sacuvaj_registrovanog(uname: str, konfig: dict):
    """Perzistiraj novoregistrovanog korisnika u registrovani.yaml (rola viewer).

    Napomena: na Streamlit Cloud fajlsistem je efemeran — nalog preživi
    sesiju, ali se pri redeployu/rebootu može izgubiti. Za trajne naloge
    upisati ih u App Secrets ili vanjsku bazu.
    """
    podaci = konfig["credentials"]["usernames"].get(uname)
    if not podaci:
        return
    podaci.setdefault("roles", ["viewer"])
    try:
        reg = {}
        if REGISTROVANI.exists():
            reg = yaml.load(REGISTROVANI.read_text(encoding="utf-8"),
                            Loader=SafeLoader) or {}
        reg.setdefault("usernames", {})[uname] = podaci
        REGISTROVANI.write_text(
            yaml.dump(reg, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
    except OSError:
        pass


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


def sidebar_footer(autentikator, korisnik: str):
    """Korisnik (→ profil) i Odjava zalijepljeni u DNO lijevog sidebara.

    Poziva se na KRAJU aplikacije (poslije svih sidebar kontrola) da bi
    flexbox 'margin-top:auto' spacer gurnuo traku na dno.
    """
    konfig = _ucitaj_konfig()
    podaci = konfig["credentials"]["usernames"].get(korisnik, {})
    ime = podaci.get("first_name", korisnik) or korisnik
    role = (podaci.get("roles") or (["guest"] if korisnik == "gost"
                                    else ["korisnik"]))[0]

    # sidebar kao flex kolona pune visine + spacer koji gura footer na dno
    st.markdown(
        "<style>"
        "[data-testid='stSidebarUserContent']{display:flex;flex-direction:"
        "column;min-height:calc(100vh - 90px);}"
        "</style>", unsafe_allow_html=True)
    st.sidebar.markdown("<div style='flex-grow:1'></div>",
                        unsafe_allow_html=True)
    st.sidebar.divider()
    st.sidebar.caption(f"👤 **{ime}** · {role}")
    c1, c2 = st.sidebar.columns(2)
    with c1:
        if st.button("Moj profil", use_container_width=True,
                     key="nav_profil"):
            st.session_state["_prikazi_profil"] = True
            st.rerun()
    with c2:
        autentikator.logout("Odjava", "sidebar", key="logout_footer",
                            use_container_width=True)


def stranica_profila(autentikator, korisnik: str) -> bool:
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
    role = (podaci.get("roles") or (["guest"] if korisnik == "gost"
                                    else ["korisnik"]))[0]

    c_nazad, c_odjava = st.columns([1, 1])
    with c_nazad:
        if st.button("← Nazad na aplikaciju", use_container_width=True):
            st.session_state["_prikazi_profil"] = False
            st.rerun()
    with c_odjava:
        autentikator.logout("Odjava", "main", key="logout_profil",
                            use_container_width=True)

    st.title(f"👤 Moj profil — {ime or korisnik}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Korisničko ime", korisnik)
    c2.metric("Rola", role)
    c3.metric("E-mail", podaci.get("email", "—"))
    st.divider()

    if _je_admin(korisnik, konfig):
        _prikazi_evidenciju_tabela(konfig)
        st.divider()
        _prikazi_zahtjeve_tabela()
    else:
        st.info("Za ovu rolu trenutno nema dodatnih funkcija na profilu.")
    return True


def _prikazi_zahtjeve_tabela():
    """Admin: pregled svih izvršenih zahtjeva (MC/GA) sa parametrima i trajanjem."""
    st.subheader("🧾 Evidencija zahtjeva (proračuni)")
    if not ZAHTJEVI.exists():
        st.info("Još nema izvršenih zahtjeva.")
        return
    import pandas as pd
    df = pd.read_csv(ZAHTJEVI)
    c1, c2, c3 = st.columns(3)
    c1.metric("Ukupno zahtjeva", len(df))
    c2.metric("Metode", df["metoda"].nunique())
    c3.metric("Prosj. trajanje", f"{df['trajanje_s'].astype(float).mean():.1f} s")
    st.write("**Po metodi:**")
    st.dataframe(df.groupby("metoda").size().rename("broj"),
                 use_container_width=True)
    st.write("**Posljednjih 50 zahtjeva:**")
    st.dataframe(df.tail(50).iloc[::-1], use_container_width=True,
                 hide_index=True)
    st.download_button("⬇️ Preuzmi zahtjeve.csv", ZAHTJEVI.read_bytes(),
                       file_name="zahtjevi.csv", mime="text/csv")