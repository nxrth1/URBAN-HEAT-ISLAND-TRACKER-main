# Urban Heat Island Tracker — Nairobi

Detect and visualise Urban Heat Island (UHI) effects across Nairobi using
Landsat 8/9 thermal infrared data. Compare dry-season composites across years
to see where the city is warming (and where it isn't).

## What this project does

1. **Downloads** Landsat Collection 2 Level-2 scenes from Microsoft Planetary
   Computer (free, no account needed).
2. **Computes** Land Surface Temperature (LST) in °C from the thermal band (ST_B10).
3. **Analyses** UHI intensity, hot spots, cool islands, and change over time.
4. **Displays** everything in an interactive Streamlit dashboard.

## Project structure

```
urban-heat-island/
├── src/
│   ├── config.py        ← Edit this to change study area / dates
│   ├── data_fetch.py    ← Downloads Landsat data
│   └── analysis.py      ← UHI calculations
├── app/
│   └── app.py           ← Streamlit dashboard
├── data/
│   ├── raw/             ← Downloaded GeoTIFFs go here
│   └── processed/       ← Derived products go here
├── notebooks/           ← Jupyter notebooks for exploration
└── requirements.txt
```

## Setup

### 1. Create a virtual environment (recommended)
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the dashboard (demo mode — no real data needed yet)
The dashboard runs with synthetic data out of the box so you can explore it
before downloading anything.
```bash
streamlit run app/app.py
```

### 4. Download real Landsat data
When you're ready to use real satellite imagery:
```bash
python src/data_fetch.py
```
This will download and save:
- `data/raw/lst_2023.tif` — 2023 dry season composite

Edit `src/config.py` to also fetch 2015 data by changing the dates.

## Dashboard features

### Tab 1: Temperature Map
- **Interactive Leaflet/Folium map** showing the LST raster overlay on CartoDB basemap
- **Blend mode selector**: Choose from Normal, Darken, Lighten, Multiply, Screen, Overlay to adjust how the raster blends with the basemap
- **AOI boundary**: Red outline showing the study area bounds (Nairobi)
- **Temperature legend**: Displays the temperature scale (hot → cool) with °C values
- **Zoom and pan**: Full map interactivity to inspect specific areas

### Tab 2: Change Detection (2015 → 2023)
- Side-by-side comparison of temperature change across the study period
- Pixel-level warming/cooling statistics
- Red pixels = areas warming >1°C (urban expansion, vegetation loss)
- Blue pixels = areas cooling (reforestation, urban green spaces)

### Tab 3: Hot Spots & Cool Islands
- Identifies the top 10% hottest pixels (urban heat cores)
- Identifies the bottom 15% coolest pixels (forests, parks, wetlands)
- Temperature distribution histogram with overlaid categories

### Metric cards
- Urban mean temperature
- Rural mean temperature
- UHI intensity (the difference)
- Number of hot spot pixels detected

## Key concepts

### Land Surface Temperature (LST)
- Source band: **ST_B10** (Band 10, thermal infrared, Landsat 8/9)
- Formula: `LST_kelvin = (DN × 0.00341802) + 149.0`
- Convert to Celsius: `LST_celsius = LST_kelvin − 273.15`
- Resolution: 30 metres per pixel

### UHI Intensity
- Defined as: `mean(urban LST) − mean(rural LST)`
- A value of +3°C means the city centre is on average 3 degrees hotter
  than surrounding rural land — which is a meaningful UHI effect.

### Data source
- **Landsat Collection 2 Level-2** via Microsoft Planetary Computer
- URL: https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2
- Licence: Landsat data is freely available with no restrictions (US Government).

## Next steps (after the basics work)

- [ ] Add ESA WorldCover land cover overlay to compare LST by land use type
- [ ] Plot NDVI vs LST scatter to show vegetation cooling effect
- [ ] Add ward boundaries and compute per-ward UHI statistics
- [ ] Export summary statistics as a CSV report
- [ ] Deploy Streamlit app to Streamlit Cloud (free)

## Tools used

| Tool | Purpose |
|---|---|
| `rasterio` | Reading and writing GeoTIFF files |
| `geopandas` | Vector data (boundaries, ward polygons) |
| `stackstac` | Stacking Landsat scenes into xarray |
| `pystac-client` | Searching the STAC satellite catalog |
| `planetary-computer` | Authentication for Planetary Computer |
| `streamlit` | Interactive web dashboard |
| `plotly` | Charts and heatmaps in the dashboard |
