#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The zip IngeTrazo's extension manager installs: one folder, dispersa/,
# with its __init__.py, from git HEAD (what is committed, nothing else).
#   tools/make_release.sh            -> build/dispersa-<version>.zip + sha256
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' dispersa/__init__.py)"
mkdir -p build
OUT="build/dispersa-$VER.zip"
rm -f "$OUT"
git archive --format=zip -9 -o "$OUT" HEAD dispersa
sha256sum "$OUT" | tee "$OUT.sha256"
