import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from pyproj import Transformer

LEVEL_BREAKS = [-5, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
LEVEL_COLORS = [
    "#30123b",
    "#4145ab",
    "#4687e3",
    "#39b7ea",
    "#1cd5cb",
    "#24e68a",
    "#5ff45a",
    "#a4fc3c",
    "#dffa2f",
    "#f9d925",
    "#fbb61a",
    "#f98e09",
    "#ef5e1a",
    "#d7352a",
    "#b60f2e",
]


def _transform_position(coord: List[float], transformer: Transformer) -> List[float]:
    lon, lat = transformer.transform(coord[0], coord[1])
    return [lon, lat]


def _transform_geometry(geometry: Dict, transformer: Transformer) -> Dict:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")

    if geom_type == "Point":
        return {"type": "Point", "coordinates": _transform_position(coords, transformer)}
    if geom_type == "LineString":
        return {"type": "LineString", "coordinates": [_transform_position(c, transformer) for c in coords]}
    if geom_type == "Polygon":
        return {
            "type": "Polygon",
            "coordinates": [[_transform_position(c, transformer) for c in ring] for ring in coords],
        }
    if geom_type == "MultiPoint":
        return {"type": "MultiPoint", "coordinates": [_transform_position(c, transformer) for c in coords]}
    if geom_type == "MultiLineString":
        return {
            "type": "MultiLineString",
            "coordinates": [[_transform_position(c, transformer) for c in line] for line in coords],
        }
    if geom_type == "MultiPolygon":
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [[_transform_position(c, transformer) for c in ring] for ring in polygon]
                for polygon in coords
            ],
        }

    raise ValueError(f"Unsupported geometry type: {geom_type}")


