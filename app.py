"""
app.py — Streamlit dashboard for the Nairobi Urban Heat Island Tracker.

Run with:
    streamlit run app/app.py

The dashboard has three tabs:
  1. Temperature Map — interactive map of LST for a chosen year
  2. Change Detection  — pixel-by-pixel warming/cooling between 2015 and 2023
  3. Hot Spots         — where are the heat islands and cool islands?
"""

import os
import sys
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px

# Make sure src/ is on the path when running from the project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config import AOI_NAME, AOI_BBOX, DATE_START_1, DATE_END_1, DATE_START_2, DATE_END_2
from analysis import (
    compute_uhi_intensity,
    detect_hotspots,
    detect_cool_islands,
    compute_temperature_change,
    make_simple_urban_mask,
    summarise_by_zone,
)

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"Urban Heat Island — {AOI_NAME}",
    page_icon="🌡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helper: load (or simulate) LST data
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Fetching Landsat data…")
def load_lst(year_label: str) -> np.ndarray:
    """
    Try to load a pre-processed LST GeoTIFF from disk.
    If not found, generate realistic synthetic data so the dashboard still
    runs before you have real data.

    To replace with real data:
      1. Run src/data_fetch.py to download and save lst_2015.tif / lst_2023.tif
      2. Update the paths below to point at your actual files.
    """
    import rasterio

    tif_path = os.path.join("data", "raw", f"lst_{year_label}.tif")

    if os.path.exists(tif_path):
        from scipy.ndimage import uniform_filter

        with rasterio.open(tif_path) as src:
            lst = src.read(1).astype(np.float32)
            lst[lst == src.nodata] = np.nan

        try:
            valid = ~np.isnan(lst)
            if valid.any():
                smoothed = uniform_filter(np.nan_to_num(lst, nan=0.0), size=3)
                weights = uniform_filter(valid.astype(np.float32), size=3)
                lst = np.where(weights > 0, smoothed / weights, np.nan)
        except Exception as e:
            st.warning(f"Could not smooth raw data: {e}")

        return lst
    else:
        # ----------------------------------------------------------------
        # SYNTHETIC FALLBACK — realistic Nairobi-like temperature field
        # This lets you explore the dashboard before downloading real data.
        # Replace this block by running data_fetch.py.
        # ----------------------------------------------------------------
        st.info(
            f"⚠️ No real data found for {year_label} "
            f"(expected at `{tif_path}`). "
            "Showing synthetic demo data. Run `src/data_fetch.py` to get real Landsat data.",
            icon="ℹ️"
        )
        rng = np.random.default_rng({"2015": 1, "2023": 2}.get(year_label, 0))
        size = (200, 220)
        base = rng.normal(loc=30.0, scale=3.0, size=size).astype(np.float32)

        # Simulate warming in 2023 (+1.5°C average, more in dense areas)
        if year_label == "2023":
            base += 1.5

        # Inject urban heat cores (CBD, Industrial Area, Eastlands)
        base[60:100,  90:130] += 7    # CBD / upper hill
        base[90:130, 130:170] += 5    # Industrial Area
        base[50:80,  150:190] += 4    # Eastlands

        # Cool islands (Karura Forest, Nairobi National Park)
        base[20:55,   10:60]  -= 6    # Karura Forest
        base[130:180, 30:90]  -= 5    # Nairobi National Park

        return base


