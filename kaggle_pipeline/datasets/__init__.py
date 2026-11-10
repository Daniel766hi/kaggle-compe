"""Registry of datasets this repo publishes. Add a new dataset by adding its SPEC here."""

from . import art_museums, commodities, defi, idn_air_quality, idn_fires, idn_politics, idn_quakes, idn_weather, idn_wiki, idr_fx, movies, supply_chain

DATASETS = {spec.name: spec for spec in (art_museums.SPEC, commodities.SPEC, defi.SPEC, idn_air_quality.SPEC, idn_fires.SPEC, idn_politics.SPEC, idn_quakes.SPEC, idn_weather.SPEC, idn_wiki.SPEC, idr_fx.SPEC, movies.SPEC, supply_chain.SPEC)}
