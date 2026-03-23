#!/usr/bin/env bash
set -euo pipefail

# Build MkDocs documentation
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v mkdocs >/dev/null 2>&1; then
  echo "mkdocs not found. Instale com: pip install mkdocs mkdocs-material"
  exit 1
fi

mkdocs build --clean

echo "Docs built to ./site"
