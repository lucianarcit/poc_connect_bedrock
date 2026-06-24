#!/usr/bin/env bash
# build_lambdas.sh — Empacota as 3 Lambdas para deploy.
# Requer: Python 3.12, pip, zip.
# Gera: packages/initializer.zip, packages/integrator.zip, packages/mcp_server.zip
#
# Uso: ./scripts/build_lambdas.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGES="$ROOT/packages"
SRC="$ROOT/src"

rm -rf "$PACKAGES"
mkdir -p "$PACKAGES"

echo "=== Building Lambda packages ==="

build_lambda() {
    local name="$1"
    shift
    local source_dirs=("$@")

    echo ""
    echo "--- Packaging $name ---"
    local build_dir="$PACKAGES/${name}_build"
    mkdir -p "$build_dir"

    # Instalar dependências
    echo "  Installing dependencies..."
    pip install boto3 mcp mangum pydantic httpx -t "$build_dir" --quiet --upgrade

    # Copiar código fonte
    for dir in "${source_dirs[@]}"; do
        echo "  Copying $dir..."
        cp -r "$SRC/$dir" "$build_dir/"
    done

    # Criar zip
    echo "  Creating $name.zip..."
    (cd "$build_dir" && zip -r "$PACKAGES/$name.zip" . -q)

    rm -rf "$build_dir"
    echo "  Done: $name.zip ($(du -h "$PACKAGES/$name.zip" | cut -f1))"
}

# --- Initializer ---
build_lambda "initializer" "initializer" "integrator" "shared"

# --- Integrator (inclui sample_documents e mcp_server para MCP local) ---
build_lambda "integrator" "integrator" "shared" "mcp_server"
# Adicionar sample_documents ao zip do integrator
(cd "$ROOT" && zip -r "$PACKAGES/integrator.zip" sample_documents/ -q)

# --- MCP Server ---
build_lambda "mcp_server" "mcp_server" "shared"
# Adicionar sample_documents
(cd "$ROOT" && zip -r "$PACKAGES/mcp_server.zip" sample_documents/ -q)

echo ""
echo "=== All packages built ==="
ls -lh "$PACKAGES"/*.zip
