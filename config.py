"""
config.py — Central settings for the Urban Heat Island Tracker.

Edit the values here to change the study area, date range, or output paths.
Everything else in the project reads from this file so you only change things once.
"""

# ---------------------------------------------------------------------------
# Area of Interest — Nairobi bounding box (WGS84 lon/lat)
# ---------------------------------------------------------------------------
# These coordinates cover greater Nairobi + surrounding areas.
# Format: [min_lon, min_lat, max_lon, max_lat]
AOI_BBOX = [36.60, -1.45, 37.10, -1.10]

# Human-readable name shown in the Streamlit dashboard
AOI_NAME = "Nairobi, Kenya"

# ---------------------------------------------------------------------------
# Date ranges to compare (dry season = June–September for clearest imagery)
# ---------------------------------------------------------------------------
# Year 1 — baseline period
DATE_START_1 = "2015-06-01"
DATE_END_1   = "2015-09-30"

# Year 2 — recent period (shows change)
DATE_START_2 = "2023-06-01"
DATE_END_2   = "2023-09-30"

# Maximum cloud cover % allowed when searching for scenes
MAX_CLOUD_COVER = 20

# ---------------------------------------------------------------------------
# Landsat settings
# ---------------------------------------------------------------------------
# We use Landsat Collection 2 Level-2 (already atmospherically corrected).
# Band ST_B10 = Surface Temperature (Band 10, thermal infrared).
LANDSAT_COLLECTION = "landsat-c2-l2"

# Scale factor and offset to convert raw DN → Kelvin (from USGS documentation)
# LST_kelvin = (DN × SCALE_FACTOR) + OFFSET
ST_SCALE_FACTOR = 0.00341802
ST_OFFSET       = 149.0

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
DATA_RAW       = "data/raw"
DATA_PROCESSED = "data/processed"
