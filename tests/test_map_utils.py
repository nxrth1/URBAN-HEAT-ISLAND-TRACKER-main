import os, sys
sys.path.insert(0, os.getcwd())

import numpy as np
import pytest

import rasterio
from rasterio.transform import from_origin

from map_utils import get_overlay_png_bytes, create_map_with_overlay


def _write_test_tif(path):
    arr = np.full((10, 12), 30.0, dtype=np.float32)
    transform = from_origin(36.6, -1.1 + 0.5, 0.01, 0.01)
    # Ensure directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Ensure rasterio uses its bundled PROJ DB (avoid system PostGIS conflicts on Windows)
    try:
        from pathlib import Path
        rasterio_proj = Path(rasterio.__file__).resolve().parent / 'proj_data'
        if rasterio_proj.exists():
            os.environ['PROJ_LIB'] = str(rasterio_proj)
    except Exception:
        pass
    with rasterio.open(
        path,
        'w',
        driver='GTiff',
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype=arr.dtype,
        crs='EPSG:4326',
        transform=transform,
    ) as dst:
        dst.write(arr, 1)


def test_get_overlay_png_bytes_and_map(tmp_path):
    # create a small tif in data/raw
    data_dir = os.path.join(os.getcwd(), 'data', 'raw')
    os.makedirs(data_dir, exist_ok=True)
    tif_path = os.path.join(data_dir, 'lst_test.tif')
    _write_test_tif(tif_path)

    payload = get_overlay_png_bytes('test', cmap_name='viridis')
    assert 'data_uri' in payload
    assert payload['data_uri'].startswith('data:image/png;base64,')
    assert 'bounds' in payload

    # Create a map (smoke) — should not raise
    m = create_map_with_overlay('test', blend_mode='Normal', colormap='viridis', opacity=0.5)
    assert hasattr(m, 'get_root')
