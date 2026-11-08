# %% [markdown]
# # Should this hotel overbook? A leak-free cancellation model and a booking-replay simulation
#
# Most notebooks on this dataset predict cancellations, often with near-perfect scores. A hotel does not
# need a score; it needs a **decision**: with 4 in 10 bookings cancelling, should it accept more bookings
# than it has rooms? Accept too few and rooms stay empty; accept too many and guests are *walked* (sent to
# another hotel at the hotel's cost).
#
# This notebook:
# 1. finds the **leaks** that make cancellation models look perfect, and builds an honest model with
#    only what is known when a booking is made;
# 2. **replays the City Hotel's real 2017 booking stream**, request by request with the real cancellation
#    dates, under different overbooking policies;
# 3. updates each booking's cancellation probability as it **survives** closer to arrival, and works out
#    the **break-even walk cost**: how cheap walking a guest must be for overbooking to pay.
#
# The answer is more interesting than "overbook X%": a small buffer pays, anything more barely does, and
# the timing of cancellations explains why.

# %%
import glob
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb", "#c3c2b7"
C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
    "font.size": 10.5, "lines.linewidth": 2, "figure.figsize": (11, 4.6), "figure.dpi": 110,
    "legend.frameon": False, "axes.xmargin": 0.01,
})


def find(name):
    for root in ("/kaggle/input", os.environ.get("DATA_ROOT", "../input")):
        hits = glob.glob(f"{root}/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError(name)


h = pd.read_csv(find("hotel_bookings.csv"))
months = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}
h["arrival"] = pd.to_datetime(dict(year=h["arrival_date_year"], month=h["arrival_date_month"].map(months),
                                   day=h["arrival_date_day_of_month"]))
h["booked_on"] = h["arrival"] - pd.to_timedelta(h["lead_time"], unit="D")
h["status_date"] = pd.to_datetime(h["reservation_status_date"])
h["nights"] = h["stays_in_weekend_nights"] + h["stays_in_week_nights"]
h = h[h["nights"] > 0].reset_index(drop=True)
print(f"{len(h):,} bookings, arrivals {h['arrival'].min():%b %Y} to {h['arrival'].max():%b %Y}")
h.groupby("hotel")["is_canceled"].agg(["mean", "size"]).rename(columns={"mean": "cancelled share", "size": "bookings"}).round(3)

# %% [markdown]
# ## 1. Why cancellation models look perfect
#
# Several columns are only filled in, or only change, **after** the guest cancels or arrives:
#
# | Column | Leak |
# |---|---|
# | `reservation_status`, `reservation_status_date` | the outcome itself, and when it happened |
# | `assigned_room_type` | assigned at check-in; differs from the reserved type mostly for guests who came |
# | `country` | confirmed at check-in; for bookings that are cancelled it often stays at the default, Portugal |
# | `booking_changes`, `total_of_special_requests`, `required_car_parking_spaces` | updated over the stay window |
#
# The country leak is easy to see:

# %%
print("Share of bookings with country = PRT:",
      h.groupby("is_canceled").apply(lambda g: (g["country"] == "PRT").mean(), include_groups=False)
       .rename({0: "kept", 1: "cancelled"}).round(3).to_dict())
print("Cancelled share by deposit type:", h.groupby("deposit_type")["is_canceled"].mean().round(3).to_dict())

# %% [markdown]
# (Non-refundable bookings cancelling 99% of the time is a known oddity of this dataset, documented by
# its authors: many are group or agency allocations released before arrival. We keep it as it is; it is
# known at booking time.)
#
# We train on arrivals before 2017 and test on 2017 arrivals, with and without the leaky columns.

# %%
honest = ["hotel", "lead_time", "arrival_date_week_number", "stays_in_weekend_nights", "stays_in_week_nights",
          "adults", "children", "babies", "meal", "market_segment", "distribution_channel", "is_repeated_guest",
          "previous_cancellations", "previous_bookings_not_canceled", "reserved_room_type", "deposit_type",
          "agent", "company", "days_in_waiting_list", "customer_type", "adr"]
