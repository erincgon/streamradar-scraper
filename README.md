<<<<<<< HEAD
# StreamRadar Scraper System

StreamRadar is a lightweight, production-ready Python scraper pipeline that builds static JSON discovery feeds for a Flutter + SQLite mobile app.

## Features

- Modular scraper architecture (`scrapers/` + `utils/`)
- Public-source scraping (no paid APIs, no backend server)
- Retry logic + request timeouts + rate limiting
- Per-scraper fault isolation (one failure does not stop full run)
- Data normalization and duplicate removal
- Image URL validation
- JSON schema validation before writing output
- Scheduled GitHub Actions job every 6 hours

## Project Structure

```text
scrapers/
utils/
output/
.github/workflows/
main.py
config.py
requirements.txt
README.md
```

## Data Feeds Generated

The pipeline writes static UTF-8 JSON feeds under `output/`:

- `trending.json`
- `upcoming.json`
- `netflix.json`
- `disney_plus.json`
- `prime_video.json`
- `hbo_max.json`
- `cinema_releases.json`

Each item contains:

- `title`
- `year`
- `type` (`movie` / `series` / `documentary` / `anime`)
- `platform`
- `release_date`
- `overview`
- `genres`
- `poster_image_url`
- `backdrop_image_url`
- `rating`
- `trailer_url`
- `source_url`
- `scraped_at`

## Local Setup

### 1) Create virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

Optional Playwright browser install (only if you use dynamic page fetch):

```bash
playwright install chromium
```

### 3) Run scraper

```bash
python main.py
```

### 4) Output

Generated files are written to `output/*.json`.

## GitHub Deployment Instructions

1. Push this project to a GitHub repository.
2. Ensure GitHub Actions is enabled for the repository.
3. The workflow at `.github/workflows/scrape.yml` automatically:
   - installs Python 3.12
   - installs dependencies
   - runs `python main.py`
   - commits changed JSON files
   - pushes updates back to the repository
4. Trigger manually from GitHub Actions tab using **Run workflow**, or wait for the 6-hour schedule.

## Engineering Notes

- Feed outputs are deduplicated and sorted by `release_date` descending.
- Maximum of 100 entries per JSON file.
- Missing fields are safely normalized to fallback values.
- Network and parser failures are logged and isolated per scraper.
- No login-protected or illegal source scraping is performed.
=======
# StreamRadar Scraper System

StreamRadar is a lightweight, production-ready Python scraper pipeline that builds static JSON discovery feeds for a Flutter + SQLite mobile app.

## Features

- Modular scraper architecture (`scrapers/` + `utils/`)
- Public-source scraping (no paid APIs, no backend server)
- Retry logic + request timeouts + rate limiting
- Per-scraper fault isolation (one failure does not stop full run)
- Data normalization and duplicate removal
- Image URL validation
- JSON schema validation before writing output
- Scheduled GitHub Actions job every 6 hours

## Project Structure

```text
scrapers/
utils/
output/
.github/workflows/
main.py
config.py
requirements.txt
README.md
```

## Data Feeds Generated

The pipeline writes static UTF-8 JSON feeds under `output/`:

- `trending.json`
- `upcoming.json`
- `netflix.json`
- `disney_plus.json`
- `prime_video.json`
- `hbo_max.json`
- `cinema_releases.json`

Each item contains:

- `title`
- `year`
- `type` (`movie` / `series` / `documentary` / `anime`)
- `platform`
- `release_date`
- `overview`
- `genres`
- `poster_image_url`
- `backdrop_image_url`
- `rating`
- `trailer_url`
- `source_url`
- `scraped_at`

## Local Setup

### 1) Create virtual environment

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

Optional Playwright browser install (only if you use dynamic page fetch):

```bash
playwright install chromium
```

### 3) Run scraper

```bash
python main.py
```

### 4) Output

Generated files are written to `output/*.json`.

## GitHub Deployment Instructions

1. Push this project to a GitHub repository.
2. Ensure GitHub Actions is enabled for the repository.
3. The workflow at `.github/workflows/scrape.yml` automatically:
   - installs Python 3.12
   - installs dependencies
   - runs `python main.py`
   - commits changed JSON files
   - pushes updates back to the repository
4. Trigger manually from GitHub Actions tab using **Run workflow**, or wait for the 6-hour schedule.

## Engineering Notes

- Feed outputs are deduplicated and sorted by `release_date` descending.
- Maximum of 100 entries per JSON file.
- Missing fields are safely normalized to fallback values.
- Network and parser failures are logged and isolated per scraper.
- No login-protected or illegal source scraping is performed.
>>>>>>> a54f1052100b7179363b61455accbc85eb01e61a
