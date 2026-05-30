"""
analysis.py — Urban Heat Island calculations and statistics.

Once we have Land Surface Temperature (LST) arrays, this module:
  1. Computes the UHI Intensity (how much hotter the city is vs surroundings)
  2. Identifies hot spots and cool islands
  3. Compares two time periods to detect temperature change
  4. Produces summary statistics per land cover zone

Key concept — Urban Heat Island (UHI):
  The UHI effect is the phenomenon where urban areas are measurably hotter
  than surrounding rural/peri-urban land due to impervious surfaces (roads,
  rooftops) absorbing and re-radiating more heat than vegetation. We measure
  it as: UHI Intensity = mean(urban LST) − mean(rural LST).
"""

import numpy as np
import pandas as pd
from scipy import ndimage


def compute_uhi_intensity(lst: np.ndarray, urban_mask: np.ndarray) -> dict:
    """
    Compute the Urban Heat Island intensity.

    Args:
        lst:        2D array of Land Surface Temperature in °C.
        urban_mask: Boolean 2D array where True = urban pixels.
                    You can create this from land cover data or a simple
                    threshold (pixels > 35°C are likely built-up in Nairobi).

    Returns:
        Dictionary with UHI statistics.
    """
    urban_temps = lst[urban_mask & ~np.isnan(lst)]
    rural_temps = lst[~urban_mask & ~np.isnan(lst)]

    if len(urban_temps) == 0 or len(rural_temps) == 0:
        raise ValueError("Urban or rural mask returned no valid pixels. Check your mask.")

    stats = {
        "urban_mean_celsius":  float(np.mean(urban_temps)),
        "rural_mean_celsius":  float(np.mean(rural_temps)),
        "uhi_intensity":       float(np.mean(urban_temps) - np.mean(rural_temps)),
        "urban_max_celsius":   float(np.max(urban_temps)),
        "rural_min_celsius":   float(np.min(rural_temps)),
        "urban_pixel_count":   int(np.sum(urban_mask)),
        "rural_pixel_count":   int(np.sum(~urban_mask & ~np.isnan(lst))),
    }
    return stats


def detect_hotspots(lst: np.ndarray, percentile: float = 90) -> np.ndarray:
    """
    Return a boolean mask of statistically hot pixels (potential heat islands).

    We use a simple percentile threshold — the hottest X% of pixels.
    A more rigorous approach would use Getis-Ord Gi* spatial statistics,
    which is a future improvement you could add using PySAL.

    Args:
        lst:        2D LST array in °C.
        percentile: Top percentile to flag as hot spots (default 90 = top 10%).

    Returns:
        Boolean 2D array — True where pixels are unusually hot.
    """
    threshold = np.nanpercentile(lst, percentile)
    hotspots = lst >= threshold
    # Apply a small smoothing to reduce pixel-level noise
    hotspots = ndimage.binary_closing(hotspots, structure=np.ones((3, 3)))
    return hotspots


def detect_cool_islands(lst: np.ndarray, percentile: float = 15) -> np.ndarray:
    """
    Return a boolean mask of cool pixels (parks, wetlands, forests).

    Args:
        lst:        2D LST array in °C.
        percentile: Bottom percentile to flag as cool islands (default = bottom 15%).

    Returns:
        Boolean 2D array — True where pixels are unusually cool.
    """
    threshold = np.nanpercentile(lst, percentile)
    cool = lst <= threshold
    cool = ndimage.binary_closing(cool, structure=np.ones((3, 3)))
    return cool


def compute_temperature_change(lst_early: np.ndarray, lst_recent: np.ndarray) -> np.ndarray:
    """
    Pixel-by-pixel temperature change between two periods.

    Args:
        lst_early:  LST array for the earlier period (e.g. 2015).
        lst_recent: LST array for the more recent period (e.g. 2023).

    Returns:
        2D array of temperature change in °C.
        Positive = warming, negative = cooling.
    """
    # Both arrays must have the same shape (same AOI and resolution)
    if lst_early.shape != lst_recent.shape:
        raise ValueError(
            f"Shape mismatch: early={lst_early.shape}, recent={lst_recent.shape}. "
            "Both rasters must cover the exact same area at the same resolution."
        )

    change = lst_recent - lst_early
    return change


def summarise_by_zone(
    lst: np.ndarray,
    zone_labels: dict[str, np.ndarray]
) -> pd.DataFrame:
    """
    Compute mean temperature for each named land cover zone.

    Useful for answering: "How hot is Kibera vs Karura Forest vs the CBD?"

    Args:
        lst:          2D LST array in °C.
        zone_labels:  Dict mapping zone name → boolean mask array.
                      e.g. {"Kibera": kibera_mask, "Karura Forest": karura_mask}

    Returns:
        DataFrame with columns: zone, mean_celsius, max_celsius, pixel_count.
    """
    rows = []
    for zone_name, mask in zone_labels.items():
        pixels = lst[mask & ~np.isnan(lst)]
        if len(pixels) == 0:
            continue
        rows.append({
            "zone":          zone_name,
            "mean_celsius":  round(float(np.mean(pixels)), 2),
            "max_celsius":   round(float(np.max(pixels)), 2),
            "min_celsius":   round(float(np.min(pixels)), 2),
            "std_celsius":   round(float(np.std(pixels)), 2),
            "pixel_count":   int(len(pixels)),
        })

    df = pd.DataFrame(rows).sort_values("mean_celsius", ascending=False)
    return df.reset_index(drop=True)


def make_simple_urban_mask(lst: np.ndarray, threshold_celsius: float = 33.0) -> np.ndarray:
    """
    Quick-and-dirty urban mask using a temperature threshold.

    In Nairobi during dry season, urban surfaces (roads, rooftops) tend to
    register above ~33°C while vegetated land stays cooler.
    This is a starting point — replace with actual land cover data for accuracy.

    Args:
        lst:               2D LST array in °C.
        threshold_celsius: Pixels hotter than this are classed as 'urban'.

    Returns:
        Boolean 2D array.
    """
    return lst >= threshold_celsius


if __name__ == "__main__":
    # Smoke test with synthetic data
    print("Running analysis smoke test with synthetic data...")

    rng = np.random.default_rng(42)
    fake_lst = rng.normal(loc=31, scale=4, size=(200, 200)).astype(np.float32)

    # Inject a heat blob (simulates CBD / industrial area)
    fake_lst[80:120, 80:120] += 8

    urban_mask = make_simple_urban_mask(fake_lst)
    stats = compute_uhi_intensity(fake_lst, urban_mask)
    hotspots = detect_hotspots(fake_lst)
    cool = detect_cool_islands(fake_lst)

    print(f"\nUHI Intensity:  {stats['uhi_intensity']:.2f}°C")
    print(f"Urban mean:     {stats['urban_mean_celsius']:.2f}°C")
    print(f"Rural mean:     {stats['rural_mean_celsius']:.2f}°C")
    print(f"Hot spot pixels: {hotspots.sum()}")
    print(f"Cool island pixels: {cool.sum()}")
    print("\nSmoke test passed.")
