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

import config as cfg
from analysis import (
    compute_uhi_intensity,
    detect_hotspots,
    detect_cool_islands,
    compute_temperature_change,
    make_simple_urban_mask,
    summarise_by_zone,
)
from map_utils import create_map_with_overlay

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"Urban Heat Island — {cfg.AOI_NAME}",
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


def create_aoi_basemap(year_label: str, blend_mode: str = cfg.DEFAULT_BLEND_MODE, colormap: str = cfg.DEFAULT_COLORMAP, opacity: float = cfg.DEFAULT_OVERLAY_OPACITY) -> folium.Map:
    """Wrapper that builds the AOI basemap using map_utils.create_map_with_overlay.

    Keeps app.py small — actual implementation lives in map_utils.py.
    """
    return create_map_with_overlay(year_label, blend_mode=blend_mode, colormap=colormap, opacity=opacity)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🌡️ UHI Tracker")
st.sidebar.markdown(f"**Study area:** {cfg.AOI_NAME}")
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
st.title(f"Urban Heat Island Tracker — {cfg.AOI_NAME}")
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
        options=cfg.BLEND_MODES,
        index=cfg.BLEND_MODES.index(cfg.DEFAULT_BLEND_MODE) if cfg.DEFAULT_BLEND_MODE in cfg.BLEND_MODES else 0,
        help="Choose how the LST raster blends with the basemap.",
    )

    colormap = st.selectbox(
        "Colormap",
        options=cfg.AVAILABLE_COLORMAPS,
        index=cfg.AVAILABLE_COLORMAPS.index(cfg.DEFAULT_COLORMAP) if cfg.DEFAULT_COLORMAP in cfg.AVAILABLE_COLORMAPS else 0,
        help="Select a matplotlib colormap for the LST overlay.",
    )

    overlay_opacity = st.slider("Overlay opacity", min_value=0.0, max_value=1.0, value=float(cfg.DEFAULT_OVERLAY_OPACITY), step=0.05)

    st.markdown("### Nairobi study area")

    # Use the map_utils helper to get PNG data URI and metadata (cached)
    try:
        from map_utils import get_overlay_png_bytes

        @st.cache_data(show_spinner=False)
        def _get_cached_overlay_payload(y, cm):
            return get_overlay_png_bytes(y, cm)

        @st.cache_data(show_spinner="Rendering cached map HTML…", max_entries=8)
        def _get_cached_map_html_bytes(y, bm, cm, op):
            # Return rendered HTML bytes for the fully-built map (used for downloads)
            from map_utils import create_map_with_overlay

            m_full = create_map_with_overlay(y, blend_mode=bm, colormap=cm, opacity=op)
            return m_full.get_root().render().encode("utf-8")

        payload = _get_cached_overlay_payload(selected_year, colormap)

        # Persist UI selections in session_state for continuity
        st.session_state.setdefault('overlay_mode', overlay_mode)
        st.session_state.setdefault('colormap', colormap)
        st.session_state.setdefault('overlay_opacity', overlay_opacity)

        # Build map quickly using cached PNG data URI
        min_lon, min_lat, max_lon, max_lat = cfg.AOI_BBOX
        center = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
        m_quick = folium.Map(location=center, zoom_start=10, tiles=cfg.MAP_TILES)
        folium.raster_layers.ImageOverlay(
            image=payload["data_uri"],
            bounds=payload["bounds"],
            opacity=overlay_opacity,
            origin="upper",
        ).add_to(m_quick)

        # Determine bounds to use: prefer persisted bounds (map view), else payload
        def _pad_bounds(bounds, pad_frac: float = cfg.DEFAULT_MAP_PADDING):
            # bounds = [[lat_min, lon_min], [lat_max, lon_max]]
            (lat_min, lon_min), (lat_max, lon_max) = (bounds[0], bounds[1])
            lat_pad = (lat_max - lat_min) * pad_frac
            lon_pad = (lon_max - lon_min) * pad_frac
            return [[lat_min - lat_pad, lon_min - lon_pad], [lat_max + lat_pad, lon_max + lon_pad]]

        use_bounds = st.session_state.get('map_bounds', payload['bounds'])
        padded = _pad_bounds(use_bounds, cfg.DEFAULT_MAP_PADDING)
        try:
            m_quick.fit_bounds(padded)
        except Exception:
            try:
                m_quick.fit_bounds(payload["bounds"])
            except Exception:
                pass

        bm = overlay_mode.lower() if overlay_mode and overlay_mode != "Normal" else None
        if bm:
            from branca.element import Template, MacroElement

            script_html = f"""
            {{% macro script(this, kwargs) %}}
            <script>
            document.addEventListener('DOMContentLoaded', function() {{
                var imgs = document.querySelectorAll('.leaflet-image-layer');
                imgs.forEach(function(img) {{ img.style.mixBlendMode = '{bm}'; img.style.opacity = '{overlay_opacity}'; }});
            }});
            </script>
            {{% endmacro %}}
            """
            script = MacroElement()
            script._template = Template(script_html)
            m_quick.get_root().add_child(script)

        folium.Rectangle(
            bounds=[[min_lat, min_lon], [max_lat, max_lon]],
            color=cfg.AOI_BOUNDARY_COLOR,
            weight=cfg.AOI_BOUNDARY_WEIGHT,
            fill=False,
            opacity=cfg.AOI_BOUNDARY_OPACITY,
            tooltip=f"{cfg.AOI_NAME} AOI",
        ).add_to(m_quick)

        folium.LayerControl().add_to(m_quick)

        st_folium(m_quick, width=700, height=360)

        # Save current payload bounds into session_state so they persist across interactions
        st.session_state['map_bounds'] = payload['bounds']

        # --- Export / download buttons ---
        try:
            import base64

            # Use cached full-map HTML for downloads when possible
            try:
                html_bytes = _get_cached_map_html_bytes(selected_year, overlay_mode, colormap, overlay_opacity)
            except Exception:
                html_bytes = m_quick.get_root().render().encode("utf-8")
            png_b64 = payload["data_uri"].split(",", 1)[1]
            png_bytes = base64.b64decode(png_b64)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button("Download map (HTML)", data=html_bytes, file_name=f"lst_map_{selected_year}.html", mime="text/html")
            with col2:
                st.download_button("Download overlay (PNG)", data=png_bytes, file_name=f"lst_overlay_{selected_year}.png", mime="image/png")
            with col3:
                # Metrics CSV
                try:
                    metrics_csv = "metric,value\n"
                    if 'stats' in locals() and isinstance(stats, dict):
                        for k, v in stats.items():
                            metrics_csv += f"{k},{v}\n"
                    else:
                        metrics_csv += f"hotspot_pixels,{hotspots.sum()}\n"
                    st.download_button("Download metrics (CSV)", data=metrics_csv.encode('utf-8'), file_name=f"lst_metrics_{selected_year}.csv", mime="text/csv")
                except Exception:
                    pass
            # Extra column for GeoTIFF
            try:
                tif_path = os.path.join('data','raw', f'lst_{selected_year}.tif')
                if os.path.exists(tif_path):
                    with open(tif_path, 'rb') as fh:
                        tif_bytes = fh.read()
                    st.download_button("Download raw GeoTIFF", data=tif_bytes, file_name=f"lst_{selected_year}.tif", mime="application/octet-stream")
            except Exception:
                pass
        except Exception:
            pass
        except Exception:
            pass
    except Exception as e:
        # Fall back to original (slower) map builder
        st.warning(f"Could not use cached overlay: {e}")
        st_folium(create_aoi_basemap(selected_year, overlay_mode, colormap, overlay_opacity), width=700, height=360)

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
