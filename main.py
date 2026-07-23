import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from custom_types import ReceiversLayout
from typing import List

import consts
from commands import (
    BuildingsReceivers,
    ClearDb,
    CreateIsosurface,
    DelaunayReceivers,
    ExportTable,
    ImportAscFile,
    ImportFile,
    ImportOsm,
    NoiseLevelFromSource,
    RandomReceivers,
)
from gis_utils import add_agl_height_from_asc, points_to_bounding_square_geojson, source_geojson_to_points
from map_export import export_folium_map
from video_export import export_digital_twin_flyover, export_route_noise_animation
from acoustic_profiles import apply_medium_agricultural_profile
from kml_utils import load_kml_routes


def _single_source_feature_collection(source_points_geojson: dict, index: int) -> dict:
    return {
        "type": "FeatureCollection",
        "name": source_points_geojson.get("name", "Source"),
        "crs": source_points_geojson.get(
            "crs",
            {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3857"}},
        ),
        "features": [source_points_geojson["features"][index]],
    }


def run_with_stuck_protection(command: List[str], env: dict):
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    time.sleep(5)

    try:
        while True:
            with open("application.log", "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
                last_line = lines[-1].strip() if lines else ""

            print(f"Checking last log line: {last_line}")

            if last_line.endswith("done"):
                print("Process completed successfully.")
                break
            if process.poll() is not None:
                raise subprocess.CalledProcessError(process.returncode, command)

            time.sleep(2)

    finally:
        if process.poll() is None:
            print("Terminating process...")
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()


def run_command(command, env: dict) -> None:
    command_list = command.get_command()
    print(f"Running command: {command_list}")

    if command.may_stuck:
        print("Running command with stuck protection (timeout)...")
        run_with_stuck_protection(command_list, env)
        print("Finished command with stuck protection")
    else:
        subprocess.run(command_list, env=env, check=True, text=True)


def run_noise_modelling(
        source_height: float,
        order_of_reflections: int,
        vertical_diffraction: bool,
        horizontal_diffraction: bool,
        receivers_layout: ReceiversLayout,
        max_reflection_distance: int,
        route_step_meters: float,
        export_route_video: bool,
        video_fps: int,
        input_folder: Path,
        output_folder: Path,
        route_kml: Path = None,
):
    env = os.environ.copy()
    # env['JAVA_HOME'] = consts.JAVA_HOME

    if route_kml is not None:
        source_geojson = load_kml_routes(route_kml)
    else:
        with open(input_folder / 'source.geojson', 'r', encoding='utf-8') as f:
            source_geojson = json.loads(f.read())

    source_points_geojson = source_geojson_to_points(
        source_geojson=source_geojson,
        source_height=source_height,
        route_step_meters=route_step_meters,
    )
    if route_kml is not None:
        source_points_geojson = add_agl_height_from_asc(
            source_points_geojson,
            input_folder / "dtm.asc",
            source_height,
        )
        source_points_geojson = apply_medium_agricultural_profile(
            source_points_geojson,
            normalize_route=True,
        )
    modelling_area = points_to_bounding_square_geojson(source_points_geojson, size_meters=2000.0)

    prepared_source_path = output_folder / "source_prepared.geojson"
    prepared_model_area_path = output_folder / "model_area_prepared.geojson"
    with open(prepared_source_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(source_points_geojson))

    with open(prepared_model_area_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(modelling_area))

    db_setup_commands = [
        ClearDb(),
        ImportOsm(input_folder / 'osm_data.osm', 3857),
        ImportFile(prepared_source_path, 3857, 'Source'),
        ImportFile(prepared_model_area_path, 3857, 'Model_Area'),
        ImportAscFile(input_folder / 'dtm.asc', 3857),
    ]

    if receivers_layout == ReceiversLayout.BUILDINGS:
        receivers_layout_command = [BuildingsReceivers('Buildings', 'Source', 10.0, 4.0, 'Model_Area')]
    
    elif receivers_layout == ReceiversLayout.RANDOM:
        receivers_layout_command = [RandomReceivers('Buildings', 'Source', 500, 4.0, 'Model_Area')]

    elif receivers_layout == ReceiversLayout.DELAUNAY:
        receivers_layout_command = [DelaunayReceivers('Buildings', 'Source', 2500.0, 4.0)]
    else:
        raise ValueError("Invalid receivers layout")
    
    noise_level_commands = [
        NoiseLevelFromSource(
            building_table_name='Buildings',
            ground_table_name='Ground',
            source_table_name='Source',
            table_receivers='Receivers',
            vertical_diffraction=vertical_diffraction,
            horizontal_diffraction=horizontal_diffraction,
            order_of_reflections=order_of_reflections,
            max_reflection_distance=max_reflection_distance
        )
    ]

    export_commands = [
        ExportTable(output_folder / 'ground.geojson', 'Ground'),
        ExportTable(output_folder / 'buildings.geojson', 'Buildings'),
        ExportTable(output_folder / 'source.geojson', 'Source'),
        ExportTable(output_folder / 'model_area.geojson', 'Model_Area'),
        ExportTable(output_folder / 'receivers.geojson', 'Receivers'),
        ExportTable(output_folder / 'receivers_level.geojson', 'Receivers_level'),
        ExportTable(output_folder / 'rays.geojson', 'Rays'),
        ExportTable(output_folder / 'dem.geojson', 'DEM'),
    ]

    if receivers_layout == ReceiversLayout.DELAUNAY:
        iso_surface_commands = [
            CreateIsosurface('Receivers_level', 0.4, '0, 2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60'),
            ExportTable(output_folder / 'noise_map.geojson', 'CONTOURING_NOISE_MAP'),
        ]
    else:
        iso_surface_commands = []

    commands = db_setup_commands + receivers_layout_command + noise_level_commands + export_commands + iso_surface_commands

    for command in commands:
        run_command(command, env)

    try:
        html_map_path = export_folium_map(output_folder)
        if html_map_path is not None:
            print(f"Saved interactive map to: {html_map_path}")
        else:
            print("Skipped Folium export: no noise_map.geojson or receivers_level.geojson found.")
    except Exception as exc:
        print(f"Failed to export Folium map: {exc}")

    if export_route_video:
        try:
            route_frame_paths = []
            source_features_count = len(source_points_geojson.get("features", []))
            if source_features_count > 1:
                frames_dir = output_folder / "route_frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                temp_source_path = frames_dir / "_source_frame.geojson"

                for idx in range(source_features_count):
                    frame_geojson = _single_source_feature_collection(source_points_geojson, idx)
                    if route_kml is not None:
                        # The aggregate flight map divides source energy across
                        # all equal-time samples. An animation frame represents
                        # the complete drone at one position, so restore the
                        # full source spectrum for that frame.
                        frame_geojson = apply_medium_agricultural_profile(
                            frame_geojson,
                            normalize_route=False,
                        )
                    with open(temp_source_path, "w", encoding="utf-8") as f:
                        f.write(json.dumps(frame_geojson))

                    frame_output_path = frames_dir / f"receivers_level_frame_{idx:04d}.geojson"
                    frame_source_table_name = f"Source_Frame_{idx:04d}"
                    frame_commands = [
                        ImportFile(temp_source_path, 3857, frame_source_table_name),
                        NoiseLevelFromSource(
                            building_table_name='Buildings',
                            ground_table_name='Ground',
                            source_table_name=frame_source_table_name,
                            table_receivers='Receivers',
                            vertical_diffraction=vertical_diffraction,
                            horizontal_diffraction=horizontal_diffraction,
                            order_of_reflections=order_of_reflections,
                            max_reflection_distance=max_reflection_distance
                        ),
                        ExportTable(frame_output_path, "Receivers_level"),
                    ]
                    for frame_command in frame_commands:
                        run_command(frame_command, env)
                    route_frame_paths.append(frame_output_path)

            try:
                video_path = export_route_noise_animation(
                    output_folder=output_folder,
                    source_geojson_3857=source_points_geojson,
                    fps=video_fps,
                    receivers_level_frame_paths=route_frame_paths,
                )
                print(f"Saved route-point noise animation to: {video_path}")
            except Exception as exc:
                print(f"Failed to export route-point GIF: {exc}")

            try:
                flyover_path = export_digital_twin_flyover(
                    output_folder=output_folder,
                    source_geojson_3857=source_points_geojson,
                    receivers_level_frame_paths=route_frame_paths,
                    fps=video_fps,
                )
                print(f"Saved 3D digital twin flyover to: {flyover_path}")
            except Exception as exc:
                print(f"Failed to export 3D digital twin flyover: {exc}")
        except Exception as exc:
            print(f"Failed to export route-point video: {exc}")

def main():
    parser = argparse.ArgumentParser(description='Run noise modelling with configurable parameters')
    
    parser.add_argument(
        '--source-height',
        type=float,
        required=True,
        help='Source height in meters; for KML routes this is height above ground level (AGL)',
    )
    parser.add_argument('--order-of-reflections', type=int, required=True, help='Order of reflections')
    parser.add_argument('--vertical-diffraction', action='store_true', help='Enable vertical diffraction')
    parser.add_argument('--horizontal-diffraction', action='store_true', help='Enable horizontal diffraction')
    parser.add_argument('--receivers-layout', type=ReceiversLayout, required=True, 
                       choices=list(ReceiversLayout), help='Receivers layout type')
    parser.add_argument('--input-folder', type=Path, required=True, help='Input folder path containing source data')
    parser.add_argument(
        '--route-kml',
        type=Path,
        help='KML flight route. When supplied, replaces input-folder/source.geojson and uses the built-in medium agricultural drone profile.',
    )
    parser.add_argument('--max-reflection-distance', type=int, default=200, help='Maximum reflection distance in meters')
    parser.add_argument('--route-step-meters', type=float, default=25.0, help='Sampling step (meters) for route sources')
    parser.add_argument('--export-route-video', action='store_true', help='Create per-route-point noise animation')
    parser.add_argument('--video-fps', type=int, default=2, help='Frames per second for route animation')

    args = parser.parse_args()

    print(f"Running noise modelling with parameters: {args}")
    if args.route_kml is not None and not args.route_kml.is_file():
        parser.error(f"KML route does not exist: {args.route_kml}")

    run_name = args.route_kml.stem if args.route_kml is not None else args.input_folder.absolute().name
    output_folder_name = f"{run_name}_height_{int(args.source_height)}_reflections_{args.order_of_reflections}_verticalDiff_{args.vertical_diffraction}_horizontalDiff_{args.horizontal_diffraction}_receiversLayout_{args.receivers_layout.value}"
    output_dir = Path(rf'./output/{output_folder_name}')
    output_dir.mkdir(parents=True, exist_ok=True)

    run_noise_modelling(
        source_height=args.source_height,
        order_of_reflections=args.order_of_reflections,
        vertical_diffraction=args.vertical_diffraction,
        horizontal_diffraction=args.horizontal_diffraction,
        receivers_layout=args.receivers_layout,
        max_reflection_distance=args.max_reflection_distance,
        route_step_meters=args.route_step_meters,
        export_route_video=args.export_route_video,
        video_fps=max(1, args.video_fps),
        input_folder=args.input_folder,
        output_folder=output_dir,
        route_kml=args.route_kml,
    )

if __name__ == "__main__":
    main()
