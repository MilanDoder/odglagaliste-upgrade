# Prijava korisnika i evidencija logina

Aplikacija je zaštićena prijavom (`streamlit-authenticator`): korisnici i
lozinke stoje u `auth_config.yaml`, svaka uspješna prijava se bilježi u
`prijave.csv`, a nalog sa rolom `admin` u sidebaru vidi ko se i kada
logovao.

## Podešavanje

1. Instaliraj zavisnosti: `pip install -r requirements.txt`
   (dodato `streamlit-authenticator` i `PyYAML`).
2. Kopiraj `auth_config.example.yaml` u `auth_config.yaml`.
3. U `auth_config.yaml` upiši korisnike. Lozinke unesi kao **običan
   tekst** u polje `password` — heširaju se automatski pri prvom
   pokretanju. Promijeni `cookie.key` u nasumičan string.
4. Pokreni: `streamlit run app_v2.py`.

Primjer jednog naloga:

```yaml
credentials:
  usernames:
    milan:
      email: milan@example.com
      first_name: Milan
      last_name: Doder
      password: moja-lozinka        # biće heširana
      roles: [editor]
      logged_in: false
      failed_login_attempts: 0
```

Role: `admin` (vidi evidenciju prijava), ostale (`editor`, `viewer`...)
su informativne — pristup aplikaciji je isti za sve prijavljene.

## Praćenje ko se logovao

Svaka prijava dodaje red u `prijave.csv`:

```
vrijeme_utc,korisnik,ime
2026-07-12T12:27:28+00:00,milan,Milan Doder
```

Admin u sidebaru („📋 Evidencija prijava") vidi ukupan broj prijava,
broj po korisniku, posljednjih 20 i dugme za preuzimanje cijelog CSV-a.

## Bezbjednost i deploy

* `auth_config.yaml` i `prijave.csv` su u `.gitignore` — **ne commituj
  ih** (sadrže hešове lozinki i evidenciju). U repo ide samo
  `auth_config.example.yaml`.
* Na Streamlit Cloud koristi **privatni repo**, ili prebaci sadržaj
  `auth_config.yaml` u App Secrets i učitaj ga odatle.
* Streamlit Cloud ima efemeran fajlsistem — `prijave.csv` se može
  izgubiti pri restartu/redeployu. Za trajnu evidenciju vezati upis na
  vanjsko skladište (npr. Google Sheet ili bazu); trenutni CSV je
  dovoljan za lokalni rad i kraće sesije.
* „Zapamti me": cookie traje `expiry_days` (default 30) — dok ne istekne,
  korisnik se ne mora ponovo prijavljivati.

## Reset / dodavanje korisnika

Dodaj novi blok pod `usernames` u `auth_config.yaml` (lozinka kao običan
tekst) i restartuj app. Za promjenu lozinke postojećem korisniku obriši
njegovu heširanu vrijednost i upiši novu u običnom tekstu — biće ponovo
heširana.

## Gost, registracija i evidencija zahtjeva (dodato)

**Gost** — na login ekranu dugme „Uđi kao gost" prijavljuje demo korisnika
(rola `guest`). Gost može koristiti **samo ugrađeni Buvac primjer**: upload
vlastitog terena/zona/centra masa je sakriven, checkbox za ugrađene podatke
se ne prikazuje. Ostatak aplikacije (MC, proračun, prikazi) radi normalno.

**Registracija** — na login ekranu „Registracija novog naloga" kreira nalog
(rola `viewer`) i snima ga u `registrovani.yaml`. Napomena: na Streamlit
Cloud je fajlsistem efemeran, pa registrovani nalozi prežive sesiju ali se
pri rebootu/redeployu mogu izgubiti — za trajne naloge upisati ih u App
Secrets ili vanjsku bazu. `registrovani.yaml` je u `.gitignore`.

**Evidencija zahtjeva (admin)** — svako pokretanje Monte Carla i proračuna
(GA / fiksna kupa) upisuje red u `zahtjevi.csv`: vrijeme, korisnik, metoda,
svi ulazni parametri (npr. `generisano=100; seed=…` za MC; `populacija`,
`generacija`, `ugao`, `rezolucija`, granice zapremine za GA), trajanje
izvršavanja i rezultat. Admin ovu tabelu vidi na svojoj profilnoj stranici
(„🧾 Evidencija zahtjeva"), sa pregledom po metodi i preuzimanjem CSV-a.
`zahtjevi.csv` je u `.gitignore`.