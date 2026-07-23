import math
import tempfile
import unittest
from pathlib import Path

from acoustic_profiles import (
    MEDIUM_AGRICULTURAL_DRONE_LW_DB,
    a_weighted_sum,
    apply_medium_agricultural_profile,
)
from kml_utils import load_kml_routes
from gis_utils import add_agl_height_from_asc


class KmlRouteTests(unittest.TestCase):
    def test_reads_linestring(self):
        content = """<?xml version="1.0"?>
        <kml xmlns="http://www.opengis.net/kml/2.2">
          <Document><Placemark><LineString>
            <altitudeMode>relativeToGround</altitudeMode>
            <coordinates>35.0,32.0,100 35.1,32.1,110</coordinates>
          </LineString></Placemark></Document>
        </kml>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flight.kml"
            path.write_text(content, encoding="utf-8")
            result = load_kml_routes(path)

        self.assertEqual(len(result["features"]), 1)
        self.assertEqual(result["features"][0]["geometry"]["coordinates"][1], [35.1, 32.1, 110.0])
        self.assertEqual(result["features"][0]["properties"]["kml_altitude_mode"], "relativeToGround")

    def test_rejects_kml_without_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.kml"
            path.write_text("<kml/>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No route"):
                load_kml_routes(path)


class AcousticProfileTests(unittest.TestCase):
    def test_proxy_level_is_documented_value(self):
        self.assertAlmostEqual(a_weighted_sum(MEDIUM_AGRICULTURAL_DRONE_LW_DB), 108.03, places=2)

    def test_route_normalization_preserves_total_energy(self):
        geojson = {
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0, 10]}}
                for _ in range(4)
            ]
        }
        apply_medium_agricultural_profile(geojson, normalize_route=True)
        per_source = geojson["features"][0]["properties"]["HZD500"]
        combined = 10 * math.log10(4 * 10 ** (per_source / 10))
        self.assertAlmostEqual(combined, 106.0)

    def test_single_animation_frame_restores_full_profile(self):
        geojson = {
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0, 10]}}
            ]
        }
        apply_medium_agricultural_profile(geojson, normalize_route=False)
        self.assertEqual(geojson["features"][0]["properties"]["HZD500"], 106.0)


class TerrainHeightTests(unittest.TestCase):
    def test_adds_ground_elevation_to_agl_height(self):
        asc = """ncols 2
nrows 2
xllcorner 0
yllcorner 0
cellsize 10
NODATA_value -9999
30 40
10 20
"""
        geojson = {
            "features": [
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [5, 5, 0]}},
                {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [15, 15, 0]}},
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terrain.asc"
            path.write_text(asc, encoding="utf-8")
            add_agl_height_from_asc(geojson, path, 100)

        self.assertEqual(geojson["features"][0]["geometry"]["coordinates"][2], 110)
        self.assertEqual(geojson["features"][1]["geometry"]["coordinates"][2], 140)
        self.assertEqual(geojson["features"][1]["properties"]["HEIGHT_AGL"], 100)


if __name__ == "__main__":
    unittest.main()
