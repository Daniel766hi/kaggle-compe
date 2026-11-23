"""Registry of datasets this repo publishes. Add a new dataset by adding its SPEC here."""

from . import anime, art_museums, commodities, defi, electricity, idn_air_quality, idn_fires, idn_politics, idn_quakes, idn_retail, idn_solar, idn_weather, idn_wiki, idr_fx, macro_asean, minerals, movies, supply_chain

DATASETS = {spec.name: spec for spec in (anime.SPEC, art_museums.SPEC, commodities.SPEC, defi.SPEC, electricity.SPEC, idn_air_quality.SPEC, idn_fires.SPEC, idn_politics.SPEC, idn_quakes.SPEC, idn_retail.SPEC, idn_solar.SPEC, idn_weather.SPEC, idn_wiki.SPEC, idr_fx.SPEC, macro_asean.SPEC, minerals.SPEC, movies.SPEC, supply_chain.SPEC)}