leaky = honest + ["country", "assigned_room_type", "booking_changes", "total_of_special_requests",
                  "required_car_parking_spaces"]


def frame(cols):
    X = h[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ("string", "str") or c in ("agent", "company"):
            values = X[c].astype(str)
            top = values.value_counts().index[:150]  # the model takes at most 255 categories per column
            X[c] = values.where(values.isin(top), "other").astype("category")
    X["children"] = pd.to_numeric(X.get("children", 0), errors="coerce")
    return X


train, test = h["arrival"] < "2017-01-01", h["arrival"] >= "2017-01-01"
models, scores = {}, []
for name, cols in (("with leaky columns", leaky), ("honest (booking-time only)", honest)):
    X = frame(cols)
    m = HistGradientBoostingClassifier(categorical_features="from_dtype", max_iter=400, learning_rate=0.05,
                                       random_state=0).fit(X[train], h.loc[train, "is_canceled"])
    p = m.predict_proba(X[test])[:, 1]
    models[name] = (m, X)
    scores.append({"model": name, "test ROC AUC (2017 arrivals)": round(roc_auc_score(h.loc[test, "is_canceled"], p), 4)})
pd.DataFrame(scores)

# %% [markdown]
# The honest model is weaker, but it is the only one a hotel can actually use when a booking request
# arrives. Its probabilities drive the policy below.

# %%
m, X = models["honest (booking-time only)"]
h["p_cancel"] = m.predict_proba(X)[:, 1]
cal = pd.DataFrame({"p": h.loc[test, "p_cancel"], "y": h.loc[test, "is_canceled"]})
cal["bin"] = pd.cut(cal["p"], [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], include_lowest=True)
cal.groupby("bin", observed=True).agg(bookings=("y", "size"), predicted=("p", "mean"), actual=("y", "mean")).round(3)

# %% [markdown]
# ## 2. When do cancellations happen?
#
# A cancelled room only stays empty if it is cancelled too late to be sold again. The timing of
# cancellations (training years, City Hotel):

# %%
cityh = h[h["hotel"] == "City Hotel"]
tr_c = cityh[(cityh["arrival"] < "2017-01-01") & (cityh["is_canceled"] == 1)]
cancel_lead = (tr_c["arrival"] - tr_c["status_date"]).dt.days.clip(lower=0)
F = np.array([(cancel_lead <= d).mean() for d in range(1000)])  # share of cancellations made <= d days before arrival
fig, ax = plt.subplots()
ax.plot(np.arange(366), 100 * F[:366], color=C[0])
for d in (7, 30, 90):
    ax.annotate(f"{100 * F[d]:.0f}% within {d} days", (d, 100 * F[d]), xytext=(15, -15), textcoords="offset points",
                fontsize=9.5, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
ax.set_xlabel("days before arrival")
ax.set_ylabel("% of cancellations made by then (cumulative)")
ax.set_title("Most cancellations come weeks or months ahead, while the room can still be resold")
plt.show()

# %% [markdown]
# Only about a sixth of cancellations happen in the last week. That matters for the policy: a booking
# that is still held a few days before arrival is much less likely to cancel than its initial
# probability says. Bayes' rule updates it: if `p` is the initial probability and `F(d)` the share of
# cancellations made within the last `d` days, a booking still held `d` days ahead cancels with probability
# `p F(d) / (1 - p + p F(d))`.
#
# ## 3. Replaying 2017
#
# We take every 2017 City Hotel booking request in the order it was made, accept or reject it under a
# policy, and release rooms on the real cancellation dates. On each night, guests beyond capacity are
# **walked**. Revenue is the ADR of every room-night actually stayed.
#
# **Policies**
# - *No overbooking*: hold at most C bookings per night.
# - *Fixed overbooking*: hold at most C x (1 + b).
# - *Model-driven*: accept while the **expected** guests per night, using the survival-updated
#   probabilities of all held bookings, stay at most C x k.

# %%
city = h[h["hotel"] == "City Hotel"]
occupied = (city[city["is_canceled"] == 0]
            .assign(night=lambda d: [pd.date_range(a, periods=n) for a, n in zip(d["arrival"], d["nights"])])
            .explode("night").groupby("night").size())
REAL_CAPACITY = int(occupied.max())
start, end = pd.Timestamp("2017-01-01"), pd.Timestamp("2017-08-31")
nights = pd.date_range(start, end)
book = city[(city["arrival"] >= start) & (city["arrival"] <= end)].copy()
book["first"] = (book["arrival"] - start).dt.days
book["last"] = (book["first"] + book["nights"]).clip(upper=len(nights))
book["cancel_time"] = np.where(book["is_canceled"] == 1, book["status_date"], pd.NaT)
avg_adr = book.loc[book["is_canceled"] == 0, "adr"].mean()
events = [(t, 0, i) for i, t in zip(book.index, book["booked_on"])]
events += [(t, 1, i) for i, t in zip(book.index, book["cancel_time"]) if pd.notna(t)]
events.sort(key=lambda e: (e[0], e[1]))
first, last, p0 = book["first"].to_dict(), book["last"].to_dict(), book["p_cancel"].to_dict()
cancelled, adr = book["is_canceled"].to_dict(), book["adr"].to_dict()


def p_now(p, days_ahead):
    if p >= 1:
        return 1.0
    f = F[min(max(days_ahead, 0), len(F) - 1)]
    return p * f / (1 - p + p * f)


def replay(capacity, limit=None, expected_limit=None):
    held = [dict() for _ in nights]
    accepted = set()
    for t, kind, i in events:
        a, b = first[i], last[i]
        if a >= b:
            continue
        if kind == 1:
            if i in accepted:
                for n in range(a, b):
                    held[n].pop(i, None)
            continue
        if limit is not None and any(len(held[n]) + 1 > limit for n in range(a, b)):
            continue
        if expected_limit is not None:
            ahead = [(nights[n] - t).days for n in range(a, b)]
            if any(sum(1 - p_now(p, d) for p in held[n].values()) + 1 - p_now(p0[i], d) > expected_limit
                   for n, d in zip(range(a, b), ahead)):
                continue
        for n in range(a, b):
            held[n][i] = p0[i]
        accepted.add(i)
    guests, revenue = np.zeros(len(nights)), np.zeros(len(nights))
    for i in accepted:
        if not cancelled[i]:
            guests[first[i]:last[i]] += 1
            revenue[first[i]:last[i]] += adr[i]
    housed = np.minimum(guests, capacity)
    walked = guests - housed
    revenue = (revenue * np.where(guests > 0, housed / np.maximum(guests, 1), 0)).sum()
    return {"room-nights sold": int(housed.sum()), "occupancy %": 100 * housed.mean() / capacity,
            "walked guest-nights": int(walked.sum()), "room revenue": revenue}


everything = replay(REAL_CAPACITY)
print(f"Real capacity {REAL_CAPACITY} rooms. Accepting every 2017 request: occupancy {everything['occupancy %']:.1f}%, "
      f"{everything['walked guest-nights']} walked guest-nights.")

# %% [markdown]
# At its real size the City Hotel **never needed to turn anyone away** in January-August 2017: even
# accepting every request, guests never exceeded its rooms. Overbooking only matters when demand outruns
# capacity, so we replay the same real booking stream for **tighter hotels** of 160, 180 and 200 rooms: the
# same customers and cancellations, less room.

# %%
rows = []
for cap in (160, 180, 200):
    base = replay(cap, limit=cap)
    rows.append({"rooms": cap, "policy": "no overbooking", **base})
    for b in (0.02, 0.05, 0.10):
        rows.append({"rooms": cap, "policy": f"fixed +{b:.0%}", **replay(cap, limit=cap * (1 + b))})
    for k in (0.90, 0.95, 1.00):
        rows.append({"rooms": cap, "policy": f"model-driven, k={k:.2f}", **replay(cap, expected_limit=cap * k)})
res = pd.DataFrame(rows)
base_sold = res[res["policy"] == "no overbooking"].set_index("rooms")["room-nights sold"]
base_rev = res[res["policy"] == "no overbooking"].set_index("rooms")["room revenue"]
res["extra room-nights"] = res["room-nights sold"] - res["rooms"].map(base_sold)
res["extra revenue"] = res["room revenue"] - res["rooms"].map(base_rev)
# Overbooking pays if a walked guest-night costs less than this many average room-nights.
res["break-even walk cost (x ADR)"] = (res["extra revenue"] / (res["walked guest-nights"] * avg_adr)).where(
    res["walked guest-nights"] > 0)
res.round({"occupancy %": 1, "room revenue": 0, "extra revenue": 0, "break-even walk cost (x ADR)": 2})

# %% [markdown]
# ## 4. The break-even walk cost
#
# Every policy that overbooks sells some extra room-nights and walks some guests. The ratio says how
# cheap walking must be for the policy to pay. Walking a guest usually costs at least a night at another
# hotel plus transport and goodwill: one to two room-nights or more.

# %%
ob = res[res["policy"] != "no overbooking"]
fig, ax = plt.subplots(figsize=(10, 5))
for (kind, color) in (("fixed", C[3]), ("model-driven", C[0])):
    r = ob[ob["policy"].str.startswith(kind)]
    ax.scatter(r["walked guest-nights"], r["extra room-nights"], color=color, s=60, label=kind)
    for _, row in r.iterrows():
        ax.annotate(f"{row['rooms']}r", (row["walked guest-nights"], row["extra room-nights"]), xytext=(4, 3),
                    textcoords="offset points", fontsize=8, color=color)
lim = max(ob["walked guest-nights"].max(), ob["extra room-nights"].max()) * 1.05
for ratio, style in ((1, "--"), (2, ":")):
    ax.plot([0, lim], [0, lim * ratio], color=INK2, lw=0.8, ls=style)
    ax.text(lim * 0.8 / ratio + lim * 0.01, lim * 0.8, f"above this line: pays if a walk costs < {ratio} night{'s' if ratio > 1 else ''}",
            fontsize=8.5, color=INK2)
ax.set_xlim(0, lim)
ax.set_ylim(0, lim)
ax.set_xlabel("walked guest-nights (Jan-Aug 2017)")
ax.set_ylabel("extra room-nights sold vs no overbooking")
ax.set_title("The first 2% pays; beyond that, about one walked guest per extra room")
ax.legend(loc="lower right")
plt.show()
summary = ob.groupby(ob["policy"].str.split(",").str[0].str.split(" ").str[0])["break-even walk cost (x ADR)"].describe()
summary[["count", "min", "50%", "max"]].round(2)

# %% [markdown]
# ## Takeaways
#
# - **Cancellation scores near 100% come from leaks** (`reservation_status`, `assigned_room_type`,
#   `country`, ...). A model limited to booking-time information is weaker but usable, and reasonably
#   calibrated on the following year.
# - **At its real size, the City Hotel had no need to overbook in 2017**: even accepting every request,
#   guests never exceeded its rooms.
# - **For a hotel that fills up, a small buffer pays and more does not.** Overbooking by 2% sold about
#   three extra room-nights per walked guest-night (break-even walk cost 3 to 4 room-nights). At 5% the
#   break-even falls to about 1.2 room-nights, and at 10% to below one: each extra room sold then costs
#   more than one walked guest.
# - **The reason is timing**: most cancellations arrive weeks ahead, when the room can still be resold;
#   only about a sixth arrive in the final week. Bookings that survive to the last days rarely cancel, so
#   there is little slack to sell twice.
# - **A simple rule beat the model.** The model-driven policy (expected guests within capacity, with
#   survival-updated probabilities) did not beat a fixed 2% buffer except for the 200-room hotel. Its
#   probabilities are good on average but too uncertain per night to fine-tune a limit; a model that
#   predicts the *number of late cancellations per night* directly is the natural next step.
#
# Assumptions: capacity is inferred from peak occupancy (and reduced on purpose in the scenarios), demand
# cannot exceed the bookings the hotel actually received, rejected guests are simply lost, and walk cost is
# counted per walked guest-night.
#
# Data: Antonio, Almeida and Nunes (2019), *Hotel booking demand datasets*, Data in Brief 22 (CC BY 4.0).
