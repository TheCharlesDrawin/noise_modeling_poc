"""Built-in source spectra used when measured drone data is unavailable."""

import math
from typing import Dict


OCTAVE_BANDS_HZ = (63, 125, 250, 500, 1000, 2000, 4000, 8000)
A_WEIGHTING_DB = (-26.2, -16.1, -8.6, -3.2, 0.0, 1.2, 1.0, -1.1)

# Engineering proxy for a medium agricultural multicopter in steady flight.
# These are octave-band sound-power levels (dB re 1 pW), not DJI-certified
# Agras measurements. Their A-weighted energetic sum is about 108 dB(A).
MEDIUM_AGRICULTURAL_DRONE_LW_DB = (100.0, 104.0, 108.0, 106.0, 103.0, 99.0, 95.0, 90.0)


def a_weighted_sum(levels_db) -> float:
    return 10.0 * math.log10(
        sum(10.0 ** ((level + correction) / 10.0) for level, correction in zip(levels_db, A_WEIGHTING_DB))
    )


def medium_agricultural_drone_properties(sample_count: int = 1) -> Dict[str, float]:
    """Return equal-time-normalized day-period source fields.

    NoiseModelling sums simultaneous sources energetically. Subtracting
    10*log10(N) from N route samples makes that sum the equal-time LAeq of
    one drone moving through those positions.
    """
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    route_average_correction = 10.0 * math.log10(sample_count)
    return {
        f"HZD{frequency}": level - route_average_correction
        for frequency, level in zip(OCTAVE_BANDS_HZ, MEDIUM_AGRICULTURAL_DRONE_LW_DB)
    }


def apply_medium_agricultural_profile(source_points_geojson: Dict, normalize_route: bool) -> Dict:
    features = source_points_geojson.get("features", [])
    sample_count = len(features) if normalize_route else 1
    signature = medium_agricultural_drone_properties(sample_count)
    for feature in features:
        feature.setdefault("properties", {}).update(signature)
        feature["properties"]["ACOUSTIC_PROFILE"] = "medium_agricultural_drone_proxy"
    return source_points_geojson
