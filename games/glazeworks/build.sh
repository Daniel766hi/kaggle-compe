#!/usr/bin/env bash
# Wraps glazeworks.html (page body) into a standalone index.html for self-hosting.
set -euo pipefail
cd "$(dirname "$0")"
{
  echo '<!doctype html>'
  echo '<html lang="en">'
  echo '<head>'
  echo '<meta charset="utf-8">'
  echo '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
  echo '<meta name="description" content="Glazeworks: a block-placing puzzle with pure-glaze lines, turn tokens and a daily seed.">'
  echo '<style>*,*::before,*::after{box-sizing:border-box}body{margin:0;font:14px system-ui,sans-serif}[hidden]{display:none!important}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}</style>'
  echo '</head>'
  echo '<body>'
  cat glazeworks.html
  echo '</body>'
  echo '</html>'
} > index.html
echo "built index.html"
