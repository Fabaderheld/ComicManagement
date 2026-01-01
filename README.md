Here's a comprehensive README for your comic pipeline script:

```markdown
# Comic Pipeline Helper

A Python CLI tool for managing and normalizing comic book archives (CBZ/CBR), with automated scraping, metadata normalization, and image optimization.

## Features

- **Scan** comics for missing or incomplete metadata
- **Normalize** metadata (set `Volume` to series start year, populate `AlternateSeries`)
- **Convert** images to WebP for smaller file sizes
- **Sync** with Kapowarr library management
- **Bash pipeline** wrapper for automated workflows with Perdoo scraper integration

---

## Installation

### Requirements

- Python 3.7+
- `Pillow` (for image conversion)
- `requests` (for Kapowarr sync)
- [Perdoo](https://github.com/Buried-In-Code/Perdoo) (optional, for scraping)

Install Python dependencies:

```bash
pip install Pillow requests
```

### Setup

Clone or download the script:

```bash
git clone <your-repo-url>
cd <repo-directory>
chmod +x comic-pipeline.sh  # Make bash wrapper executable
```

---

## Usage

### Python CLI Commands

#### 1. `scan` – Find comics needing metadata

Scans CBZ/CBR files and reports which ones need scraping based on missing metadata fields.

```bash
python3 main.py scan [--strict] [--output FORMAT] [--output-file FILE] <paths...>
```

**What it checks:**

| Field | Required | Strict Mode Only | Notes |
|-------|----------|------------------|-------|
| `Series` | ✅ Yes | | Comic series name |
| `Number` | ✅ Yes | | Issue number |
| `Year` | ✅ Yes | | Publication year (4-digit) |
| `Publisher` | | ✅ Yes | Publisher name |
| `Title` | | ✅ Yes | Issue title |
| `MetronInfo.xml` | | | If present, file is considered already scraped |

**Special behavior:**

- If `MetronInfo.xml` exists in the archive, the file is **skipped** (assumed already scraped by Perdoo)
- CBR files are included in scan results (they need conversion to CBZ)
- Files in `#recycle` directories are ignored

**Output formats:**

- `console` (default): Human-readable output with reasons
- `json`: Machine-readable JSON array
- `list`: Plain list of file paths (one per line, for piping to other tools)

**Examples:**

```bash
# Scan a directory (basic checks only)
python3 main.py scan /path/to/comics

# Scan with strict checks (requires Publisher + Title)
python3 main.py scan --strict /path/to/comics

# Output as JSON
python3 main.py scan --output json --output-file results.json /path/to/comics

# Output as list for piping to Perdoo
python3 main.py scan --output list /path/to/comics > to_scrape.txt
cat to_scrape.txt | xargs -I {} perdoo import --skip-clean {}
```

**Exit codes:**

- `0` = No files need scraping
- `1` = Files need scraping (list printed/saved)
- `2+` = Error

---

#### 2. `normalize` – Fix metadata inconsistencies

Normalizes `ComicInfo.xml` metadata across your library:

1. **Sets `Volume` to series start year**: Analyzes all issues in a series and sets `<Volume>` to the year of issue #1
2. **Populates `AlternateSeries`**: Copies `StoryArc` or `StoryArcTitle` into `AlternateSeries` if empty

```bash
python3 main.py normalize [--dry-run] [--verbose] <paths...>
```

**What it does:**

**Pass 1: Detect series runs**
- Scans all CBZ files in the given paths
- Groups by `Series` + `Publisher`
- Finds the earliest `Year` for each series (the "start year")

**Pass 2: Apply normalization**

For each file:

| Field | Action | Example |
|-------|--------|---------|
| `Volume` | Set to series start year | `<Volume>2016</Volume>` |
| `AlternateSeries` | Copy from `StoryArc` if empty | `<AlternateSeries>I Am Gotham</AlternateSeries>` |

**Output:**

Shows per-file changes:

```
[NORMALIZE] Batman Vol.2016 - #001.cbz
  Volume: <none> -> 2016
  AlternateSeries: <none> -> I Am Gotham

[NORMALIZE] Batman Vol.2016 - #002.cbz
  Volume: 2015 -> 2016
```

**Examples:**

```bash
# Normalize a directory
python3 main.py normalize /path/to/comics

# Dry-run (preview changes without writing)
python3 main.py normalize --dry-run /path/to/comics

# Verbose output (show XML previews)
python3 main.py normalize --verbose /path/to/comics

# Normalize specific files
python3 main.py normalize file1.cbz file2.cbz file3.cbz
```

---

#### 3. `webp` – Convert images to WebP

Converts JPG/PNG pages inside CBZ files to WebP format for smaller file sizes.

```bash
python3 main.py webp [--quality QUALITY] [--dry-run] <paths...>
```

**What it does:**

- Opens each CBZ file
- Checks image formats (only processes JPG/PNG)
- Converts to WebP with specified quality (default: 90)
- Rewrites the CBZ with converted images

**Options:**

- `--quality N` (default: 90): WebP quality (1-100)
- `--dry-run`: Preview which files would be converted

**Examples:**

```bash
# Convert all comics in a directory
python3 main.py webp /path/to/comics

# Use higher quality
python3 main.py webp --quality 95 /path/to/comics

# Dry-run
python3 main.py webp --dry-run /path/to/comics
```

---

#### 4. `kapowarr-sync` – Sync with Kapowarr

Updates Kapowarr's library with corrected `Volume` metadata from your normalized comics.

```bash
python3 main.py kapowarr-sync [--kapowarr-url URL] [--kapowarr-key KEY] [--dry-run] <paths...>
```

**Requirements:**

- ComicVine API key (via `--comicvine-key` or `COMICVINE_API_KEY` env var)
- Kapowarr API key (via `--kapowarr-key` or `KAPOWARR_API_KEY` env var)

