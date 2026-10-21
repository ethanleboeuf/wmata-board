#!/usr/bin/env bash
# One-time (or occasional) basemap build: cut the Metrorail area out of the
# Protomaps daily planet build into data/basemap.pmtiles. OpenStreetMap data,
# ODbL -- the page shows "© OpenStreetMap contributors".
#
#   tools/build_basemap.sh            # latest build
#   tools/build_basemap.sh 20261019   # a specific build date
#
# The bbox covers the whole system (Ashburn to Largo, Shady Grove to
# Franconia) so the phone can zoom out; maxzoom 15 is plenty for a wall map.
set -euo pipefail
cd "$(dirname "$0")/.."

PMTILES_VERSION="1.31.2"
BBOX="-77.52,38.74,-76.82,39.14"   # west,south,east,north
MAXZOOM=15

case "$(uname -m)" in
  aarch64|arm64) ARCH=arm64 ;;
  x86_64) ARCH=x86_64 ;;
  *) echo "unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

mkdir -p data/bin
if [ ! -x data/bin/pmtiles ]; then
  curl -fsSL "https://github.com/protomaps/go-pmtiles/releases/download/v${PMTILES_VERSION}/go-pmtiles_${PMTILES_VERSION}_Linux_${ARCH}.tar.gz" \
    | tar -xz -C data/bin pmtiles
fi

if [ $# -ge 1 ]; then
  BUILD="$1"
else
  BUILD="$(curl -fsSL https://build-metadata.protomaps.dev/builds.json \
    | python3 -c 'import json,sys; print(sorted(b["key"] for b in json.load(sys.stdin))[-1].removesuffix(".pmtiles"))')"
fi
echo "extracting from Protomaps build ${BUILD} (bbox ${BBOX}, maxzoom ${MAXZOOM})"
data/bin/pmtiles extract "https://build.protomaps.com/${BUILD}.pmtiles" data/basemap.pmtiles.tmp \
  --bbox="${BBOX}" --maxzoom="${MAXZOOM}"
mv data/basemap.pmtiles.tmp data/basemap.pmtiles
ls -lh data/basemap.pmtiles
