import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from matplotlib import colors

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


def _load_geojson(path: Path) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_route_points(source_geojson_3857: Dict) -> Tuple[np.ndarray, np.ndarray]:
    xs: List[float] = []
    ys: List[float] = []
    for feature in source_geojson_3857.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        xs.append(float(coords[0]))
        ys.append(float(coords[1]))
    return np.asarray(xs), np.asarray(ys)


def _extract_level_value(props: Dict) -> float:
    raw = props.get("ISOLVL", props.get("LAEQ", props.get("LEQ", 0.0)))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _polygon_rings(feature: Dict) -> List[List[List[float]]]:
    geometry = feature.get("geometry", {})
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    rings: List[List[List[float]]] = []
    if geom_type == "Polygon":
        if coords:
            rings.append(coords[0])
    elif geom_type == "MultiPolygon":
        for poly in coords:
            if poly:
                rings.append(poly[0])
    return rings


def _draw_noise_polygons(ax, noise_map_geojson: Dict):
    features = noise_map_geojson.get("features", [])
    if not features:
        return None, None, None

    values = np.asarray([_extract_level_value(f.get("properties", {})) for f in features], dtype=float)
    level_breaks = _compute_level_breaks(values, len(LEVEL_COLORS))
    cmap = colors.ListedColormap(LEVEL_COLORS)
    norm = colors.BoundaryNorm(level_breaks, cmap.N, clip=True)
    vmin = float(level_breaks[0])
    vmax = float(level_breaks[-1])

    for feature in features:
        level = _extract_level_value(feature.get("properties", {}))
        color = cmap(norm(level))
        for ring in _polygon_rings(feature):
            if len(ring) < 3:
                continue
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.fill(xs, ys, facecolor=color, edgecolor="#1a1a1a", linewidth=0.2, alpha=0.75, zorder=1)

    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    return sm, vmin, vmax


def _draw_receivers_fallback(ax, receivers_level_geojson: Dict):
    xs: List[float] = []
    ys: List[float] = []
    levels: List[float] = []

    for feature in receivers_level_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        xs.append(float(coords[0]))
        ys.append(float(coords[1]))
        levels.append(_extract_level_value(feature.get("properties", {})))

    if len(xs) < 3:
        return None, None, None

    xs_arr = np.asarray(xs)
    ys_arr = np.asarray(ys)
    lv_arr = np.asarray(levels)

    level_breaks = _compute_level_breaks(lv_arr, len(LEVEL_COLORS))
    cmap = colors.ListedColormap(LEVEL_COLORS)
    norm = colors.BoundaryNorm(level_breaks, cmap.N, clip=True)
    vmin = float(level_breaks[0])
    vmax = float(level_breaks[-1])

    tri = mtri.Triangulation(xs_arr, ys_arr)
    contour = ax.tricontourf(
        tri,
        lv_arr,
        levels=level_breaks,
        cmap=cmap,
        norm=norm,
        alpha=0.85,
        zorder=1,
    )
    return contour, vmin, vmax


def _extract_receivers_arrays(receivers_level_geojson: Dict) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: List[Tuple[int, float, float, float]] = []

    for feature in receivers_level_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        props = feature.get("properties", {})
        receiver_id = props.get("IDRECEIVER")
        try:
            receiver_id = int(receiver_id)
        except (TypeError, ValueError):
            receiver_id = -1
        x = float(coords[0])
        y = float(coords[1])
        level = _extract_level_value(props)
        rows.append((receiver_id, x, y, level))

    # Exports can arrive in arbitrary row order; use a stable ordering across frames.
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    xs = np.asarray([row[1] for row in rows], dtype=float)
    ys = np.asarray([row[2] for row in rows], dtype=float)
    levels = np.asarray([row[3] for row in rows], dtype=float)
    return xs, ys, levels


def _percentile(sorted_values: np.ndarray, p: float) -> float:
    if sorted_values.size == 0:
        return 0.0
    if sorted_values.size == 1:
        return float(sorted_values[0])
    p = max(0.0, min(1.0, p))
    idx = p * (sorted_values.size - 1)
    lo = int(idx)
    hi = min(lo + 1, sorted_values.size - 1)
    frac = idx - lo
    return float(sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac)


