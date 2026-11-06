"""SCAG TransCAD loaded network and trip tables -> TAPlite GMNS inputs.

Selected by ``region: {model: transcad_scag}`` in ``region.yaml``. The Cube/NVTA code in
``dtalite4cube`` and ``conic_replay`` is not used for conversion and is not modified.

Modules
-------
config      region.yaml for the SCAG TransCAD model
dictionary  SCAG data dictionaries (shapefile <-> DBD field names) and .DCC headers
fields      per-record and per-direction shapefile values, addressed by DBD name
topology    nodes and directed links from the line layer
zones       Tier-1 zone centroids
vdf         Table 16-2 piecewise BPR, on-ramp meter, connectors, period capacity factor
access      allowed_use rules and their check against SCAG's loaded class flows
network     link.csv and node.csv
demand      TransCAD CSV matrices -> one demand CSV per mode
runfiles    settings.csv and mode_type.csv
provenance  FIELD_PROVENANCE.csv and CONVERSION_REPORT.md
pipeline    the conversion stages, driven by code/main_convert.py
checks      input checks, driven by code/check_inputs.py
"""
