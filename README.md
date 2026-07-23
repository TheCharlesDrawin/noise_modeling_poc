
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

## KML flight route and dB(A) map

Use a KML `LineString` or `gx:Track` as the drone route with `--route-kml`.
The KML longitude/latitude route replaces `input-folder/source.geojson`; the
selected input folder still supplies `osm_data.osm` and `dtm.asc`.

Example using the included Zefat terrain and demo route:

```bash
cd noise_modeling_poc
python3 main.py \
  --route-kml examples/zefat_height_map_route.kml \
  --source-height 100 \
  --order-of-reflections 1 \
  --receivers-layout delaunay \
  --input-folder inputs/zefat \
  --route-step-meters 100 \
  --export-route-video \
  --video-fps 2
```

Open the generated:

```text
output/zefat_height_map_route_height_100_reflections_1_verticalDiff_False_horizontalDiff_False_receiversLayout_delaunay/noise_map.html
```

The same output folder also contains the exported GIS layers. With
`--export-route-video`, it additionally produces `route_noise_animation.gif`
and `digital_twin_flyover.html`. Video export runs one additional propagation
calculation per sampled route point, so omit that flag when only the aggregate
HTML/GIS map is needed.

For KML runs, the model applies an omnidirectional proxy spectrum for a medium
agricultural multicopter. It uses octave-band sound-power levels (dB re 1 pW)
of `100, 104, 108, 106, 103, 99, 95, 90` at
`63, 125, 250, 500, 1000, 2000, 4000, 8000 Hz`, respectively. The energetic
A-weighted source sum is approximately 108 dB(A). This is an engineering
default, **not** a measured or certified DJI Agras signature.

For KML runs, `--source-height` is interpreted as height above ground level
(AGL). The program samples `input-folder/dtm.asc` at every route point and
sets the acoustic Z coordinate to terrain elevation plus the requested
height. A route point outside the terrain raster or on a NODATA cell stops
the run with an error instead of silently placing the drone underground.

All sampled route positions are equal-time weighted. Their source powers are
normalized before propagation, so the resulting receiver `LAEQ` represents
the flight-average level for constant speed rather than all route positions
operating simultaneously. KML altitude values are retained by the parser but
currently overridden by the explicit AGL value.

## Route video export
- Optional CLI flags:
  - `--export-route-video` to generate per-route-point noise animation
  - `--video-fps <int>` to control animation speed (default `2`)
- Output files:
  - `output/<run_name>/route_noise_animation.gif`
- Performance note:
  - Video export uses the run's existing noise layer (`noise_map.geojson` or `receivers_level.geojson`) and animates the moving route point, so runtime stays close to the original fast run.
