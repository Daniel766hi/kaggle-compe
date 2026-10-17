"""Registry of datasets this repo publishes. Add a new dataset by adding its SPEC here."""

from . import defi, idn_air_quality, idn_politics, idn_weather, idr_fx, movies

DATASETS = {spec.name: spec for spec in (defi.SPEC, idn_air_quality.SPEC, idn_politics.SPEC, idn_weather.SPEC, idr_fx.SPEC, movies.SPEC)}
