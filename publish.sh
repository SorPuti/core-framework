#!/usr/bin/env bash
# Publicação de release: bump, build, upload PyPI, commit e push.
# Uso: ./publish.sh [VERSÃO]   ou   ./publish.sh [patch|minor|major]
# Ex.: ./publish.sh           # interativo, sugere patch
#      ./publish.sh 0.18.0    # publica versão exata
#      ./publish.sh minor     # 0.17.38 -> 0.18.0
#      ./publish.sh --dry-run # só mostra o que faria
source .venv/bin/activate
set -e
cd "$(dirname "$0")"

# Python: preferir python3 se python não existir (Linux)
PYTHON=""
for p in python3 python; do
  if command -v "$p" &>/dev/null; then
    PYTHON="$p"
    break
  fi
done
[[ -z "$PYTHON" ]] && { echo "Erro: python ou python3 não encontrado."; exit 1; }

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}$*${NC}"; }
warn()  { echo -e "${YELLOW}$*${NC}"; }
ok()    { echo -e "${GREEN}$*${NC}"; }
err()   { echo -e "${RED}$*${NC}"; }
title() { echo -e "\n${BOLD}${CYAN}═══ $* ═══${NC}\n"; }

# ── Argumentos ──
DRY_RUN=false
VERSION_ARG=""
for a in "$@"; do
  case "$a" in
    --dry-run|-n) DRY_RUN=true ;;
    patch|minor|major) VERSION_ARG="$a" ;;
    [0-9]*.[0-9]*.[0-9]*) VERSION_ARG="$a" ;;
    *) ;;
  esac
done

# ── Ler versão atual ──
CURRENT=$(grep -E '^version\s*=' pyproject.toml | sed -E 's/.*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/')
if [[ -z "$CURRENT" ]]; then
  err "Não foi possível ler version de pyproject.toml"
  exit 1
fi

# ── Calcular próxima versão ──
calc_next_version() {
  local kind="$1"
  local major minor patch
  major=$(echo "$CURRENT" | cut -d. -f1)
  minor=$(echo "$CURRENT" | cut -d. -f2)
  patch=$(echo "$CURRENT" | cut -d. -f3)

  case "$kind" in
    patch)  echo "$major.$minor.$((patch + 1))" ;;
    minor)  echo "$major.$((minor + 1)).0" ;;
    major)  echo "$((major + 1)).0.0" ;;
    *)      echo "" ;;
  esac
}

# ── Definir NEW_VERSION ──
if [[ -n "$VERSION_ARG" ]]; then
  case "$VERSION_ARG" in
    patch)  NEW_VERSION=$(calc_next_version patch) ;;
    minor)  NEW_VERSION=$(calc_next_version minor) ;;
    major)  NEW_VERSION=$(calc_next_version major) ;;
    *)      NEW_VERSION="$VERSION_ARG" ;;
  esac
else
  # Padrão: patch
  NEW_VERSION=$(calc_next_version patch)
fi

# ── Validação semver ──
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  err "Versão inválida: $NEW_VERSION (use major.minor.patch)"
  exit 1
fi

# ── Resumo interativo ──
title "Publicar stride"
info "Versão atual:  ${BOLD}$CURRENT${NC}"
info "Nova versão:   ${BOLD}$NEW_VERSION${NC}"
if [[ -n "$VERSION_ARG" && "$VERSION_ARG" != "patch" ]]; then
  info "Tipo:          $VERSION_ARG"
fi

if [[ "$DRY_RUN" == "true" ]]; then
  warn "Modo dry-run: nenhuma alteração será feita."
  echo ""
  echo "Passos que seriam executados:"
  echo "  1. Atualizar version em pyproject.toml e stride/__init__.py para $NEW_VERSION"
  echo "  2. rm -rf dist/ && python -m build"
  echo "  3. twine upload dist/*"
  echo "  4. git add pyproject.toml stride/__init__.py && git commit -m \"chore: bump version to $NEW_VERSION\" && git push"
  exit 0
fi

echo ""
read -p "Publicar versão $NEW_VERSION? (y/N): " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  info "Publicação cancelada."
  exit 0
fi

# ── 1. Bump nos arquivos ──
title "1. Atualizando versão"
sed -i "s/^version = \"[^\"]*\"/version = \"$NEW_VERSION\"/" pyproject.toml
sed -i "s/^__version__ = \"[^\"]*\"/__version__ = \"$NEW_VERSION\"/" stride/__init__.py
ok "Versão $NEW_VERSION definida em pyproject.toml e stride/__init__.py"

# ── 2. Build ──
title "2. Build do pacote"
rm -rf dist/
# Forçar índice de instalação: token PyPI em PIP_INDEX_URL quebra o build (upload ≠ install)
PIP_INDEX_URL="https://pypi.org/simple" PIP_EXTRA_INDEX_URL="" "$PYTHON" -m build
ok "Build concluído: dist/"

# ── 3. Upload PyPI ──
title "3. Upload para PyPI"
if ! command -v twine &>/dev/null; then
  err "twine não encontrado. Instale: pip install twine"
  exit 1
fi
read -p "Enviar para PyPI? (y/N): " UPLOAD
if [[ "$UPLOAD" == "y" || "$UPLOAD" == "Y" ]]; then
  twine upload dist/*
  ok "Publicado: https://pypi.org/project/stride/$NEW_VERSION/"
else
  warn "Upload para PyPI ignorado."
fi

# ── 4. Git commit e push ──
title "4. Git"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if ! git diff --quiet pyproject.toml stride/__init__.py 2>/dev/null; then
  git add pyproject.toml stride/__init__.py
  git status
  read -p "Fazer commit e push para '$BRANCH'? (y/N): " PUSH
  if [[ "$PUSH" == "y" || "$PUSH" == "Y" ]]; then
    git commit -m "chore: bump version to $NEW_VERSION"
    git push origin "$BRANCH"
    ok "Push concluído: $NEW_VERSION em $BRANCH"
  else
    warn "Commit/push ignorado. Versão alterada apenas localmente."
  fi
else
  info "Nenhuma alteração pendente em pyproject.toml / stride/__init__.py"
fi

title "Concluído"
info "Versão: $NEW_VERSION"
info "Branch: $BRANCH"
