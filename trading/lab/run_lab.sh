#!/usr/bin/env bash
# The trading lab: backtest strategies on real prices, the same way, on GitHub's servers.
# Run by .github/workflows/trading-lab.yml. Third-party strategies are downloaded at fixed commits.
set -euo pipefail
cd "$(dirname "$0")"
IMAGE=freqtradeorg/freqtrade:2026.9
NFI_COMMIT=c2e427d354131833ddacd1203b06166a959d30ad    # iterativv/NostalgiaForInfinity
FTS_COMMIT=f3340ce11f5bdf62f598522e64d1f5638eaa13f5    # freqtrade/freqtrade-strategies
STRATEGIES=${STRATEGIES:-"TrendPullback NostalgiaForInfinityX8 CombinedBinHAndCluc ClucMay72018 BbandRsi Supertrend MultiMa Heracles Bandtastic Strategy005 Diamond PowerTower TrendRiderStrategy"}
DAYS=${DAYS:-730}

rm -rf work results.json config.json && mkdir -p work/user_data/strategies
cp ../user_data/strategies/*.py work/user_data/strategies/
raw=https://raw.githubusercontent.com
curl -fsSL "$raw/iterativv/NostalgiaForInfinity/$NFI_COMMIT/NostalgiaForInfinityX8.py" -o work/user_data/strategies/NostalgiaForInfinityX8.py
for s in Strategy005 Supertrend MultiMa Diamond PowerTower TrendRiderStrategy Heracles Bandtastic; do
  curl -fsSL "$raw/freqtrade/freqtrade-strategies/$FTS_COMMIT/user_data/strategies/$s.py" -o "work/user_data/strategies/$s.py"
done
for s in CombinedBinHAndCluc ClucMay72018 BbandRsi; do
  curl -fsSL "$raw/freqtrade/freqtrade-strategies/$FTS_COMMIT/user_data/strategies/berlinguyinca/$s.py" -o "work/user_data/strategies/$s.py"
done

docker pull -q "$IMAGE"
# Freqtrade runs as its own user in the container: let it write to the shared folders. The files
# this script writes (config.json) stay the runner's, and Freqtrade only reads them.
chmod -R a+rwX work .
ft() { docker run --rm -v "$PWD/work/user_data:/freqtrade/user_data" -v "$PWD:/lab" "$IMAGE" "$@"; }
py() { docker run --rm --entrypoint python -v "$PWD/work/user_data:/freqtrade/user_data" -v "$PWD:/lab" "$IMAGE" "$@"; }

# GitHub's servers are in the US; some exchanges refuse US visitors. Use the first that answers.
EXCHANGE=""
for ex in binance okx kucoin gate; do
  python3 make_config.py "$ex" > config.json
  if ft list-pairs --config /lab/config.json --quote USDT -1 > probe.log 2>&1; then EXCHANGE=$ex; break; fi
  echo "$ex didn't answer from here:"; tail -n 5 probe.log
done
[ -n "$EXCHANGE" ] || { echo "No exchange reachable"; exit 1; }
echo "Exchange: $EXCHANGE"

cfg=/lab/config.json
ft download-data --config "$cfg" --timeframes 5m --days $((DAYS + 10))
ft download-data --config "$cfg" --timeframes 15m 1h 4h 1d --days $((DAYS + 250))

split=$(date -u -d "$((DAYS / 2)) days ago" +%Y%m%d)
start=$(date -u -d "$DAYS days ago" +%Y%m%d)
for s in $STRATEGIES; do
  for period in A B; do
    range=$([ "$period" = A ] && echo "$start-$split" || echo "$split-")
    echo "::group::$s year $period ($range)"
    if ft backtesting --config "$cfg" --strategy "$s" --timerange "$range" --export trades --cache none; then
      py /lab/collect.py "$s" "$period" || true
    else
      echo "$s failed in year $period"
    fi
    echo "::endgroup::"
  done
done
python3 report.py results.json > report.md
cat report.md
[ -n "${GITHUB_STEP_SUMMARY:-}" ] && { echo "## Trading lab ($EXCHANGE, last $DAYS days)"; cat report.md; } >> "$GITHUB_STEP_SUMMARY"
