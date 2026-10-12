# NU reading-list exporter (Chrome extension)

Vendored snapshot of
[OliverSiwers/NoveUpdates-reading-list-exporter](https://github.com/OliverSiwers/NoveUpdates-reading-list-exporter)
at commit `817c19d`. Manifest V3, no build step, no dependencies.

## Why it lives here

This extension is the upstream producer of the scraper's reading-list import.
It exports the logged-in user's NovelUpdates reading lists to a
`novelupdates-<timestamp>.json` file. Drop that file into
`data/reading_lists/` and `main.py` picks it up at startup via
[`core/import_nu_export.py`](../../core/import_nu_export.py), which populates
`series_info` (current chapter, latest chapter, list name) so the My List page
knows where you are in each series.

The importer depends on this extension's exact output schema — including the
upstream `letestChapter` key spelling — so the tool is kept in the repo rather
than referenced as an external download.

## Install

1. Open `chrome://extensions` and enable **Developer mode**.
2. **Load unpacked** → select this `tools/nu-reading-list-exporter/` directory.

## Use

1. Log in to novelupdates.com and open any page on `www.novelupdates.com`
   (the forums do not work).
2. Click the extension icon and confirm the export.
3. Move the downloaded `novelupdates-*.json` into `data/reading_lists/`.
