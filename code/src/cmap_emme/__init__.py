"""CMAP (Emme) highway network -> GMNS, selected by ``region: {model: emme_cmap}``.

Modules
-------
config      read region.cmap.yaml, resolve paths
emme_read   period shapefiles (links, nodes), Emme extra-attribute and transaction files
crs         EPSG:26771 -> EPSG:4326 (pyproj when installed, built-in fallback otherwise)
vdf         CMAP volume-delay functions, capacity rule, 99,999 placeholder (VDF 6, 7)
access      MODES letters -> allowed_use
network     node.csv and link.csv
checks      gates G1-G12 and the input check used by code/check_inputs.py
report      CONVERSION_REPORT.md, FIELD_PROVENANCE.csv, manifest
pipeline    the stages, driven by code/main_convert.py

Every CMAP number lives in region.cmap.yaml with its source; this package holds none.
Work plan: CMAP_model/CMAP_network_workplan.md.
"""