def _to_wgs84(geojson: Dict, src_epsg: int) -> Dict:
    transformer = Transformer.from_crs(f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    features = geojson.get("features", [])
    transformed_features = []

    for feature in features:
        transformed_features.append(
            {
                "type": "Feature",
                "properties": feature.get("properties", {}),
                "geometry": _transform_geometry(feature["geometry"], transformer),
            }
        )

    return {"type": "FeatureCollection", "features": transformed_features}


def _iter_positions(geometry: Dict) -> Iterable[Tuple[float, float]]:
    geom_type = geometry["type"]
    coords = geometry["coordinates"]

    if geom_type == "Point":
        yield coords[0], coords[1]
        return
    if geom_type in ("LineString", "MultiPoint"):
        for p in coords:
            yield p[0], p[1]
        return
    if geom_type in ("Polygon", "MultiLineString"):
        for part in coords:
            for p in part:
                yield p[0], p[1]
        return
    if geom_type == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                for p in ring:
                    yield p[0], p[1]
        return

    raise ValueError(f"Unsupported geometry type: {geom_type}")


def _get_geojson_bounds(geojson: Dict) -> Optional[List[List[float]]]:
    min_lon = min_lat = float("inf")
    max_lon = max_lat = float("-inf")
    found = False

    for feature in geojson.get("features", []):
        for lon, lat in _iter_positions(feature["geometry"]):
            found = True
            min_lon = min(min_lon, lon)
            max_lon = max(max_lon, lon)
            min_lat = min(min_lat, lat)
            max_lat = max(max_lat, lat)

    if not found:
        return None

    return [[min_lat, min_lon], [max_lat, max_lon]]


def _get_center_from_source(source_geojson: Dict) -> Optional[List[float]]:
    features = source_geojson.get("features", [])
    if not features:
        return None
    geometry = features[0].get("geometry", {})
    if geometry.get("type") != "Point":
        return None
    lon, lat = geometry.get("coordinates", [None, None])[:2]
    if lon is None or lat is None:
        return None
    return [lat, lon]


def _noise_color(value: float) -> str:
    for idx in range(len(LEVEL_BREAKS) - 1):
        if LEVEL_BREAKS[idx] <= value < LEVEL_BREAKS[idx + 1]:
            return LEVEL_COLORS[idx]
    if value < LEVEL_BREAKS[0]:
        return LEVEL_COLORS[0]
    return LEVEL_COLORS[-1]


def _noise_opacity(value: float) -> float:
    min_level = LEVEL_BREAKS[0]
    max_level = LEVEL_BREAKS[-1]
    if value <= min_level:
        return 0.28
    if value >= max_level:
        return 0.9
    ratio = (value - min_level) / (max_level - min_level)
    return 0.28 + (0.62 * ratio)


def _noise_value(props: Dict) -> float:
    raw_level = props.get("ISOLVL", props.get("LAEQ", props.get("LEQ", 0)))
    try:
        return float(raw_level)
    except (TypeError, ValueError):
        return 0.0


def _add_legend(m) -> None:
    from branca.element import Element

    rows = []
    for idx, color in enumerate(LEVEL_COLORS):
        low = LEVEL_BREAKS[idx]
        high = LEVEL_BREAKS[idx + 1]
        rows.append(
            f'<div style="display:flex;align-items:center;margin:2px 0;">'
            f'<span style="display:inline-block;width:14px;height:14px;background:{color};margin-right:8px;border:1px solid #333;"></span>'
            f"<span>{low} to {high} dB</span>"
            f"</div>"
        )

    legend_html = (
        '<div style="position: fixed; bottom: 28px; right: 14px; z-index: 9999; '
        'background: rgba(255,255,255,0.94); border: 1px solid #666; border-radius: 6px; '
        'padding: 10px 12px; font-size: 12px; line-height: 1.2; box-shadow: 0 1px 8px rgba(0,0,0,0.25);">'
        '<div style="font-weight:700; margin-bottom:6px;">Noise Level</div>'
        + "".join(rows)
        + "</div>"
    )
    m.get_root().html.add_child(Element(legend_html))


def _load_geojson(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def export_folium_map(output_folder: Path, source_epsg: int = 3857) -> Optional[Path]:
    try:
        import folium
    except ModuleNotFoundError:
        raise ModuleNotFoundError("folium is not installed. Install it with: pip install folium")

    noise_map_path = output_folder / "noise_map.geojson"
    receivers_level_path = output_folder / "receivers_level.geojson"
    source_path = output_folder / "source.geojson"
    buildings_path = output_folder / "buildings.geojson"
    model_area_path = output_folder / "model_area.geojson"

    if noise_map_path.exists():
        primary_path = noise_map_path
        primary_name = "Noise Isosurfaces"
    elif receivers_level_path.exists():
        primary_path = receivers_level_path
        primary_name = "Receiver Levels"
    else:
        return None

    primary_geojson = _to_wgs84(_load_geojson(primary_path), source_epsg)

    source_geojson = _to_wgs84(_load_geojson(source_path), source_epsg) if source_path.exists() else None
    buildings_geojson = _to_wgs84(_load_geojson(buildings_path), source_epsg) if buildings_path.exists() else None
    model_area_geojson = _to_wgs84(_load_geojson(model_area_path), source_epsg) if model_area_path.exists() else None

    center = _get_center_from_source(source_geojson) if source_geojson else None
    if center is None:
        bounds = _get_geojson_bounds(primary_geojson)
        if bounds:
            center = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
        else:
            center = [0.0, 0.0]

    m = folium.Map(location=center, zoom_start=14, tiles=None, control_scale=True)
    folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street").add_to(m)

    def primary_style_fn(feature: Dict) -> Dict:
        props = feature.get("properties", {})
        level_value = _noise_value(props)
        color = _noise_color(level_value)
        return {
            "color": "#1e1e1e",
            "weight": 0.6,
            "fillColor": color,
            "fillOpacity": _noise_opacity(level_value),
        }

    tooltip_candidates = ["ISOLVL", "ISOLABEL", "LAEQ", "LEQ", "PERIOD"]
    tooltip_fields = []
    if primary_geojson.get("features"):
        first_props = primary_geojson["features"][0].get("properties", {})
        tooltip_fields = [k for k in tooltip_candidates if k in first_props]

    is_point_layer = all(
        f.get("geometry", {}).get("type") == "Point" for f in primary_geojson.get("features", [])
    )
    if is_point_layer:
        points_group = folium.FeatureGroup(name=primary_name)
        for feature in primary_geojson.get("features", []):
            geometry = feature.get("geometry", {})
            props = feature.get("properties", {})
            lon, lat = geometry.get("coordinates", [None, None])[:2]
            if lon is None or lat is None:
                continue
            level_value = _noise_value(props)
            color = _noise_color(level_value)
            popup_lines = [f"<b>Noise:</b> {level_value:.1f} dB"]
            for key in ("IDRECEIVER", "PERIOD", "LAEQ", "LEQ"):
                if key in props:
                    popup_lines.append(f"<b>{key}:</b> {props[key]}")
            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color="#202020",
                weight=0.5,
                fill=True,
                fill_color=color,
                fill_opacity=_noise_opacity(level_value),
                popup=folium.Popup("<br>".join(popup_lines), max_width=260),
            ).add_to(points_group)
        points_group.add_to(m)
    else:
        folium.GeoJson(
            primary_geojson,
            name=primary_name,
            style_function=primary_style_fn,
            tooltip=folium.features.GeoJsonTooltip(fields=tooltip_fields) if tooltip_fields else None,
        ).add_to(m)

    if model_area_geojson is not None:
        folium.GeoJson(
            model_area_geojson,
            name="Model Area",
            style_function=lambda _: {"color": "#444444", "weight": 2, "fillOpacity": 0},
        ).add_to(m)

    if buildings_geojson is not None:
        folium.GeoJson(
            buildings_geojson,
            name="Buildings",
            style_function=lambda _: {"color": "#666666", "weight": 0.5, "fillColor": "#999999", "fillOpacity": 0.2},
        ).add_to(m)

    if source_geojson is not None:
        source_group = folium.FeatureGroup(name="Source")
        for feature in source_geojson.get("features", []):
            geometry = feature.get("geometry", {})
            if geometry.get("type") != "Point":
                continue
            lon, lat = geometry.get("coordinates", [None, None])[:2]
            if lon is None or lat is None:
                continue
            folium.CircleMarker(
                location=[lat, lon],
                radius=7,
                color="#ffffff",
                weight=2,
                fill=True,
                fill_color="#e31a1c",
                fill_opacity=1.0,
            ).add_to(source_group)
        source_group.add_to(m)

    bounds = _get_geojson_bounds(primary_geojson)
    if bounds:
        m.fit_bounds(bounds)

    _add_legend(m)
    folium.LayerControl(collapsed=False).add_to(m)

    output_path = output_folder / "noise_map.html"
    m.save(str(output_path))
    return output_path
