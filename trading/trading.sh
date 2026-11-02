#!/usr/bin/env bash
# Paper-trading bot (Freqtrade) for macOS/Linux: bash trading.sh setup | backtest | start | stop | status
set -euo pipefail
cd "$(dirname "$0")"
ft=/freqtrade/user_data/config.json
command -v docker >/dev/null || { echo "Install Docker first: https://docs.docker.com/get-docker/"; exit 1; }
password() { sed -n 's/^FREQTRADE__API_SERVER__PASSWORD=//p' .env; }
setup() {
  if [ ! -f .env ]; then
    { echo "FREQTRADE__API_SERVER__JWT_SECRET_KEY=$(openssl rand -hex 32)"
      echo "FREQTRADE__API_SERVER__WS_TOKEN=$(openssl rand -hex 16)"
      echo "FREQTRADE__API_SERVER__PASSWORD=$(openssl rand -hex 8)"; } > .env
    chmod 600 .env
  fi
  docker compose pull
  docker compose run --rm freqtrade download-data --config "$ft" --timeframes 1h --days 500
}
case "${1:-}" in
  setup) setup ;;
  backtest) docker compose run --rm freqtrade backtesting --config "$ft" --strategy TrendPullback \
              --timerange "$(date -d '365 days ago' +%Y%m%d 2>/dev/null || date -v-365d +%Y%m%d)-" --export trades ;;
  start) [ -f .env ] || setup; docker compose up -d
         echo "Dashboard: http://127.0.0.1:8080  user: freqtrader  password: $(password)" ;;
  stop) docker compose down ;;
  status) docker compose ps; docker compose logs --tail 20 ;;
  *) echo "usage: bash trading.sh setup | backtest | start | stop | status" ;;
esac
