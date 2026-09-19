# The Grounding Ladder — LookML realization of the d1 ("NorthStar Commerce") certified model.
#
# This project is a SECOND, INDEPENDENT implementation of the same semantic model the
# benchmark's deterministic compiler (condition S) enforces. Where the compiler aggregates
# each measure at its declared base grain and FULL OUTER JOINs on shared dimensions, LookML
# achieves the identical fan-out safety through declared primary keys + symmetric aggregates.
# validate/validate_lookml.py runs every certified measure through this model on Looker and
# checks it reproduces results/certified_measures_d1.json to the cent.
#
# To deploy: set these three constants to your own instance (in the LookML manifest or the
# Looker Admin connection), load the d1 warehouse with validate/load_d1_to_bigquery.py, and
# point @{connection_name} at the BigQuery project holding dataset @{SCHEMA}.

constant: connection_name { value: "your_bigquery_connection"  export: override_optional }
constant: gcp_project     { value: "your-gcp-project"          export: override_optional }
constant: SCHEMA          { value: "sgl_grounding_ladder_d1"   export: override_optional }
