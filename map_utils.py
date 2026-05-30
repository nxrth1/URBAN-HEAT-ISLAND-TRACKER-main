"""map_utils.py — helper functions for creating Folium maps and raster overlays.

Keep Folium / rasterio overlay logic here so the Streamlit app stays small
and focused on UI wiring.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple, Optional

import numpy as np

try:
    import rasterio
    import rasterio.warp
    from scipy.ndimage import uniform_filter
    import matplotlib.cm as cm
    import matplotlib.colors as colors
    import folium
    from branca.element import Template, MacroElement
except Exception:  # pragma: no cover - optional deps at runtime
    rasterio = None  # type: ignore
    folium = None  # type: ignore

import config as cfg


def _ensure_proj(rio_module) -> None:
    """Set PROJ_LIB to rasterio's bundled proj_data when available.

    This avoids conflicts with other PROJ installations on Windows.
    """
    try:
        rasterio_proj_data = Path(rio_module.__file__).resolve().parent / "proj_data"
        if rasterio_proj_data.exists():
            os.environ["PROJ_LIB"] = str(rasterio_proj_data)
    except Exception:
        pass


def _read_and_prepare(tif_path: str) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
    """Read the raster, mask nodata, compute geographic bounds (WGS84),
    and return the data array and bounds for Folium (lat/lon order).
    """
    if rasterio is None:
        raise RuntimeError("rasterio is required for reading GeoTIFFs")

    _ensure_proj(rasterio)

    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype(np.float32)
        nod = src.nodata
        if nod is not None:
            arr[arr == nod] = np.nan

        geo_bounds = rasterio.warp.transform_bounds(
            src.crs,
            "EPSG:4326",
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top,
            densify_pts=21,
        )
        # Folium expects [[lat_min, lon_min], [lat_max, lon_max]]
        bounds = [[geo_bounds[1], geo_bounds[0]], [geo_bounds[3], geo_bounds[2]]]

    return arr, bounds


def _apply_colormap(arr: np.ndarray, cmap_name: str, vmin: float, vmax: float) -> np.ndarray:
    norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    cmap = cm.get_cmap(cmap_name)
    rgba = cmap(norm(np.nan_to_num(arr, nan=vmin)))
    rgba[..., 3] = np.where(np.isnan(arr), 0.0, 0.75)
    return (rgba * 255).astype(np.uint8)


def get_overlay_png_bytes(year_label: str, cmap_name: Optional[str] = None):
    """Read the GeoTIFF for `year_label`, apply colormap and return a data-URI PNG
    plus bounds and vmin/vmax. The returned PNG bytes are suitable for caching
    by Streamlit's `st.cache_data`.

    Returns: dict with keys `data_uri`, `bounds`, `vmin`, `vmax`, `shape`.
    """
    try:
        from PIL import Image
        from io import BytesIO
        import base64
    except Exception:
        raise RuntimeError("Pillow is required for serializing overlay to PNG")

    tif_path = os.path.join("data", "raw", f"lst_{year_label}.tif")
    arr, bounds = _read_and_prepare(tif_path)

    if np.all(np.isnan(arr)):
        raise ValueError("Raster contains only nodata values")

    # Smooth if scipy is available
    try:
        valid = ~np.isnan(arr)
        if valid.any():
            sm = uniform_filter(np.nan_to_num(arr, nan=0.0), size=cfg.RASTER_SMOOTH_KERNEL)
            w = uniform_filter(valid.astype(np.float32), size=cfg.RASTER_SMOOTH_KERNEL)
            arr = np.where(w > 0, sm / w, np.nan)
    except Exception:
        pass

    cmap_name = cmap_name or cfg.DEFAULT_COLORMAP
    vmin, vmax = np.nanpercentile(arr, [cfg.LST_PERCENTILE_MIN, cfg.LST_PERCENTILE_MAX])
    overlay = _apply_colormap(arr, cmap_name, vmin, vmax)

    # Convert RGBA numpy array to PNG bytes
    img = Image.fromarray(overlay, mode="RGBA")
    bio = BytesIO()
    img.save(bio, format="PNG")
    bio.seek(0)
    raw = bio.read()
    data_uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

    return {"data_uri": data_uri, "bounds": bounds, "vmin": float(vmin), "vmax": float(vmax), "shape": overlay.shape}


def create_map_with_overlay(
    year_label: str,
    blend_mode: str = "Normal",
    colormap: Optional[str] = None,
    opacity: Optional[float] = None,
) -> "folium.Map":
    """Create a Folium map centered on the AOI and overlay the yearly LST TIFF.

    Returns a Folium Map object ready to be displayed in Streamlit.
    """
    if folium is None:
        raise RuntimeError("folium is required to build maps")

    min_lon, min_lat, max_lon, max_lat = cfg.AOI_BBOX
    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
    m = folium.Map(location=center, zoom_start=10, tiles=cfg.MAP_TILES)
    tif_path = os.path.join("data", "raw", f"lst_{year_label}.tif")

    if os.path.exists(tif_path):
        try:
            arr, bounds = _read_and_prepare(tif_path)

            if np.all(np.isnan(arr)):
                raise ValueError("Raster contains only nodata values")

            # Smooth if scipy is available
            try:
                valid = ~np.isnan(arr)
                if valid.any():
                    sm = uniform_filter(np.nan_to_num(arr, nan=0.0), size=cfg.RASTER_SMOOTH_KERNEL)
                    w = uniform_filter(valid.astype(np.float32), size=cfg.RASTER_SMOOTH_KERNEL)
                    arr = np.where(w > 0, sm / w, np.nan)
            except Exception:
                pass
            # apply defaults if caller did not provide
            colormap = colormap or cfg.DEFAULT_COLORMAP
            opacity = opacity if opacity is not None else cfg.DEFAULT_OVERLAY_OPACITY

            vmin, vmax = np.nanpercentile(arr, [cfg.LST_PERCENTILE_MIN, cfg.LST_PERCENTILE_MAX])
            overlay = _apply_colormap(arr, colormap, vmin, vmax)

            folium.raster_layers.ImageOverlay(
                image=overlay,
                bounds=bounds,
                opacity=opacity,
                origin="upper",
            ).add_to(m)

            # Inject JS to set blend mode if requested
            bm = blend_mode.lower() if blend_mode and blend_mode != "Normal" else None
            if bm:
                script_html = f"""
                {{% macro script(this, kwargs) %}}
                <script>
                document.addEventListener('DOMContentLoaded', function() {{
                    var imgs = document.querySelectorAll('.leaflet-image-layer');
                    imgs.forEach(function(img) {{ img.style.mixBlendMode = '{bm}'; img.style.opacity = '{opacity}'; }});
                }});
                </script>
                {{% endmacro %}}
                """
                script = MacroElement()
                script._template = Template(script_html)
                m.get_root().add_child(script)

            # AOI boundary on top
            folium.Rectangle(
                bounds=[[min_lat, min_lon], [max_lat, max_lon]],
                color=cfg.AOI_BOUNDARY_COLOR,
                weight=cfg.AOI_BOUNDARY_WEIGHT,
                fill=False,
                opacity=cfg.AOI_BOUNDARY_OPACITY,
                tooltip=f"{cfg.AOI_NAME} AOI",
            ).add_to(m)

            # Legend
            try:
                legend_html = f"""
                {{% macro html(this, kwargs) %}}
                <div style="position: fixed; bottom: 45px; left: 10px; width: 210px; height: 120px; background-color: white; border:2px solid grey; z-index:9999; font-size:14px; line-height:18px; padding: 10px; opacity: 0.88;">
                    <strong>LST overlay</strong><br>
                    <i style="background: #a50026; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Hot ~{vmax:.1f}°C<br>
                    <i style="background: #ffffbf; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Mid ~{(vmax+vmin)/2:.1f}°C<br>
                    <i style="background: #313695; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Cool ~{vmin:.1f}°C<br>
                    <div style="clear: both;"></div>
                    <div style="margin-top: 6px; font-size:12px; color:#555;">Opacity {int(opacity*100)}% · Blend: {blend_mode}</div>
                </div>
                {{% endmacro %}}
                """
                legend = MacroElement()
                legend._template = Template(legend_html)
                m.get_root().add_child(legend)
            except Exception:
                pass

            folium.LayerControl().add_to(m)
            # Auto-fit the map to the overlay bounds for a better initial view
            try:
                m.fit_bounds(bounds)
            except Exception:
                # Some folium versions may not expose fit_bounds; ignore safely
                pass
        except Exception as e:
            # Surface-level failure — draw AOI and continue
            folium.Rectangle(
                bounds=[[min_lat, min_lon], [max_lat, max_lon]],
                color=cfg.AOI_BOUNDARY_COLOR,
                weight=cfg.AOI_BOUNDARY_WEIGHT,
                fill=False,
                tooltip=f"{cfg.AOI_NAME} AOI",
            ).add_to(m)
            folium.Marker(center, popup=cfg.AOI_NAME, tooltip="Study area center").add_to(m)
            raise
    else:
        folium.Rectangle(
            bounds=[[min_lat, min_lon], [max_lat, max_lon]],
            color=cfg.AOI_BOUNDARY_COLOR,
            weight=cfg.AOI_BOUNDARY_WEIGHT,
            fill=False,
            tooltip=f"{cfg.AOI_NAME} AOI",
        ).add_to(m)
        folium.Marker(center, popup=cfg.AOI_NAME, tooltip="Study area center").add_to(m)

    return m
