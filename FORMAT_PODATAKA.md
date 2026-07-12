# Format ulaznih podataka — odlagalište za bilo koju lokaciju

Aplikacija dolazi sa ugrađenim primjerom **Buvač** (folder `podaci/`), a za
bilo koju drugu lokaciju u sidebaru se isključi „Koristi ugrađene Buvac
podatke" i učita **5 tekstualnih fajlova** opisanih ispod (peti je opcion).

## Opšta pravila

Sve koordinate su u **istom metričkom koordinatnom sistemu** (državna
projekcija, UTM, lokalna gradilišna mreža — svejedno, bitno je da su
jedinice metri i da su SVI fajlovi u istom sistemu). Teren mora prostorno
pokrivati cijelu interesnu zonu. Decimalni separator je tačka, separator
kolona zarez. Kodiranje UTF-8. Linije koje počinju sa `%%` ili `#` su
komentari.

## 1. Teren (obavezan)

Jedna tačka po liniji: `X,Y,Z`. Ne mora biti pravilna mreža — može
direktno izvoz iz geodetskog snimanja ili fotogrametrije; iz tačaka se
gradi triangulacija i interpolator. Preporuka: 10.000–100.000 tačaka
(Buvač ima ~42.000).

```
6411177.27,4968315.08,142.35
6411182.27,4968315.08,142.61
...
```

## 2. Granica interesne zone (obavezan)

Prve dvije linije su okvir (bounding box): min pa max, `X,Y,Z`. Od treće
linije tjemena poligona `X,Y,Z` po liniji — poligon može biti bilo koji
zatvoreni oblik, ne samo pravougaonik. Odlagalište (cijeli footprint
presjeka) mora ostati unutar ovog poligona.

```
6411177.27,4968315.08,100
6414977.27,4972115.08,200
6411177.27,4968315.08,150
6414977.27,4968315.08,150
6414977.27,4972115.08,150
6411177.27,4972115.08,150
6411177.27,4968315.08,150
```

## 3. Centar masa (obavezan)

Jedna linija: `X,Y` — tačka od koje se računa transportna distanca
(tipično težište otkopa iz kojeg se materijal vozi).

```
6413080.0,4970217.0
```

## 4. Ekonomske zone (obavezan)

**5 linija po zoni**, bez praznih linija između:

```
NAZIV_ZONE
cijena_po_m2
povrsina_m2
X1,X2,X3,...      ← X koordinate tjemena poligona zone
Y1,Y2,Y3,...      ← Y koordinate (isti broj vrijednosti)
```

Pravila:

* **Naziv je slobodan** („PARCELA-12", „LIVADA A", „Z-1-1.5"...), s tim
  da ne smije početi brojem niti sadržavati zarez.
* **Zabranjene zone** (odlagalište ih ne smije dodirnuti): naziv počinje
  sa `K` (npr. `K-7`) ILI sadrži riječ `ZABRAN` (npr. `ZABRANJENA-3`).
  Sve ostale zone su dozvoljene, uz trošak zemljišta.
* **Cijena po m²** (2. linija) množi se sa stvarno zahvaćenom površinom
  footprinta u toj zoni. Izuzetak: istorijski Buvač nazivi
  (`Z-1-*`, `Z-3*`, `Z-4-*`, `Z-5*`, `K-5*`) i dalje idu kroz originalne
  MATLAB formule radi kompatibilnosti — za nove lokacije koristite svoje
  nazive i cijena iz fajla važi.
* Površina (3. linija) se koristi u brzom režimu GA petlje; u finalnom
  izvještaju računa se stvarna zahvaćena površina.

Primjer:

```
PARCELA-12
2.5
360000
100,550,550,100
100,100,900,900
ZABRANJENA-3
0
91000
550,900,900,550
640,640,900,900
```

## 5. Dodatni parametri (opcion)

Brojevi u zasebnim linijama, redom (linije sa `%%` su komentari):

| # | Parametar | Ako se izostavi |
|---|---|---|
| 1 | nadmorska visina baze — mnv [m] | najniža kota terena |
| 2 | broj GA generacija | 3 |
| 3 | max transportna distanca [m] | dijagonala interesne zone |
| 4 | cijena transporta [valuta/(m³·km)] | 0.8 (MATLAB original) |
| 5 | cijena dizanja [valuta/(m³·m visine)] | 0.024 (MATLAB original) |

Parametri 4 i 5 su novi i opcioni — Buvač fajl ih nema i koristi
defaulte, čime ostaje identičan originalu. Isti koeficijenti se mogu
mijenjati i u sidebaru („Ekonomski koeficijenti").

```
%% nadmorska visina baze (mv)
300
%% broj GA generacija
3
%% max distanca transporta [m]
5000
%% cijena transporta [valuta/(m3*km)]
1.5
%% cijena dizanja [valuta/(m3*m)]
0.05
```

## Funkcija cilja (radi razumijevanja rezultata)

Za svaku kandidat-kupu: `f = (c1 + c2 + c3) / V`, gdje je
`c1 = distanca_km · cijena_transporta · V` (transport),
`c2 = V · max(kota_vrha − mnv, 0) · cijena_dizanja` (dizanje materijala),
`c3` = trošak zemljišta po zonama, a `V` zapremina odlagališta.
Manja vrijednost f = bolja lokacija.

## Provjera novih podataka

Poslije pripreme fajlova pokrenuti `py test_nova_lokacija.py` kao šablon
provjere, ili jednostavno učitati fajlove u aplikaciju — tab „PODACI"
odmah crta teren, zone i granicu pa se greške u koordinatama vide na
prvi pogled.
