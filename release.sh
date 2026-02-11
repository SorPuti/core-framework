#!/usr/bin/env bash
# Release script: add, commit, push, build, bump, upload to PyPI
# Usage: ./release.sh [VERSION]
#   VERSION: optional, e.g. 0.18.0 (default: auto-increment patch)

set -e
cd "$(dirname "$0")"

# ── 1. Git add, commit e push se tiver alterações ──
git add .
if ! git diff --staged --quiet 2>/dev/null; then
    echo " Committing and pushing changes..."
    git commit -m "chore: updates before release"
    # ── 2. Commit e push do bump ──
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    echo "Current branch: $CURRENT_BRANCH"
    read -p "Confirm push to branch '$CURRENT_BRANCH'? (y/N): " CONFIRM

    if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
      echo "Push aborted."
      exit 1
    fi

    git add pyproject.toml core/__init__.py
    git commit -m "chore: bump version to $NEW_VERSION"
    echo " Done."
else
    echo " No pending changes to commit."
fi

# ── 2. Determinar nova versão ──
CURRENT=$(grep -E '^version\s*=' pyproject.toml | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')
if [[ -n "$1" ]]; then
    NEW_VERSION="$1"
    echo " Bump to $NEW_VERSION (from argument)"
else
    # Auto-increment patch: 0.17.2 -> 0.17.3
    MAJOR=$(echo "$CURRENT" | cut -d. -f1)
    MINOR=$(echo "$CURRENT" | cut -d. -f2)
    PATCH=$(echo "$CURRENT" | cut -d. -f3)
    PATCH=$((PATCH + 1))
    NEW_VERSION="$MAJOR.$MINOR.$PATCH"
    echo " Bump to $NEW_VERSION (auto-increment from $CURRENT)"
fi

# ── 3. Aplicar bump ──
sed -i "s/^version = \"[^\"]*\"/version = \"$NEW_VERSION\"/" pyproject.toml
sed -i "s/^__version__ = \"[^\"]*\"/__version__ = \"$NEW_VERSION\"/" core/__init__.py
echo " Version updated in pyproject.toml and core/__init__.py"

# ── 4. Limpar dist e fazer build ──
rm -rf dist/
echo " Building package..."
python -m build
echo " Build complete: dist/"

# ── 5. Upload para PyPI ──
echo " Uploading to PyPI..."
twine upload dist/*
echo " Uploaded: https://pypi.org/project/core-framework/$NEW_VERSION/"

# ── 6. Commit e push do bump ──

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Current branch: $CURRENT_BRANCH"
read -p "Confirm push to branch '$CURRENT_BRANCH'? (y/N): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Push aborted."
  exit 1
fi

git add pyproject.toml core/__init__.py
git commit -m "chore: bump version to $NEW_VERSION"
git push origin "$CURRENT_BRANCH"

echo "Done. Version $NEW_VERSION pushed to $CURRENT_BRANCH."
