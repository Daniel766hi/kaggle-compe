"""Features for the next-day PM2.5 model, built from three Kaggle datasets:

- Indonesia Air Quality (idn_air_quality_daily.csv, cities.csv)
- Indonesia Daily Weather (idn_weather_daily.csv)
- Indonesia Fire Hotspots (hotspots.parquet)

Every feature for day t uses only data available at the end of day t, and the target is the
daily mean PM2.5 of day t+1.
"""

import numpy as np
import pandas as pd

FIRE_RADII_KM = (100, 300)

FEATURES = [
    "pm25", "pm25_lag1", "pm25_lag2", "pm25_mean7", "pm25_max3",
    "fires_100km", "fires_100km_lag1", "fires_300km", "fires_300km_lag1", "fires_300km_sum7",
    "rain_mm", "rain_hours", "rain_mm_sum7", "dry_days", "wind_max", "temp_max", "et0",
    "doy_sin", "doy_cos",
]
# Skewed counts and concentrations enter the model as log(1 + x).
LOG_FEATURES = ["pm25", "pm25_lag1", "pm25_lag2", "pm25_mean7", "pm25_max3", "fires_100km", "fires_100km_lag1",
                "fires_300km", "fires_300km_lag1", "fires_300km_sum7", "rain_mm", "rain_mm_sum7"]


def predict_next_day(model, X):
    """Tomorrow's mean PM2.5 (µg/m³). The model predicts the change from today on a log scale,
    log(1 + tomorrow) - log(1 + today), which lets it follow haze peaks beyond past levels."""
    change = model.predict(X[FEATURES])
    return np.clip(np.expm1(np.log1p(X["pm25"].to_numpy()) + change), 0, None)


def fires_near_cities(hotspots, cities, radii=FIRE_RADII_KM):
    """Daily fire detections within each radius of each city (both VIIRS satellites)."""
    lat = np.radians(hotspots["latitude"].to_numpy())
    lon = np.radians(hotspots["longitude"].to_numpy())
    days = hotspots["acq_date"].to_numpy()
    out = []
    for city in cities.itertuples():
        clat, clon = np.radians(city.latitude), np.radians(city.longitude)
        a = np.sin((lat - clat) / 2) ** 2 + np.cos(clat) * np.cos(lat) * np.sin((lon - clon) / 2) ** 2
        dist = 2 * 6371 * np.arcsin(np.sqrt(a))
        counts = {}
        for r in radii:
            near = pd.Series(days[dist <= r]).value_counts()
            counts[f"fires_{r}km"] = near
        df = pd.DataFrame(counts).fillna(0)
        df.index.name = "date"
        out.append(df.reset_index().assign(city=city.city))
    return pd.concat(out, ignore_index=True)


def build_features(aq, weather, hotspots, cities):
    """One row per city and day with all FEATURES, plus `target` (next day's mean PM2.5)."""
    aq = aq[["city", "date", "pm2_5_mean"]].rename(columns={"pm2_5_mean": "pm25"})
    hot = hotspots[hotspots["acq_date"] >= aq["date"].min() - pd.Timedelta(days=10)]
    fires = fires_near_cities(hot, cities)
    wx = weather[["city", "date", "precipitation_sum", "precipitation_hours", "wind_speed_10m_max",
                  "temperature_2m_max", "et0_fao_evapotranspiration"]].rename(columns={
                      "precipitation_sum": "rain_mm", "precipitation_hours": "rain_hours",
                      "wind_speed_10m_max": "wind_max", "temperature_2m_max": "temp_max",
                      "et0_fao_evapotranspiration": "et0"})

    rows = []
    for city, g in aq.groupby("city"):
        # A complete daily calendar per city, so that lags and rolling windows are in days.
        days = pd.date_range(g["date"].min(), g["date"].max(), freq="D")
        df = pd.DataFrame({"date": days, "city": city})
        df = df.merge(g, on=["city", "date"], how="left")
        df = df.merge(wx[wx["city"] == city], on=["city", "date"], how="left")
        df = df.merge(fires[fires["city"] == city], on=["city", "date"], how="left")
        for r in FIRE_RADII_KM:
            df[f"fires_{r}km"] = df[f"fires_{r}km"].fillna(0)
        df["pm25_lag1"] = df["pm25"].shift(1)
        df["pm25_lag2"] = df["pm25"].shift(2)
        df["pm25_mean7"] = df["pm25"].rolling(7, min_periods=4).mean()
        df["pm25_max3"] = df["pm25"].rolling(3, min_periods=2).max()
        df["fires_100km_lag1"] = df["fires_100km"].shift(1)
        df["fires_300km_lag1"] = df["fires_300km"].shift(1)
        df["fires_300km_sum7"] = df["fires_300km"].rolling(7, min_periods=1).sum()
        df["rain_mm_sum7"] = df["rain_mm"].rolling(7, min_periods=4).sum()
        wet = (df["rain_mm"] >= 1).astype(float).where(df["rain_mm"].notna())
        df["dry_days"] = wet.groupby(wet.cumsum()).cumcount().where(wet.notna())  # days since >= 1 mm rain
        df["target"] = df["pm25"].shift(-1)
        rows.append(df)
    df = pd.concat(rows, ignore_index=True)
    doy = df["date"].dt.dayofyear
    df["doy_sin"], df["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return df
