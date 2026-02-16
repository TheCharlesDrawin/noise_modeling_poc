
## Logical order
# Prepare
- Download to the root folder of the repo from https://noisemodelling.readthedocs.io/en/latest/Get_Started_Script.html: NoiseModelling_without_gui
- Get the OSM data of the chosen area (Buildings and Ground):
    - Use the command below with the relevant bbox borders (south west, north, east):
        - ```wget -O OUTPUT.osm "https://api.openstreetmap.org/api/0.6/map?bbox=GOE_DD_WEST,GEO_DD_SOUTH,GEO_DD_EAST,GEO_DD_NORTH"```
- Download DTM layer of the chosen area:
    - Use the following swagger - https://portal.opentopography.org/apidocs/#/Public/getGlobalDem
    - translate the geotiff into ESRI format:
        - ```gdal_translate -of AAIGrid INPUT_TIFF.tif OUTPUT_ESRI.asc``

# Run
- python3 main.py
- `source.geojson` can now be:
  - `Point` / `MultiPoint`
  - `LineString` / `MultiLineString` (route is sampled into point sources)
- Route sampling density is controlled by:
  - `--route-step-meters` (default `25.0`)

Example route input for Zfat:
- `inputs/zefat_route_linestring/source_drone_route_zfat.geojson`

## Folium HTML export
- Install dependency:
  - `pip install folium`
- After each run, the script now writes an interactive browser map to:
  - `output/<run_name>/noise_map.html`
