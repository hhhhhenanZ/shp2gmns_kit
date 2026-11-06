"""Conical replay layer: region configuration, the conic overlay, and the analysis.

Everything new lives here. ``dtalite4cube`` beside it is the original converter and
assignment runner, copied unchanged.

Modules
-------
``region``            reads region.yaml; every path and field name comes from here
``parameters``        derives vdf_alpha per facility x area type, and E per period
``conic_vdf``         rewrites the VDF columns of a converted link.csv
``config``            constants for the analysis, built from the region and parameters
``vdf_math``          pure VDF, capacity and speed functions
``loaders``           reads and joins the Cube side and the TAPlite side
``item4_vdf``         conical replay checks
``item5_vmt_vht``     VMT / VHT / PMT / PHT and network speed
``item6_diagnostics`` convergence, runtime, corridors
``figures``           charts
"""
