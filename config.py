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

# ---------------------------------------------------------------------------
# Map visualization settings (centralised)
# ---------------------------------------------------------------------------
# Map overlay opacity (0.0 = transparent, 1.0 = opaque)
DEFAULT_OVERLAY_OPACITY = 0.85

# Default colormap for LST visualization
DEFAULT_COLORMAP = "RdYlBu_r"

# Available colormaps for user selection
AVAILABLE_COLORMAPS = [
	"RdYlBu_r",      # Red-Yellow-Blue (reversed) — traditional for temperature
	"viridis",       # Perceptually uniform
	"plasma",        # Perceptually uniform, bright
	"turbo",         # Rainbow-like with good contrast
	"coolwarm",      # Diverging colormap
	"seismic",       # Diverging: blue-white-red
	"twilight",      # Cyclic colormap
]

# Default blend modes for overlay
BLEND_MODES = ["Normal", "Darken", "Lighten", "Multiply", "Screen", "Overlay"]
DEFAULT_BLEND_MODE = "Normal"

# Map tile provider
MAP_TILES = "CartoDB positron"

# Default map zoom level (can be auto-fitted to bounds)
DEFAULT_MAP_ZOOM = 10

# Default padding when auto-fitting bounds (fraction to expand bbox)
DEFAULT_MAP_PADDING = 0.05  # 5% padding

# Raster percentiles for color normalization
LST_PERCENTILE_MIN = 2
LST_PERCENTILE_MAX = 98

# Raster smoothing kernel size
RASTER_SMOOTH_KERNEL = 3

# Hot spot percentile threshold (top X% of pixels)
HOTSPOT_PERCENTILE = 90  # top 10% = 90th percentile

# Cool island percentile threshold (bottom X% of pixels)
COOL_PERCENTILE = 15  # bottom 15% = 15th percentile

# AOI boundary styling
AOI_BOUNDARY_COLOR = "#D85A30"
AOI_BOUNDARY_WEIGHT = 3
AOI_BOUNDARY_OPACITY = 0.8