def _compute_level_breaks(values: np.ndarray, bin_count: int) -> np.ndarray:
    if values.size == 0:
        return np.linspace(0.0, float(bin_count), bin_count + 1)

    sorted_values = np.sort(values.astype(float))
    lo = _percentile(sorted_values, 0.05)
    hi = _percentile(sorted_values, 0.95)

    if hi - lo < 0.5:
        lo = float(np.min(sorted_values) - 0.25)
        hi = float(np.max(sorted_values) + 0.25)
    if hi - lo < 0.01:
        hi = lo + 1.0

    breaks = np.linspace(lo, hi, bin_count + 1)
    breaks[0] = min(float(breaks[0]), float(np.min(sorted_values)))
    breaks[-1] = max(float(breaks[-1]), float(np.max(sorted_values)))
    return breaks


def _get_bounds(features: List[Dict]) -> Optional[Tuple[float, float, float, float]]:
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    found = False

    for feature in features:
        geometry = feature.get("geometry", {})
        geom_type = geometry.get("type")
        coords = geometry.get("coordinates", [])
        points: List[List[float]] = []

        if geom_type == "Point":
            points = [coords]
        elif geom_type in ("LineString", "MultiPoint"):
            points = coords
        elif geom_type in ("Polygon", "MultiLineString"):
            for part in coords:
                points.extend(part)
        elif geom_type == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    points.extend(ring)

        for p in points:
            if len(p) < 2:
                continue
            found = True
            min_x = min(min_x, float(p[0]))
            max_x = max(max_x, float(p[0]))
            min_y = min(min_y, float(p[1]))
            max_y = max(max_y, float(p[1]))

    if not found:
        return None
    return min_x, max_x, min_y, max_y


