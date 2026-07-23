import pyproj
from pyproj import Transformer
import pyproj
from pathlib import Path
from typing import Tuple
from typing import Dict, Iterable, List, Optional


def _extract_epsg_from_geojson_crs(geojson: Dict) -> Optional[int]:
    crs = geojson.get("crs", {})
    props = crs.get("properties", {})
    name = str(props.get("name", "")).upper()
    if "3857" in name:
        return 3857
    if "4326" in name or "CRS84" in name:
        return 4326
    return None


def _infer_epsg_from_coordinates(coords: List[float]) -> int:
    if len(coords) < 2:
        return 3857
    x, y = coords[0], coords[1]
    if -180 <= x <= 180 and -90 <= y <= 90:
        return 4326
    return 3857


def _convert_xy(x: float, y: float, src_epsg: int, dst_epsg: int) -> List[float]:
    if src_epsg == dst_epsg:
        return [x, y]
    tx = Transformer.from_crs(f"EPSG:{src_epsg}", f"EPSG:{dst_epsg}", always_xy=True)
    xx, yy = tx.transform(x, y)
    return [xx, yy]


def _iter_linestring_segments(coords: List[List[float]]) -> Iterable[List[List[float]]]:
    if len(coords) < 2:
        return
    for i in range(len(coords) - 1):
        yield [coords[i], coords[i + 1]]


def _distance_2d(a: List[float], b: List[float]) -> float:
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return (dx * dx + dy * dy) ** 0.5


def _sample_line(coords: List[List[float]], step_meters: float) -> List[List[float]]:
    if len(coords) == 0:
        return []
    if len(coords) == 1:
        return [coords[0]]

    sampled = [coords[0]]
    carry = 0.0

    for start, end in _iter_linestring_segments(coords):
        seg_len = _distance_2d(start, end)
        if seg_len <= 0:
            continue
        ux = (end[0] - start[0]) / seg_len
        uy = (end[1] - start[1]) / seg_len

        distance = step_meters - carry
        while distance <= seg_len:
            sampled.append([start[0] + ux * distance, start[1] + uy * distance])
            distance += step_meters

        carry = max(0.0, distance - seg_len)

    if sampled[-1][0] != coords[-1][0] or sampled[-1][1] != coords[-1][1]:
        sampled.append(coords[-1])

    return sampled


def source_geojson_to_points(source_geojson: Dict, source_height: float, route_step_meters: float = 25.0) -> Dict:
    if route_step_meters <= 0:
        raise ValueError("route_step_meters must be > 0")

    epsg = _extract_epsg_from_geojson_crs(source_geojson)
    features = source_geojson.get("features", [])

    first_coord = None
    for feature in features:
        geometry = feature.get("geometry", {})
        gtype = geometry.get("type")
        coords = geometry.get("coordinates", [])
        if gtype == "Point" and len(coords) >= 2:
            first_coord = coords
            break
        if gtype == "LineString" and len(coords) >= 1 and len(coords[0]) >= 2:
            first_coord = coords[0]
            break
        if gtype == "MultiLineString" and len(coords) >= 1 and len(coords[0]) >= 1 and len(coords[0][0]) >= 2:
            first_coord = coords[0][0]
            break
        if gtype == "MultiPoint" and len(coords) >= 1 and len(coords[0]) >= 2:
            first_coord = coords[0]
            break

    src_epsg = epsg if epsg is not None else _infer_epsg_from_coordinates(first_coord or [0, 0])
    out_features = []
    pk = 1

    for feature in features:
        geometry = feature.get("geometry", {})
        gtype = geometry.get("type")
        coords = geometry.get("coordinates", [])
        base_props = dict(feature.get("properties", {}))

        if gtype == "Point":
            x, y = _convert_xy(coords[0], coords[1], src_epsg, 3857)
            out_features.append(
                {
                    "type": "Feature",
                    "properties": {**base_props, "PK": pk},
                    "geometry": {"type": "Point", "coordinates": [x, y, source_height]},
                }
            )
            pk += 1
            continue

        if gtype == "MultiPoint":
            for p in coords:
                x, y = _convert_xy(p[0], p[1], src_epsg, 3857)
                out_features.append(
                    {
                        "type": "Feature",
                        "properties": {**base_props, "PK": pk},
                        "geometry": {"type": "Point", "coordinates": [x, y, source_height]},
                    }
                )
                pk += 1
            continue

        if gtype == "LineString":
            line_3857 = [_convert_xy(p[0], p[1], src_epsg, 3857) for p in coords]
            sampled = _sample_line(line_3857, route_step_meters)
            for p in sampled:
                out_features.append(
                    {
                        "type": "Feature",
                        "properties": {**base_props, "PK": pk},
                        "geometry": {"type": "Point", "coordinates": [p[0], p[1], source_height]},
                    }
                )
                pk += 1
            continue

        if gtype == "MultiLineString":
            for line in coords:
                line_3857 = [_convert_xy(p[0], p[1], src_epsg, 3857) for p in line]
                sampled = _sample_line(line_3857, route_step_meters)
                for p in sampled:
                    out_features.append(
                        {
                            "type": "Feature",
                            "properties": {**base_props, "PK": pk},
                            "geometry": {"type": "Point", "coordinates": [p[0], p[1], source_height]},
                        }
                    )
                    pk += 1
            continue

        raise ValueError(f"Unsupported source geometry type: {gtype}")

    return {
        "type": "FeatureCollection",
        "name": source_geojson.get("name", "Source"),
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3857"}},
        "features": out_features,
    }


