"""
data_fetch.py — Download Landsat surface temperature data.

We use Microsoft Planetary Computer (planetarycomputer.microsoft.com) as our
data source. It is completely free and does not require an account or API key.
It hosts the full Landsat archive going back to the 1980s.

How STAC works (quick primer):
  STAC = SpatioTemporal Asset Catalog. It is a standard way to search satellite
  imagery by location + date range + cloud cover. Think of it like a search
  engine for satellite data. We send it our bounding box and date range, and it
  returns a list of matching "items" (scenes). We then download only the bands
  we need (ST_B10 for temperature, SR_B4/SR_B5 for NDVI cross-check).
"""

import os
import numpy as np
import rasterio
import pystac_client
import planetary_computer
import stackstac
from tqdm import tqdm

# Import our central settings
import sys
sys.path.insert(0, os.path.dirname(__file__))
from config import (
    AOI_BBOX, LANDSAT_COLLECTION, MAX_CLOUD_COVER,
    ST_SCALE_FACTOR, ST_OFFSET, DATA_RAW
)


def search_scenes(date_start: str, date_end: str) -> list:
    """
    Search the Planetary Computer STAC catalog for Landsat scenes over our AOI.

    Args:
        date_start: ISO date string, e.g. "2015-06-01"
        date_end:   ISO date string, e.g. "2015-09-30"

    Returns:
        List of STAC items (each item = one satellite pass / scene).
    """
    print(f"Searching for Landsat scenes from {date_start} to {date_end}...")

    # Open the Planetary Computer STAC catalog
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,  # adds auth tokens automatically
    )

    # Build our search query
    search = catalog.search(
        collections=[LANDSAT_COLLECTION],
        bbox=AOI_BBOX,
        datetime=f"{date_start}/{date_end}",
        query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
    )

    items = list(search.items())
    print(f"  Found {len(items)} scenes with <{MAX_CLOUD_COVER}% cloud cover.")
    return items


def load_surface_temperature(items: list) -> tuple[np.ndarray, object]:
    """
    Load and mosaic the Surface Temperature band (ST_B10) from a list of scenes.

    Landsat Collection 2 Level-2 delivers ST_B10 already corrected for
    atmospheric effects. We just need to apply the USGS scale factor to get
    real-world temperature values.

    Args:
        items: List of STAC items from search_scenes().

    Returns:
        Tuple of:
          - 2D numpy array of Land Surface Temperature in degrees Celsius.
          - xarray coords object for the stacked composite.
    """
    if not items:
        raise ValueError("No scenes found. Try relaxing date range or cloud cover filter.")

    print(f"Loading ST_B10 from {len(items)} scenes...")

    # Re-sign items immediately before stacking.
    # Planetary Computer auth tokens are short-lived (~1 hour). If they were
    # signed at search time and stacking happens later, the URLs will be stale
    # and stackstac's reader table will come back empty.  Signing again here
    # guarantees fresh tokens right before .compute() fires.
    # We also convert to plain dicts because stackstac resolves proj:bbox and
    # proj:transform more reliably from raw dicts than from PySTAC item objects.
    signed_items = []
    for item in items:
        signed = planetary_computer.sign(item).to_dict()

        # Landsat Surface Temperature assets are named differently by sensor:
        # - Landsat 7/ETM+ uses `lwir`
        # - Landsat 8/OLI-TIRS uses `lwir11`
        # We alias both to `ST_B10` so stackstac can request a single common band.
        if "ST_B10" in signed["assets"]:
            thermal_asset = signed["assets"]["ST_B10"]
        elif "lwir" in signed["assets"]:
            thermal_asset = signed["assets"]["lwir"]
        elif "lwir11" in signed["assets"]:
            thermal_asset = signed["assets"]["lwir11"]
        else:
            raise ValueError(f"No thermal asset found for scene {item.id}")

        signed["assets"]["ST_B10"] = thermal_asset
        signed_items.append(signed)

    # stackstac turns a list of STAC items into an xarray DataArray.
    # It handles reprojection, mosaicking, and lazy loading automatically.
    stack = stackstac.stack(
        signed_items,
        assets=["ST_B10"],        # only download the thermal band alias
        bounds_latlon=AOI_BBOX,
        resolution=30,             # 30 metres — native Landsat resolution
        epsg=32737,               # UTM zone 37S (correct for Nairobi)
        rescale=False,            # preserve raw DN so we can apply our own Kelvin conversion
    )

    # Take the median across all scenes to reduce cloud noise
    # .median("time") collapses the time dimension into a single composite
    print("  Computing median composite (removes cloud noise)...")
    composite = stack.median("time").compute()   # .compute() triggers the download

    # Extract the numpy array from xarray (squeeze removes single-element dims)
    raw_dn = composite.squeeze().values

    # -----------------------------------------------------------------------
    # Convert raw Digital Numbers → Kelvin → Celsius
    # Formula from USGS Landsat Collection 2 Level-2 Science Product Guide
    # -----------------------------------------------------------------------
    lst_kelvin  = (raw_dn * ST_SCALE_FACTOR) + ST_OFFSET
    lst_celsius = lst_kelvin - 273.15

    # Mask out fill values (no-data pixels come through as very cold or very hot)
    lst_celsius = np.where((lst_celsius < -20) | (lst_celsius > 80), np.nan, lst_celsius)

    print(f"  Temperature range: {np.nanmin(lst_celsius):.1f}°C – {np.nanmax(lst_celsius):.1f}°C")
    return lst_celsius, composite.coords


def save_raster(array: np.ndarray, coords, filename: str):
    """
    Save a numpy array as a GeoTIFF so it can be opened in QGIS.

    Args:
        array:    2D numpy array to save.
        coords:   xarray coordinates from the stackstac composite (has CRS + transform).
        filename: Output filename (will be saved inside data/raw/).
    """
    os.makedirs(DATA_RAW, exist_ok=True)
    output_path = os.path.join(DATA_RAW, filename)

    # Build the geospatial transform from the xarray coordinates.
    # The stack was created in UTM zone 37S, so we must preserve that CRS.
    from rasterio.transform import from_bounds

    x = coords["x"].values if "x" in coords else None
    y = coords["y"].values if "y" in coords else None

    if x is None or y is None:
        left, bottom, right, top = AOI_BBOX
    else:
        left, right = float(x.min()), float(x.max())
        bottom, top = float(y.min()), float(y.max())

    height, width = array.shape
    transform = from_bounds(left, bottom, right, top, width, height)

    crs = "EPSG:32737"
    if x is not None and hasattr(coords["x"], "attrs"):
        crs = coords["x"].attrs.get("crs", crs)

    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,               # 1 band
        dtype=array.dtype,
        crs=crs,
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(array, 1)

    print(f"  Saved → {output_path}")
    return output_path


if __name__ == "__main__":
    # Import BOTH sets of dates from your config file
    from config import DATE_START_1, DATE_END_1, DATE_START_2, DATE_END_2

    # 1. Fetch 2015 Data (Year 1)
    items_2015 = search_scenes(DATE_START_1, DATE_END_1)
    if items_2015:
        lst_2015, coords_2015 = load_surface_temperature(items_2015)
        save_raster(lst_2015, coords_2015, "lst_2015.tif")
        
    # 2. Fetch 2023 Data (Year 2)
    items_2023 = search_scenes(DATE_START_2, DATE_END_2)
    if items_2023:
        lst_2023, coords_2023 = load_surface_temperature(items_2023)
        save_raster(lst_2023, coords_2023, "lst_2023.tif")

    print("\nFetch successful! Both 2015 and 2023 datasets are ready in data/raw/")
