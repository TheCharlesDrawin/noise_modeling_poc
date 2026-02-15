import pyproj
from pyproj import Transformer
import pyproj
from typing import Tuple


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