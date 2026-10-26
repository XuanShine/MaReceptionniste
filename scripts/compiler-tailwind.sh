#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
binaire="scripts/tailwindcss"
if [ ! -x "$binaire" ]; then
  curl -fsSL -o "$binaire" https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64
  chmod +x "$binaire"
fi
"$binaire" --input src/ma_receptionniste2/static/tailwind.css --output src/ma_receptionniste2/static/app.css --minify