def create_aoi_basemap(year_label: str, blend_mode: str = "Normal") -> folium.Map:
    min_lon, min_lat, max_lon, max_lat = AOI_BBOX
    center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]

    m = folium.Map(location=center, zoom_start=10, tiles="CartoDB positron")
    tif_path = os.path.join("data", "raw", f"lst_{year_label}.tif")

    if os.path.exists(tif_path):
        try:
            import rasterio
            import rasterio.warp
            import matplotlib.cm as cm
            import matplotlib.colors as colors
            from pathlib import Path

            rasterio_proj_data = Path(rasterio.__file__).resolve().parent / "proj_data"
            if rasterio_proj_data.exists():
                os.environ["PROJ_LIB"] = str(rasterio_proj_data)

            with rasterio.open(tif_path) as src:
                lst_raw = src.read(1).astype(np.float32)
                lst_raw[lst_raw == src.nodata] = np.nan
                geo_bounds = rasterio.warp.transform_bounds(
                    src.crs,
                    "EPSG:4326",
                    src.bounds.left,
                    src.bounds.bottom,
                    src.bounds.right,
                    src.bounds.top,
                    densify_pts=21,
                )
                bounds = [[geo_bounds[1], geo_bounds[0]], [geo_bounds[3], geo_bounds[2]]]

            if np.all(np.isnan(lst_raw)):
                raise ValueError("Raster contains only nodata values")

            vmin, vmax = np.nanpercentile(lst_raw, [2, 98])
            norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
            rgba = cm.get_cmap("RdYlBu_r")(norm(np.nan_to_num(lst_raw, nan=vmin)))
            rgba[..., 3] = np.where(np.isnan(lst_raw), 0.0, 0.75)
            overlay_array = (rgba * 255).astype(np.uint8)

            blend_css = blend_mode.lower() if blend_mode != "Normal" else None
            overlay_kwargs = dict(
                image=overlay_array,
                bounds=bounds,
                opacity=0.85,
                name=f"LST {year_label}",
                interactive=True,
                cross_origin=False,
                zindex=1,
                origin='upper',
            )

            folium.raster_layers.ImageOverlay(**overlay_kwargs).add_to(m)

            if blend_css:
                from branca.element import Template, MacroElement

                script_html = f"""
                {{% macro script(this, kwargs) %}}
                <script>
                    // Set blend mode on the image overlay
                    document.addEventListener('DOMContentLoaded', function() {{
                        var imgs = document.querySelectorAll('.leaflet-image-layer');
                        imgs.forEach(function(img) {{
                            img.style.mixBlendMode = '{blend_css}';
                        }});
                    }});
                </script>
                {{% endmacro %}}
                """
                script = MacroElement()
                script._template = Template(script_html)
                m.get_root().add_child(script)

            folium.Rectangle(
                bounds=[[min_lat, min_lon], [max_lat, max_lon]],
                color="#D85A30",
                weight=3,
                fill=False,
                opacity=0.8,
                tooltip=f"{AOI_NAME} AOI",
            ).add_to(m)
            folium.LayerControl().add_to(m)

            try:
                from branca.element import Template, MacroElement

                legend_html = f"""
                {{% macro html(this, kwargs) %}}
                <div style="position: fixed; bottom: 45px; left: 10px; width: 210px; height: 120px; 
                            background-color: white; border:2px solid grey; z-index:9999; font-size:14px; 
                            line-height:18px; padding: 10px; opacity: 0.88;">
                    <strong>LST overlay</strong><br>
                    <i style="background: #a50026; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Hot ~{vmax:.1f}°C<br>
                    <i style="background: #ffffbf; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Mid ~{(vmax+vmin)/2:.1f}°C<br>
                    <i style="background: #313695; width: 18px; height: 12px; float: left; margin-right: 8px;"></i> Cool ~{vmin:.1f}°C<br>
                    <div style="clear: both;"></div>
                    <div style="margin-top: 6px; font-size:12px; color:#555;">Opacity 85% for stronger overlay visibility</div>
                </div>
                {{% endmacro %}}
                """
                legend = MacroElement()
                legend._template = Template(legend_html)
                m.get_root().add_child(legend)
            except Exception:
                pass
        except Exception as e:
            st.warning(f"Could not overlay TIFF on basemap: {e}")
    else:
        folium.Rectangle(
            bounds=[[min_lat, min_lon], [max_lat, max_lon]],
            color="#D85A30",
            weight=3,
            fill=False,
            tooltip=f"{AOI_NAME} AOI",
        ).add_to(m)
        folium.Marker(center, popup=AOI_NAME, tooltip="Study area center").add_to(m)

    return m


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🌡️ UHI Tracker")
st.sidebar.markdown(f"**Study area:** {AOI_NAME}")
st.sidebar.markdown("---")

selected_year = st.sidebar.radio(
    "Select year to explore",
    options=["2015", "2023"],
    index=1,
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Data source:** Landsat 8/9 Collection 2 Level-2 "
    "via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) "
    "(free, open access)."
)
st.sidebar.markdown(
    "**Resolution:** 30 m/pixel · **Season:** Dry (Jun–Sep)"
)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
lst = load_lst(selected_year)
urban_mask = make_simple_urban_mask(lst)
hotspots   = detect_hotspots(lst)
cool       = detect_cool_islands(lst)

# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------
st.title(f"Urban Heat Island Tracker — {AOI_NAME}")
st.caption(
    f"Land Surface Temperature (LST) derived from Landsat thermal band (ST_B10) · "
    f"Showing {selected_year} dry-season composite"
)

# ---------------------------------------------------------------------------
# Metric cards
# ---------------------------------------------------------------------------
try:
    stats = compute_uhi_intensity(lst, urban_mask)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Urban mean temp",  f"{stats['urban_mean_celsius']:.1f} °C")
    c2.metric("Rural mean temp",  f"{stats['rural_mean_celsius']:.1f} °C")
    c3.metric(
        "UHI intensity",
        f"{stats['uhi_intensity']:.1f} °C",
        help="How much hotter urban areas are compared to surrounding rural land.",
    )
    c4.metric("Hot spot pixels",  f"{hotspots.sum():,}")