def export_route_noise_animation(
    output_folder: Path,
    source_geojson_3857: Dict,
    fps: int = 2,
    receivers_level_frame_paths: Optional[Sequence[Path]] = None,
) -> Path:
    route_x, route_y = _extract_route_points(source_geojson_3857)
    if route_x.size == 0:
        raise ValueError("Cannot export route animation: source route has no point features.")

    noise_map_path = output_folder / "noise_map.geojson"
    receivers_level_path = output_folder / "receivers_level.geojson"

    fig, ax = plt.subplots(figsize=(10, 8), dpi=120)

    colorbar_ref = None
    contour_levels = None
    contour_tri = None
    contour_frame_values = None
    contour_holder = [None]

    if receivers_level_frame_paths:
        frame_arrays: List[np.ndarray] = []
        base_x = None
        base_y = None

        for frame_path in receivers_level_frame_paths:
            if not frame_path.exists():
                continue
            frame_geojson = _load_geojson(frame_path)
            frame_x, frame_y, frame_level = _extract_receivers_arrays(frame_geojson)
            if frame_x.size < 3:
                continue
            if base_x is None:
                base_x = frame_x
                base_y = frame_y
            elif (
                frame_x.size != base_x.size
                or frame_y.size != base_y.size
                or not np.allclose(frame_x, base_x)
                or not np.allclose(frame_y, base_y)
            ):
                raise ValueError("Inconsistent receivers across route frames; cannot animate changing noise map.")
            frame_arrays.append(frame_level)

        if not frame_arrays or base_x is None or base_y is None:
            raise ValueError("No valid route-frame receiver files found for animation.")

        contour_frame_values = np.vstack(frame_arrays)
        contour_levels = _compute_level_breaks(contour_frame_values.reshape(-1), len(LEVEL_COLORS))
        cmap = colors.ListedColormap(LEVEL_COLORS)
        norm = colors.BoundaryNorm(contour_levels, cmap.N, clip=True)
        vmin = float(contour_levels[0])
        vmax = float(contour_levels[-1])
        contour_tri = mtri.Triangulation(base_x, base_y)
        contour_holder[0] = ax.tricontourf(
            contour_tri,
            contour_frame_values[0],
            levels=contour_levels,
            cmap=cmap,
            norm=norm,
            alpha=0.85,
            zorder=1,
        )
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        sm.set_array([])
        colorbar_ref = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
        colorbar_ref.set_label(f"Noise level ({vmin:.1f} to {vmax:.1f})")
        bounds = (
            float(np.nanmin(base_x)),
            float(np.nanmax(base_x)),
            float(np.nanmin(base_y)),
            float(np.nanmax(base_y)),
        )
        frame_count = min(route_x.size, contour_frame_values.shape[0])
    elif noise_map_path.exists():
        noise_map_geojson = _load_geojson(noise_map_path)
        sm, vmin, vmax = _draw_noise_polygons(ax, noise_map_geojson)
        if sm is not None:
            colorbar_ref = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02)
            colorbar_ref.set_label(f"Noise level ({vmin:.1f} to {vmax:.1f})")
        bounds = _get_bounds(noise_map_geojson.get("features", []))
        frame_count = route_x.size
    elif receivers_level_path.exists():
        receivers_level_geojson = _load_geojson(receivers_level_path)
        contour, vmin, vmax = _draw_receivers_fallback(ax, receivers_level_geojson)
        if contour is not None:
            colorbar_ref = fig.colorbar(contour, ax=ax, fraction=0.03, pad=0.02)
            colorbar_ref.set_label(f"Noise level ({vmin:.1f} to {vmax:.1f})")
        bounds = _get_bounds(receivers_level_geojson.get("features", []))
        frame_count = route_x.size
    else:
        raise FileNotFoundError("No noise layer found. Expected noise_map.geojson or receivers_level.geojson.")

    ax.plot(route_x, route_y, color="#ffffff", linewidth=1.2, alpha=0.9, zorder=5)
    ax.scatter(route_x, route_y, c="#f7f7f7", s=8, edgecolors="#111111", linewidths=0.2, alpha=0.8, zorder=6)
    moving_point = ax.scatter(
        [route_x[0]],
        [route_y[0]],
        c="#ff1f1f",
        s=130,
        edgecolors="#ffffff",
        linewidths=1.2,
        zorder=10,
    )
    title = ax.set_title(f"Noise map along route (1/{frame_count})")

    if bounds is None:
        min_x = float(route_x.min())
        max_x = float(route_x.max())
        min_y = float(route_y.min())
        max_y = float(route_y.max())
    else:
        min_x, max_x, min_y, max_y = bounds

    margin_x = max((max_x - min_x) * 0.05, 100.0)
    margin_y = max((max_y - min_y) * 0.05, 100.0)
    ax.set_xlim(min_x - margin_x, max_x + margin_x)
    ax.set_ylim(min_y - margin_y, max_y + margin_y)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("X (EPSG:3857)")
    ax.set_ylabel("Y (EPSG:3857)")

    def _update(index: int):
        if contour_frame_values is not None and contour_tri is not None and contour_levels is not None:
            if contour_holder[0] is not None:
                for coll in contour_holder[0].collections:
                    coll.remove()
            contour_holder[0] = ax.tricontourf(
                contour_tri,
                contour_frame_values[index],
                levels=contour_levels,
                cmap=colors.ListedColormap(LEVEL_COLORS),
                norm=colors.BoundaryNorm(contour_levels, len(LEVEL_COLORS), clip=True),
                alpha=0.85,
                zorder=1,
            )
        moving_point.set_offsets(np.array([[route_x[index], route_y[index]]]))
        title.set_text(f"Noise map along route ({index + 1}/{frame_count})")
        return moving_point, title

    ani = animation.FuncAnimation(
        fig,
        _update,
        frames=frame_count,
        blit=False,
        interval=1000 / max(1, fps),
    )

    output_path = output_folder / "route_noise_animation.gif"
    writer = animation.PillowWriter(fps=max(1, fps))
    ani.save(str(output_path), writer=writer)
    plt.close(fig)
    return output_path


def _build_plotly_discrete_colorscale(level_breaks: np.ndarray) -> List[List[object]]:
    if level_breaks.size < 2:
        return [[0.0, LEVEL_COLORS[0]], [1.0, LEVEL_COLORS[-1]]]

    lo = float(level_breaks[0])
    hi = float(level_breaks[-1])
    if hi <= lo:
        hi = lo + 1.0

    scale: List[List[object]] = []
    for idx, color in enumerate(LEVEL_COLORS):
        left = (float(level_breaks[idx]) - lo) / (hi - lo)
        right = (float(level_breaks[idx + 1]) - lo) / (hi - lo)
        left = max(0.0, min(1.0, left))
        right = max(0.0, min(1.0, right))
        scale.append([left, color])
        scale.append([right, color])
    return scale