**What it does:**

1. Reads `ComicInfo.xml` from each CBZ
2. Queries ComicVine API for volume info
3. Updates Kapowarr's database via its API

**Examples:**

```bash
# Sync with default Kapowarr instance (localhost:5656)
python3 main.py kapowarr-sync --comicvine-key YOUR_KEY /path/to/comics

# Custom Kapowarr URL
python3 main.py kapowarr-sync \
  --comicvine-key YOUR_KEY \
  --kapowarr-key YOUR_KAPOWARR_KEY \
  --kapowarr-url http://192.168.1.100:5656 \
  /path/to/comics
```

---

### Bash Pipeline Wrapper

The `comic-pipeline.sh` script automates the full workflow:

```
Scan → Perdoo Scrape → Normalize → WebP
```

#### Usage

```bash
./comic-pipeline.sh /path/to/comics
```

#### What it does

1. **Scan** for files needing scraping (CBZ + CBR)
2. **Perdoo** (if files found): Runs `perdoo import --skip-clean` on each file
   - Converts CBR → CBZ
   - Scrapes metadata from ComicVine
   - Writes `ComicInfo.xml` and `MetronInfo.xml`
3. **Normalize**: Fixes `Volume` and `AlternateSeries` across the entire directory
4. **WebP**: Converts images to WebP for all comics

#### Behavior

- If **no files need scraping**: Skips Perdoo, still runs normalize + webp
- If **files already scraped** (have `MetronInfo.xml`): Won't re-scrape them
- Perdoo is **interactive**: You can answer prompts during scraping
- Idempotent: Safe to run multiple times

#### Example output

```
============================================
 Starting Comic Pipeline
 Target: /mnt/synology/comics/DC Comics/Batman (2016)/
============================================
[1/4] Scanning for files needing scraping (CBZ + CBR)...
→ Found 12 files needing attention.
[2/4] Running Perdoo Scraper...
NOTE: Perdoo may be interactive. Please follow prompts.
--- Processing: Batman Vol.2016 - #150.cbz ---
INFO     Metadata up-to-date
✓ Scraping complete.
[3/4] Normalizing Metadata (Volume/AlternateSeries)...
Detected runs:
- DC Comics | Batman -> start year 2016
[NORMALIZE] Batman Vol.2016 - #150.cbz
  Volume: <none> -> 2016
Changed 12 files
✓ Normalization complete.
[4/4] Converting images to WebP...
✓ WebP conversion complete.
============================================
 Pipeline Finished Successfully!
============================================
```

---

## Workflow Examples

### Initial library setup

```bash
# Run full pipeline on entire library
./comic-pipeline.sh /path/to/comics
```

### Add new comics

```bash
# Just run the pipeline again – it only processes what needs work
./comic-pipeline.sh /path/to/comics
```

### Manual workflow (without bash wrapper)

```bash
# 1. Find files needing scraping
python3 main.py scan --strict --output list /path/to/comics > to_scrape.txt

# 2. Scrape with Perdoo
cat to_scrape.txt | xargs -I {} perdoo import --skip-clean {}

# 3. Normalize metadata
python3 main.py normalize /path/to/comics

# 4. Convert to WebP
python3 main.py webp /path/to/comics
```

---

## Configuration

### API Keys

For `kapowarr-sync` command:

```bash
# Option 1: Environment variables (recommended)
export COMICVINE_API_KEY="your_key_here"
export KAPOWARR_API_KEY="your_key_here"

# Option 2: Command-line arguments
python3 main.py kapowarr-sync \
  --comicvine-key YOUR_KEY \
  --kapowarr-key YOUR_KEY \
  /path/to/comics
```

### Default Kapowarr URL

Default: `http://localhost:5656`

Override with `--kapowarr-url` argument.

---

## Troubleshooting

### Files keep getting re-scraped

**Cause:** `scan` still detects missing metadata after Perdoo runs.

**Solution:** The script now checks for `MetronInfo.xml` presence. If a file has `MetronInfo.xml`, it's considered already scraped and won't be re-processed.

If you're still seeing re-scraping, check what `scan` reports:

```bash
python3 main.py scan --strict /path/to/problem-file.cbz
```

### Perdoo hangs or says "Input is not a terminal"

**Cause:** Perdoo needs interactive input but stdin is redirected.

**Solution:** The bash wrapper uses `< /dev/tty` to give Perdoo terminal access. Make sure you're using the provided `comic-pipeline.sh` script.

### "0 files changed" during normalize

**Cause:** Files already have correct `Volume` values, or `StoryArc` is empty.

**Solution:** This is normal if you've already run normalize. Use `--dry-run --verbose` to see why files are skipped:

```bash
python3 main.py normalize --dry-run --verbose /path/to/comics
```

---

## File Format Support

| Format | Scan | Normalize | WebP | Notes |
|--------|------|-----------|------|-------|
| `.cbz` | ✅ | ✅ | ✅ | Fully supported |
| `.cbr` | ✅ | ❌ | ❌ | Detected by scan; Perdoo converts to CBZ |

**Note:** CBR files are included in `scan` output so they can be sent to Perdoo for conversion to CBZ. After conversion, `normalize` and `webp` will process the resulting CBZ files.

---

## License

[Your license here]

## Contributing

[Your contribution guidelines here]
```

---

This README covers:

- ✅ What each command does
- ✅ Detailed scan checks (with the MetronInfo.xml behavior)
- ✅ Detailed normalize logic (two-pass explanation)
- ✅ Bash pipeline workflow
- ✅ Common troubleshooting scenarios
- ✅ Examples for every use case

Feel free to adjust the license/contributing sections or add installation details specific to your setup!
