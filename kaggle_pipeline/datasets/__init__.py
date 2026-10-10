"""Registry of datasets this repo publishes. Add a new dataset by adding its SPEC here."""

from . import defi, idn_air_quality, idn_weather, idr_fx

DATASETS = {spec.name: spec for spec in (defi.SPEC, idn_air_quality.SPEC, idn_weather.SPEC, idr_fx.SPEC)}
