# TNP dashboard: en teden (ali poljubno obdobje) v Triglavskem narodnem parku

Javno: https://tomazbercic.github.io/tnp-dashboard/ (GitHub Pages, repozitorij github.com/tomazbercic/tnp-dashboard)
Tudi kot artefakt na claude.ai (zasebno): https://claude.ai/artifact/CV2smq2ZTTuUsS2oAiToqF

Animiran 3D prikaz parka ura za uro: obisk na 12 števcih JZ TNP, vreme z 9 samodejnih postaj ARSO,
pretoki z 10 vodomernih postaj ARSO, avtobusi in vlaki po voznem redu IJPP, žičnice in kolesarske poti iz OSM,
sonce s pravega položaja. Oznake vremenskih postaj kažejo temperaturo in veter (puščica kaže, kam piha).
Privzeto prikaže zadnjih 7 dni, v izbirniku na časovnici pa lahko izbereš do 31 dni iz arhiva.

## Mape in datoteke

- `tnp-dashboard/index.html` – stran (Three.js, brez gradnje)
- `tnp-dashboard/week.json` – statični sloji (relief, meja parka, ceste, reke, poti, jezera, avtobusne linije)
  in podatki referenčnega tedna 2.–8. 11. 2026 (rezerva, če `archive.json` manjka)
- `tnp-dashboard/dem.json`, `albedo.jpg`, `zones.png` – relief, tekstura, varstvena območja
- `tnp-dashboard/archive.json` – arhiv podatkov za izbiro obdobja (dnevni obisk, urna temperatura, padavine, veter, pretoki)
- `tnp-dashboard/osm.json` – žičnice in vlečnice v obratovanju, kolesarske in gorskokolesarske poti (OSM, statično)
- `scripts/fetch_data.py` – zbere sveže podatke in jih doda v `archive.json` (samo standardna knjižnica Pythona)
- `scripts/fetch_osm.py` – iz Overpass API ponovno zgradi `osm.json` (po potrebi, npr. enkrat na sezono)
- `video/` – snemanje videa 3D MAP 013/100 (glej spodaj), končni posnetki v `video/out/`
- `.github/workflows/pages.yml` – ob vsakem potisku na `main` objavi mapo `tnp-dashboard` na GitHub Pages
- `.claude/launch.json` – lokalni predogled (`python -m http.server 8765 --directory tnp-dashboard`), ni v repozitoriju

Skripte, s katerimi so bili na računalniku XPS 12. 11. 2026 pripravljeni statični sloji (relief, OSM, GTFS),
niso tu; ostale so v tisti seji na XPS-u.

## Osveževanje podatkov

```
python -I scripts/fetch_data.py tnp-dashboard/archive.json

git add tnp-dashboard/archive.json
git commit -m "Data to YYYY-MM-DD"
git push
```

Potisk na GitHub v minuti posodobi javno stran. V Claude se `archive.json` objavi še na artefakt.
Oboje vsak dan samodejno naredi načrtovano opravilo »TNP dashboard: osveži podatke« v aplikaciji Claude
(teče, ko je aplikacija odprta na tem računalniku).

Viri in omejitve:
- števci TNP: stran posameznega števca, zadnjih 60 dni
- vreme ARSO: arhiv webmet (10-min temperatura in veter, 30-min padavine → urno, CET), zadnji dan iz 48-urnega prikaza;
  arhiv da največ dve spremenljivki na zahtevo, zato temperatura in padavine ter veter (hitrost, smer) posebej
- pretoki ARSO: urne tabele za zadnjih 30 dni → arhiv mora teči vsaj enkrat na 30 dni, sicer nastane vrzel
- avtobusi: vozni red tedna 2.–8. 11. 2026, ponovljen po dnevih v tednu
- žičnice in kolesarske poti: OpenStreetMap, brez gibanja (podatkov o obratovanju in številu kolesarjev ni);
  izpuščene so opuščene in zgodovinske naprave (npr. Kanin C–D, Golobar)

## Video 3D MAP 013/100 (LinkedIn)

`video/stage.html` je oder 1080 × 1350 (glava serije, podnapisi, povzetek, noga) z nadzorno ploščo v okvirju,
`video/rec.mjs` pa jo posname v Chromu brez okna, sličico za sličico (navidezni čas, prava miška).

```
set FFMPEG=C:/pot/do/ffmpeg.exe
node video/rec.mjs                  (MP4 in PNG zadnjega kadra v video/out/; strežnik ni potreben)
set STILLS=6,20,44 & node video/rec.mjs   (samo posamezne sličice za preverjanje)
```

Scenarij (podnapisi, premiki kazalca, kliki, zum) je na vrhu `rec.mjs`. Slog sledi dokumentu
»3D MAP 001–100: grafična podoba« (4:5, 30 sličic/s, H.264 CRF 18, števec 013/100, EN najprej).
