# The Grounding Ladder — LookML realization of the d1 ("NorthStar Commerce") certified model.
#
# This project is a SECOND, INDEPENDENT implementation of the same semantic model the
# benchmark's deterministic compiler (condition S) enforces. Where the compiler aggregates
# each measure at its declared base grain and FULL OUTER JOINs on shared dimensions, LookML
# achieves the identical fan-out safety through declared primary keys + symmetric aggregates.
# validate/validate_lookml.py runs every certified measure through this model on Looker and
# checks it reproduces results/certified_measures_d1.json to the cent.

constant: SCHEMA {
  value: "sgl_grounding_ladder_d1"
  export: override_optional
}
