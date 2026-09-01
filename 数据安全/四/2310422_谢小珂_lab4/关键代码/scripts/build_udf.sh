#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-observation}"

if [[ "$MODE" == "observation" ]]; then
  M=4
  UPPER='(1LL<<8)'
elif [[ "$MODE" == "textbook" ]]; then
  M=128
  UPPER='(1LL<<62)'
else
  echo "Usage: $0 [observation|textbook]"
  exit 1
fi

PLUGIN_DIR="$(mysql_config --plugindir)"
echo "[build] mode=$MODE FHOPE_M=$M FHOPE_INITIAL_UPPER=$UPPER"
echo "[build] plugin_dir=$PLUGIN_DIR"

g++ -std=c++17 -Wall -Wextra -O2 -shared -fPIC \
  -DFHOPE_M="$M" -DFHOPE_INITIAL_UPPER="$UPPER" \
  src/UDF.cpp src/Node.cpp \
  -I"$(mysql_config --include | sed 's/^-I//')" \
  -o libfhope.so

sudo cp libfhope.so "$PLUGIN_DIR/libfhope.so"
sudo chmod 755 "$PLUGIN_DIR/libfhope.so"

echo "[build] installed $PLUGIN_DIR/libfhope.so"
