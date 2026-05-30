import os, sys
sys.path.insert(0, os.getcwd())

import numpy as np
import pandas as pd
import pytest

from analysis import (
    compute_uhi_intensity,
    detect_hotspots,
    detect_cool_islands,
    compute_temperature_change,
    summarise_by_zone,
    make_simple_urban_mask,
)


def test_compute_uhi_intensity_basic():
    lst = np.array([[30.0, 35.0], [40.0, 20.0]], dtype=np.float32)
    urban_mask = np.array([[False, True], [True, False]])
    stats = compute_uhi_intensity(lst, urban_mask)
    assert 'uhi_intensity' in stats
    assert pytest.approx(stats['urban_mean_celsius']) == (35.0 + 40.0) / 2


def test_detect_hotspots_and_cool_islands():
    rng = np.random.default_rng(0)
    arr = rng.normal(loc=30.0, scale=5.0, size=(50, 50)).astype(np.float32)
    hotspots = detect_hotspots(arr, percentile=95)
    cool = detect_cool_islands(arr, percentile=5)
    assert hotspots.shape == arr.shape
    assert cool.shape == arr.shape


def test_temperature_change_shape_mismatch():
    a = np.zeros((10, 10))
    b = np.zeros((8, 8))
    with pytest.raises(ValueError):
        _ = compute_temperature_change(a, b)


def test_summarise_by_zone_and_mask():
    lst = np.arange(16, dtype=np.float32).reshape((4, 4))
    zones = {
        'A': np.array([[True, True, False, False]] * 4),
        'B': np.array([[False, False, True, True]] * 4),
    }
    df = summarise_by_zone(lst, zones)
    assert isinstance(df, pd.DataFrame)
    assert 'zone' in df.columns


def test_make_simple_urban_mask():
    lst = np.array([[32.0, 34.0], [33.0, 31.0]])
    mask = make_simple_urban_mask(lst, threshold_celsius=33.0)
    assert mask.dtype == bool
    assert mask.sum() == 2
