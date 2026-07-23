"""Small, dependency-free KML route reader.

The acoustic model needs a route geometry, not KML styling.  This module
therefore intentionally supports the two common route encodings only:
KML LineString and Google gx:Track.
"""

from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET


def _parse_coordinates(text: str) -> List[List[float]]:
    coordinates: List[List[float]] = []
    for token in (text or "").replace("\n", " ").split():
        values = token.split(",")
        if len(values) < 2:
            continue
        coordinate = [float(values[0]), float(values[1])]
        if len(values) >= 3 and values[2] != "":
            coordinate.append(float(values[2]))
        coordinates.append(coordinate)
    return coordinates


def load_kml_routes(path: Path) -> Dict:
    """Return all KML LineString/gx:Track routes as WGS84 GeoJSON."""
    root = ET.parse(path).getroot()
    features = []

    for index, line in enumerate(root.findall(".//{*}LineString"), start=1):
        node = line.find("{*}coordinates")
        coordinates = _parse_coordinates(node.text if node is not None else "")
        if len(coordinates) >= 2:
            altitude_node = line.find("{*}altitudeMode")
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "route_id": index,
                        "kml_altitude_mode": (
                            altitude_node.text.strip()
                            if altitude_node is not None and altitude_node.text
                            else "unspecified"
                        ),
                    },
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )

    # gx:Track stores each position in a separate <gx:coord> as "lon lat alt".
    for track in root.findall(".//{*}Track"):
        coordinates = []
        for node in track.findall("{*}coord"):
            values = (node.text or "").split()
            if len(values) >= 2:
                coordinates.append([float(value) for value in values[:3]])
        if len(coordinates) >= 2:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "route_id": len(features) + 1,
                        "kml_altitude_mode": "gx:Track",
                    },
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )

    if not features:
        raise ValueError(f"No route LineString or gx:Track with at least two coordinates found in {path}")

    return {
        "type": "FeatureCollection",
        "name": path.stem,
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