except Exception as e:
    st.warning(f"Could not compute UHI metrics: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["🗺️ Temperature map", "📈 Change 2015 → 2023", "🔴 Hot & cool spots"])

# ── Tab 1: Temperature heatmap ────────────────────────────────────────────
with tab1:
    st.subheader(f"Land Surface Temperature — {selected_year}")

    overlay_mode = st.selectbox(
        "Overlay blend mode",
        options=["Normal", "Darken", "Lighten", "Multiply", "Screen", "Overlay"],
        help="Choose how the LST raster blends with the basemap.",
    )

    st.markdown("### Nairobi study area")
    st_folium(create_aoi_basemap(selected_year, overlay_mode), width=700, height=360)

    fig = px.imshow(
        lst,
        color_continuous_scale="RdYlBu_r",   # red = hot, blue = cool
        labels={"color": "LST (°C)"},
        aspect="equal",
        title=f"Nairobi LST — {selected_year} dry season composite",
    )
    fig.update_layout(
        coloraxis_colorbar=dict(title="°C"),
        margin=dict(l=0, r=0, t=40, b=0),
        height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Each pixel = 30 m × 30 m. Red pixels are hottest (roads, rooftops). "
        "Blue pixels are coolest (forests, parks, wetlands)."
    )

# ── Tab 2: Change detection ───────────────────────────────────────────────
with tab2:
    st.subheader("Temperature change: 2015 → 2023")

    lst_2015 = load_lst("2015")
    lst_2023 = load_lst("2023")

    try:
        change = compute_temperature_change(lst_2015, lst_2023)

        col_a, col_b = st.columns([2, 1])

        with col_a:
            fig_change = px.imshow(
                change,
                color_continuous_scale="RdBu_r",
                range_color=[-5, 5],
                labels={"color": "Δ°C"},
                title="Temperature change (°C) — warmer areas in red",
            )
            fig_change.update_layout(height=460, margin=dict(l=0, r=0, t=40, b=0))
            st.plotly_chart(fig_change, use_container_width=True)

        with col_b:
            warming_pixels = np.sum(change > 1.0)
            cooling_pixels = np.sum(change < -1.0)
            total_valid    = np.sum(~np.isnan(change))

            st.metric("Pixels warming >1°C",  f"{warming_pixels:,}")
            st.metric("Pixels cooling >1°C",  f"{cooling_pixels:,}")
            st.metric("Mean change",           f"{np.nanmean(change):.2f} °C")
            st.metric("Max warming",           f"{np.nanmax(change):.1f} °C")

            st.markdown("---")
            st.markdown(
                "**Interpreting this map:** Red areas have warmed more than 1°C "
                "between 2015 and 2023 — typically areas of new construction or "
                "vegetation clearance. Blue areas have cooled (reforestation, new "
                "green spaces, or change in land use)."
            )

    except ValueError as e:
        st.error(f"Could not compute change: {e}")

# ── Tab 3: Hot spots & cool islands ──────────────────────────────────────
with tab3:
    st.subheader("Hot spots and cool islands")

    col_l, col_r = st.columns(2)

    with col_l:
        fig_hot = px.imshow(
            hotspots.astype(np.uint8),
            color_continuous_scale=["white", "#D85A30"],
            title="Hot spots (top 10% of pixels)",
            labels={"color": "Hot spot"},
        )
        fig_hot.update_coloraxes(showscale=False)
        fig_hot.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_hot, use_container_width=True)
        st.caption("Orange = unusually hot pixels (roads, rooftops, bare soil).")

    with col_r:
        fig_cool = px.imshow(
            cool.astype(np.uint8),
            color_continuous_scale=["white", "#185FA5"],
            title="Cool islands (bottom 15% of pixels)",
            labels={"color": "Cool island"},
        )
        fig_cool.update_coloraxes(showscale=False)
        fig_cool.update_layout(height=380, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_cool, use_container_width=True)
        st.caption("Blue = unusually cool pixels (Karura Forest, Nairobi National Park, wetlands).")

    # Temperature distribution histogram
    st.markdown("### Temperature distribution")
    valid_temps = lst[~np.isnan(lst)].flatten()

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=valid_temps,
        nbinsx=60,
        name="All pixels",
        marker_color="#888780",
        opacity=0.6,
    ))
    fig_hist.add_trace(go.Histogram(
        x=lst[hotspots & ~np.isnan(lst)].flatten(),
        nbinsx=40,
        name="Hot spots",
        marker_color="#D85A30",
        opacity=0.8,
    ))
    fig_hist.add_trace(go.Histogram(
        x=lst[cool & ~np.isnan(lst)].flatten(),
        nbinsx=40,
        name="Cool islands",
        marker_color="#185FA5",
        opacity=0.8,
    ))
    fig_hist.update_layout(
        barmode="overlay",
        xaxis_title="Temperature (°C)",
        yaxis_title="Pixel count",
        legend_title="Category",
        height=320,
        margin=dict(l=0, r=0, t=20, b=0),
    )
    st.plotly_chart(fig_hist, use_container_width=True)