def add_agl_height_from_asc(
    source_points_geojson: Dict,
    asc_path: Path,
    height_agl_meters: float,
) -> Dict:
    """Set point Z to terrain elevation plus the requested AGL height.

    ESRI ASCII-grid rows are stored north-to-south while ``yllcorner`` is the
    southern edge, hence the row-index inversion below. Nearest-cell sampling
    is sufficient for the relatively coarse bundled terrain model.
    """
    if height_agl_meters < 0:
        raise ValueError("height_agl_meters must be non-negative")

    with open(asc_path, "r", encoding="utf-8") as asc_file:
        header = {}
        for _ in range(6):
            key, value = asc_file.readline().split()[:2]
            header[key.lower()] = float(value)
        rows = [[float(value) for value in line.split()] for line in asc_file if line.strip()]

    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    x_origin = header.get("xllcorner", header.get("xllcenter"))
    y_origin = header.get("yllcorner", header.get("yllcenter"))
    cellsize = header["cellsize"]
    nodata = header.get("nodata_value")

    if x_origin is None or y_origin is None or len(rows) != nrows or any(len(row) != ncols for row in rows):
        raise ValueError(f"Invalid ESRI ASCII grid: {asc_path}")

    for feature in source_points_geojson.get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        x, y = float(coordinates[0]), float(coordinates[1])
        column = int((x - x_origin) // cellsize)
        row_from_south = int((y - y_origin) // cellsize)
        row = nrows - 1 - row_from_south
        if not (0 <= column < ncols and 0 <= row < nrows):
            raise ValueError(f"Route point ({x}, {y}) is outside terrain grid {asc_path}")
        ground_elevation = rows[row][column]
        if nodata is not None and ground_elevation == nodata:
            raise ValueError(f"Route point ({x}, {y}) falls on NODATA terrain in {asc_path}")
        coordinates[:] = [x, y, ground_elevation + height_agl_meters]
        properties = feature.setdefault("properties", {})
        properties["GROUND_ELEVATION"] = ground_elevation
        properties["HEIGHT_AGL"] = height_agl_meters

    return source_points_geojson


def points_to_bounding_square_geojson(source_points_geojson: Dict, size_meters: float = 2000.0) -> Dict:
    features = source_points_geojson.get("features", [])
    if not features:
        raise ValueError("No source points available to build modelling area")

    xs = []
    ys = []
    for feature in features:
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        xs.append(coords[0])
        ys.append(coords[1])

    if not xs or not ys:
        raise ValueError("Invalid source points geometry")

    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    route_w = max_x - min_x
    route_h = max_y - min_y
    side = max(size_meters, route_w, route_h)
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    half = side / 2

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [cx - half, cy - half],
                            [cx + half, cy - half],
                            [cx + half, cy + half],
                            [cx - half, cy + half],
                            [cx - half, cy - half],
                        ]
                    ],
                },
                "properties": {},
            }
        ],
    }


def get_geojson_coordinates(geojson: dict) -> Tuple[float, float, float]:
    if geojson.get("type") == "FeatureCollection":
        # Get first feature's coordinates
        coordinates = geojson["features"][0]["geometry"]["coordinates"]
    elif geojson.get("type") == "Feature":
        # Get feature's coordinates
        coordinates = geojson["geometry"]["coordinates"]
    elif geojson.get("type") == "Point":
        # Direct point geometry
        coordinates = geojson["coordinates"]
    else:
        raise ValueError("GeoJSON must contain a Point geometry")
    
    return coordinates


def point_to_square(geojson: dict, size_meters: int = 100, use_utm: bool = False) -> dict:
    lon, lat, alt = get_geojson_coordinates(geojson)

    if use_utm:
        # Convert to UTM (automatically determine zone from coordinates)
        wsg84_lon, wsg84_lat = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform(lon, lat)
        utm_epsg = pyproj.database.query_utm_crs_info('WGS 84', pyproj.aoi.AreaOfInterest(wsg84_lon, wsg84_lon, wsg84_lat, wsg84_lat))[0].code
        utm_crs = pyproj.CRS.from_epsg(utm_epsg)
        
        center_x, center_y = Transformer.from_crs("EPSG:3857", utm_crs, always_xy=True).transform(lon, lat)

        # Calculate half the size
        half_size = size_meters / 2
        
        # Calculate bounding box corners
        min_x = center_x - half_size
        max_x = center_x + half_size
        min_y = center_y - half_size
        max_y = center_y + half_size

        # Create GeoJSON FeatureCollection with polygon and transform coordinates back to EPSG:3857
        # as noisemodelling does not handles UTM appropriately
        transformer = Transformer.from_crs(utm_crs, 'EPSG:3857', always_xy=True)
        
        geojson_result = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        transformer.transform(min_x, min_y),
                        transformer.transform(max_x, min_y),
                        transformer.transform(max_x, max_y),
                        transformer.transform(min_x, max_y),
                        transformer.transform(min_x, min_y)  # Close the ring
                    ]]
                },
                "properties": {}
            }]
        }
        
    else:
        center_x, center_y = lon, lat

        # Calculate half the size
        half_size = size_meters / 2
        
        # Calculate bounding box corners
        min_x = center_x - half_size
        max_x = center_x + half_size
        min_y = center_y - half_size
        max_y = center_y + half_size
    
        # Create GeoJSON FeatureCollection with polygon
        geojson_result = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        # transformer.transform(min_x, min_y),
                        # transformer.transform(max_x, min_y),
                        # transformer.transform(max_x, max_y),
                        # transformer.transform(min_x, max_y),
                        # transformer.transform(min_x, min_y)  # Close the ring
                        [min_x, min_y],
                        [max_x, min_y],
                        [max_x, max_y],
                        [min_x, max_y],
                        [min_x, min_y]  # Close the ring
                    ]]
                },
                "properties": {}
            }]
        }

    return geojson_result
