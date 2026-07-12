# Trajna istorija preko Supabase baze

Bez baze, na Streamlit Cloud se prijave, pokušaji i zahtjevi čuvaju u
lokalnim CSV/YAML fajlovima koji se gube pri rebootu. Uz Supabase sve to
ide u bazu i ostaje trajno. Aktivira se čim dodaš `[supabase]` u App
Secrets — ako te sekcije nema, aplikacija radi po starom (fajlovi).

## 1. Napravi projekat i tabele

1. Na https://supabase.com napravi projekat (besplatan plan je dovoljan).
2. Otvori **SQL Editor** i pokreni cijeli `supabase_shema.sql` iz repoa.
   Time se prave tabele: `korisnici`, `prijave`, `pokusaji`, `zahtjevi`,
   uz uključen RLS i početni `admin` nalog.

## 2. Uzmi podatke za konekciju

U Supabase → **Project Settings → API**:
- **Project URL** (npr. `https://abcxyz.supabase.co`)
- **service_role** ključ (Project API keys → `service_role`, „reveal").
  Ovaj ključ zaobilazi RLS i sme stajati **samo na serveru** (Streamlit
  backend), nikad u frontend ni u git.

## 3. Dodaj u App Secrets

Streamlit Cloud → Manage app → Settings → Secrets, dodaj (uz postojeći
`[auth_config]`):

```toml
[supabase]
url = "https://abcxyz.supabase.co"
service_key = "eyJ...tvoj_service_role_kljuc..."
```

Save → Reboot. Od tada:
- **korisnici** se čitaju iz baze (registracija upisuje nove trajno);
- svaka **prijava** i **pokušaj** (uspješan/neuspješan) se bilježe;
- svaki **zahtjev** (Monte Carlo / GA / fiksna kupa) ide u `zahtjevi` sa
  parametrima (JSON), trajanjem i rezultatom.

Admin sve to vidi na svojoj profilnoj stranici (prijave, zahtjevi po
metodi i trajanju, te pokušaji prijave), sa preuzimanjem CSV-a.

## 4. Dodavanje korisnika

Dvije opcije:
- kroz aplikaciju: forma „Registracija" (rola `viewer`), upisuje u
  `korisnici`;
- ručno u Supabase: `Table editor → korisnici → Insert`, lozinku unijeti
  kao **bcrypt heš** (ne čist tekst). Heš:
  ```python
  import streamlit_authenticator as stauth
  print(stauth.Hasher.hash_list(["nova_lozinka"])[0])
  ```
  Za admina staviti `roles = {admin}`.

## Šema (kratko)

| tabela | sadržaj |
|---|---|
| `korisnici` | nalozi za prijavu (bcrypt heš lozinke, roles) |
| `prijave` | uspješne prijave: username, ime, vrijeme |
| `pokusaji` | svi pokušaji: username, uspjeh, razlog, vrijeme |
| `zahtjevi` | proračuni: username, metoda, parametri(jsonb), trajanje_s, rezultat, vrijeme |

## Bezbjednost

- `service_role` ključ ide isključivo u App Secrets. Ako procuri, u
  Supabase ga odmah rotiraj (Settings → API → Reset).
- RLS je uključen bez policy-ja za anon, pa anon ključ ne može čitati
  tabele — pristup ima samo aplikacija preko service_role.
- Lozinke se nikad ne čuvaju u čistom tekstu — samo bcrypt heš.
