import folium
import rasterio
import rasterio.warp as warp
import numpy as np
import matplotlib.cm as cm
import matplotlib.colors as colors
from pathlib import Path

path = Path('data/raw/lst_2023.tif')
with rasterio.open(path) as src:
    data = src.read(1).astype(np.float32)
    data[data == src.nodata] = np.nan
    geo_bounds = warp.transform_bounds(
        src.crs,
        'EPSG:4326',
        src.bounds.left,
        src.bounds.bottom,
        src.bounds.right,
        src.bounds.top,
        densify_pts=21,
    )
    bounds = [[geo_bounds[1], geo_bounds[0]], [geo_bounds[3], geo_bounds[2]]]

vmin, vmax = np.nanpercentile(data, [2, 98])
norm = colors.Normalize(vmin=vmin, vmax=vmax, clip=True)
rgba = cm.get_cmap('RdYlBu_r')(norm(np.nan_to_num(data, nan=vmin)))
rgba[..., 3] = np.where(np.isnan(data), 0.0, 0.75)
overlay = (rgba * 255).astype(np.uint8)

m = folium.Map(location=[-1.275, 36.85], zoom_start=10, tiles='CartoDB positron')
folium.raster_layers.ImageOverlay(
    image=overlay,
    bounds=bounds,
    opacity=0.55,
    origin='upper',
).add_to(m)
m.save('tmp_map.html')
print('saved tmp_map.html')