def _extract_dem_grid(dem_geojson: Dict, max_cells: int = 20000) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    rows: List[Tuple[float, float, float]] = []
    for feature in dem_geojson.get("features", []):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        z = feature.get("properties", {}).get("Z")
        if z is None:
            continue
        try:
            rows.append((float(coords[0]), float(coords[1]), float(z)))
        except (TypeError, ValueError):
            continue

    if not rows:
        return None

    xs = sorted({r[0] for r in rows})
    ys = sorted({r[1] for r in rows})
    if len(xs) * len(ys) > max_cells:
        return None

    x_idx = {x: i for i, x in enumerate(xs)}
    y_idx = {y: i for i, y in enumerate(ys)}
    z_grid = np.full((len(ys), len(xs)), np.nan, dtype=float)
    for x, y, z in rows:
        z_grid[y_idx[y], x_idx[x]] = z

    if np.isnan(z_grid).all():
        return None

    if np.isnan(z_grid).any():
        fill = float(np.nanmean(z_grid))
        z_grid = np.where(np.isnan(z_grid), fill, z_grid)

    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), z_grid


def _build_buildings_wireframe(
    buildings_geojson: Dict,
    center_x: float,
    center_y: float,
    z_base: float,
    max_buildings: int = 260,
) -> Tuple[List[float], List[float], List[float]]:
    x_lines: List[float] = []
    y_lines: List[float] = []
    z_lines: List[float] = []

    features = buildings_geojson.get("features", [])[:max_buildings]
    for feature in features:
        height_raw = feature.get("properties", {}).get("HEIGHT", 8.0)
        try:
            height = float(height_raw)
        except (TypeError, ValueError):
            height = 8.0
        height = max(2.0, min(80.0, height))

        for ring in _polygon_rings(feature):
            if len(ring) < 3:
                continue

            for p in ring:
                x_lines.append(float(p[0]) - center_x)
                y_lines.append(float(p[1]) - center_y)
                z_lines.append(z_base)
            x_lines.append(None)
            y_lines.append(None)
            z_lines.append(None)

            for p in ring:
                x_lines.append(float(p[0]) - center_x)
                y_lines.append(float(p[1]) - center_y)
                z_lines.append(z_base + height)
            x_lines.append(None)
            y_lines.append(None)
            z_lines.append(None)

            step = max(1, len(ring) // 6)
            for p in ring[::step]:
                x0 = float(p[0]) - center_x
                y0 = float(p[1]) - center_y
                x_lines.extend([x0, x0, None])
                y_lines.extend([y0, y0, None])
                z_lines.extend([z_base, z_base + height, None])

    return x_lines, y_lines, z_lines


def export_digital_twin_flyover(
    output_folder: Path,
    source_geojson_3857: Dict,
    receivers_level_frame_paths: Optional[Sequence[Path]] = None,
    fps: int = 2,
) -> Path:
    try:
        import plotly.graph_objects as go
    except ModuleNotFoundError:
        raise ModuleNotFoundError("plotly is required for 3D flyover export. Install with: pip install plotly")

    route_x, route_y = _extract_route_points(source_geojson_3857)
    if route_x.size == 0:
        raise ValueError("Cannot export 3D flyover: source route has no point features.")

    buildings_path = output_folder / "buildings.geojson"
    dem_path = output_folder / "dem.geojson"
    receivers_level_path = output_folder / "receivers_level.geojson"

    if receivers_level_frame_paths:
        existing_paths = [p for p in receivers_level_frame_paths if p.exists()]
    else:
        existing_paths = []
    if not existing_paths and receivers_level_path.exists():
        existing_paths = [receivers_level_path]
    if not existing_paths:
        raise FileNotFoundError("No receiver level data found for 3D flyover.")

    first_frame_geojson = _load_geojson(existing_paths[0])
    base_x, base_y, base_levels = _extract_receivers_arrays(first_frame_geojson)
    if base_x.size < 3:
        raise ValueError("Need at least 3 receiver points for 3D flyover.")

    sample_size = min(9000, base_x.size)
    if sample_size < base_x.size:
        sample_idx = np.linspace(0, base_x.size - 1, sample_size).astype(int)
    else:
        sample_idx = np.arange(base_x.size)

    base_x = base_x[sample_idx]
    base_y = base_y[sample_idx]
    base_levels = base_levels[sample_idx]

    frame_levels: List[np.ndarray] = []
    for frame_path in existing_paths:
        frame_geojson = _load_geojson(frame_path)
        frame_x, frame_y, levels = _extract_receivers_arrays(frame_geojson)
        if frame_x.size < sample_idx.max() + 1:
            continue
        if frame_x.size != frame_y.size or frame_x.size != levels.size:
            continue
        frame_levels.append(levels[sample_idx])

    if not frame_levels:
        frame_levels = [base_levels]

    level_matrix = np.vstack(frame_levels)
    level_breaks = _compute_level_breaks(level_matrix.reshape(-1), len(LEVEL_COLORS))
    colorscale = _build_plotly_discrete_colorscale(level_breaks)
    level_lo = float(level_breaks[0])
    level_hi = float(level_breaks[-1])

    center_x = float(np.mean([float(np.min(base_x)), float(np.max(base_x)), float(np.min(route_x)), float(np.max(route_x))]))
    center_y = float(np.mean([float(np.min(base_y)), float(np.max(base_y)), float(np.min(route_y)), float(np.max(route_y))]))

    terrain_min_z = 0.0
    terrain_trace = None
    if dem_path.exists():
        dem_geojson = _load_geojson(dem_path)
        dem_grid = _extract_dem_grid(dem_geojson)
        if dem_grid is not None:
            dem_x, dem_y, dem_z = dem_grid
            terrain_min_z = float(np.min(dem_z))
            terrain_trace = go.Surface(
                x=dem_x - center_x,
                y=dem_y - center_y,
                z=dem_z,
                colorscale=[[0.0, "#445b4a"], [0.5, "#5f7f62"], [1.0, "#8ca879"]],
                showscale=False,
                opacity=0.93,
                name="Terrain",
                hoverinfo="skip",
            )

    noise_scale = 2.0
    noise_base_z = terrain_min_z + 8.0
    noise_z0 = noise_base_z + (level_matrix[0] - level_lo) * noise_scale

    route_x_local = route_x - center_x
    route_y_local = route_y - center_y
    route_z = np.full(route_x_local.shape, noise_base_z + 2.0)

    data_traces = []
    if terrain_trace is not None:
        data_traces.append(terrain_trace)

    if buildings_path.exists():
        buildings_geojson = _load_geojson(buildings_path)
        bx, by, bz = _build_buildings_wireframe(
            buildings_geojson=buildings_geojson,
            center_x=center_x,
            center_y=center_y,
            z_base=terrain_min_z + 1.0,
        )
        data_traces.append(
            go.Scatter3d(
                x=bx,
                y=by,
                z=bz,
                mode="lines",
                line={"color": "#d3d6db", "width": 2},
                opacity=0.65,
                name="Buildings",
                hoverinfo="skip",
            )
        )

    data_traces.append(
        go.Scatter3d(
            x=route_x_local,
            y=route_y_local,
            z=route_z,
            mode="lines",
            line={"color": "#ffffff", "width": 6},
            name="Route",
            hoverinfo="skip",
        )
    )

    noise_trace_index = len(data_traces)
    data_traces.append(
        go.Scatter3d(
            x=base_x - center_x,
            y=base_y - center_y,
            z=noise_z0,
            mode="markers",
            marker={
                "size": 2.3,
                "opacity": 0.88,
                "color": level_matrix[0],
                "colorscale": colorscale,
                "cmin": level_lo,
                "cmax": level_hi,
                "colorbar": {"title": "Noise (dB)"},
            },
            name="Noise cloud",
            hovertemplate="Noise: %{marker.color:.1f} dB<extra></extra>",
        )
    )

    source_trace_index = len(data_traces)
    source_start_z = source_geojson_3857.get("features", [{}])[0].get("geometry", {}).get("coordinates", [0, 0, noise_base_z + 35.0])
    src_z = float(source_start_z[2]) if len(source_start_z) >= 3 else (noise_base_z + 35.0)
    data_traces.append(
        go.Scatter3d(
            x=[route_x_local[0]],
            y=[route_y_local[0]],
            z=[src_z],
            mode="markers",
            marker={"size": 8, "color": "#ff2a2a", "line": {"color": "#ffffff", "width": 1}},
            name="Source",
            hovertemplate="Moving source<extra></extra>",
        )
    )

    frame_count = min(route_x_local.size, level_matrix.shape[0])
    max_span = max(
        float(np.max(route_x_local) - np.min(route_x_local)),
        float(np.max(route_y_local) - np.min(route_y_local)),
        300.0,
    )
    eye_r = max_span * 1.35 / 300.0
    z_eye = max(0.9, eye_r * 0.8)

    frames = []
    for i in range(frame_count):
        angle = 2.0 * np.pi * (i / max(1, frame_count))
        cam = {
            "eye": {"x": eye_r * np.cos(angle), "y": eye_r * np.sin(angle), "z": z_eye},
            "center": {"x": 0.0, "y": 0.0, "z": -0.15},
            "up": {"x": 0.0, "y": 0.0, "z": 1.0},
        }

        noise_zi = noise_base_z + (level_matrix[i] - level_lo) * noise_scale
        frame_data = [
            go.Scatter3d(
                x=base_x - center_x,
                y=base_y - center_y,
                z=noise_zi,
                mode="markers",
                marker={
                    "size": 2.3,
                    "opacity": 0.88,
                    "color": level_matrix[i],
                    "colorscale": colorscale,
                    "cmin": level_lo,
                    "cmax": level_hi,
                },
                hovertemplate="Noise: %{marker.color:.1f} dB<extra></extra>",
            ),
            go.Scatter3d(
                x=[route_x_local[i]],
                y=[route_y_local[i]],
                z=[src_z],
                mode="markers",
                marker={"size": 8, "color": "#ff2a2a", "line": {"color": "#ffffff", "width": 1}},
                hovertemplate="Moving source<extra></extra>",
            ),
        ]
        frames.append(
            go.Frame(
                data=frame_data,
                traces=[noise_trace_index, source_trace_index],
                name=str(i),
                layout={"scene": {"camera": cam}, "title": f"3D Noise Flyover ({i + 1}/{frame_count})"},
            )
        )

    fig = go.Figure(data=data_traces, frames=frames)
    fig.update_layout(
        title=f"3D Noise Flyover (1/{frame_count})",
        paper_bgcolor="#0e1013",
        plot_bgcolor="#0e1013",
        scene={
            "xaxis": {"title": "X (local m)", "showbackground": False, "color": "#d8dde5"},
            "yaxis": {"title": "Y (local m)", "showbackground": False, "color": "#d8dde5"},
            "zaxis": {"title": "Elevation / Noise", "showbackground": False, "color": "#d8dde5"},
            "aspectmode": "data",
            "camera": {"eye": {"x": eye_r, "y": -eye_r, "z": z_eye}},
        },
        font={"color": "#e6e9ef"},
        margin={"l": 0, "r": 0, "t": 50, "b": 0},
        updatemenus=[
            {
                "type": "buttons",
                "showactive": False,
                "x": 0.02,
                "y": 0.98,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [None, {"frame": {"duration": int(1000 / max(1, fps)), "redraw": True}, "fromcurrent": True}],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                    },
                ],
            }
        ],
        sliders=[
            {
                "active": 0,
                "x": 0.16,
                "y": 0.02,
                "len": 0.8,
                "steps": [
                    {
                        "label": str(i + 1),
                        "method": "animate",
                        "args": [[str(i)], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}}],
                    }
                    for i in range(frame_count)
                ],
            }
        ],
    )

    output_path = output_folder / "digital_twin_flyover.html"
    fig.write_html(str(output_path), include_plotlyjs="cdn")
    return output_path
