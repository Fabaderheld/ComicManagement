#!/usr/bin/env bash
#
# Comic Pipeline Helper
# Workflow: Scan -> Perdoo Scrape -> Normalize -> WebP
#

set -euo pipefail

# --- Configuration ---
PYTHON_SCRIPT="main.py"  # Path to your python script
COMICS_DIR="${1:-}"      # Take directory from first argument
LIST_FILE="to_process.txt"

# --- Validation ---
if [ -z "$COMICS_DIR" ]; then
    echo "Usage: $0 /path/to/comics"
    exit 1
fi

if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "Error: $PYTHON_SCRIPT not found in current directory."
    exit 1
fi

echo "============================================"
echo " Starting Comic Pipeline"
echo " Target: $COMICS_DIR"
echo "============================================"

# 1. SCAN
echo "[1/4] Scanning for files needing scraping..."


# Show the exact command
echo "[DEBUG] Command: python3 \"$PYTHON_SCRIPT\" scan --strict --output list \"$COMICS_DIR\" > \"$LIST_FILE\""

set +e

python3 "$PYTHON_SCRIPT" scan --strict --output list "$COMICS_DIR" > "$LIST_FILE"
SCAN_EXIT=$?
set -e

echo "[DEBUG] scan exit code: $SCAN_EXIT"

# Check if list is empty
if [ ! -s "$LIST_FILE" ]; then
    echo "✓ No files need scraping. Moving to maintenance steps..."
    FILES_FOUND=false
else
    COUNT=$(wc -l < "$LIST_FILE")
    echo "→ Found $COUNT files needing attention."
    FILES_FOUND=true
fi

# 2. PERDOO (Only if files found)
if [ "$FILES_FOUND" = true ]; then
    echo "[2/4] Running Perdoo Scraper..."
    echo "NOTE: Perdoo may be interactive. Please follow prompts."
    
    while IFS= read -r file; do
        echo "--- Processing: $(basename "$file") ---"
        perdoo import --skip-clean "$file" < /dev/tty
    done < "$LIST_FILE"
    echo "✓ Scraping complete."
else
    echo "[2/4] Skipping Perdoo (nothing to scrape)."
fi

# 3. NORMALIZE
echo "[3/4] Normalizing Metadata (Volume/AlternateSeries)..."
# We run this on the whole directory to ensure 'Start Year' calculation is accurate
python3 "$PYTHON_SCRIPT" normalize "$COMICS_DIR"
echo "✓ Normalization complete."

# 4. WEBP CONVERSION
echo "[4/4] Converting images to WebP..."
# This is idempotent; it will skip files that are already WebP
python3 "$PYTHON_SCRIPT" webp "$COMICS_DIR"
echo "✓ WebP conversion complete."

# --- Cleanup ---
if [ -f "$LIST_FILE" ]; then
    rm "$LIST_FILE"
fi

echo "============================================"
echo " Pipeline Finished Successfully!"
echo "============================================"
