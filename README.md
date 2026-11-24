# Buoy Bench

Compare real ECCC buoy observations in the Pacific and Atlantic, retain marine forecast editions, and review observations made after an edition was saved. The public browser app runs from static files at https://coolcode.ca/buoybench/ and needs no account or API key.

<!-- coolcode:guide -->
Choose a buoy, comparison buoy and dated capture. Wind is shown in knots, significant wave height in metres, and water temperature in °C; each plotted point is a source observation. Select a retained forecast edition to read what ECCC issued and inspect the later observations. Forecasts describe areas while buoys measure points, so this is a manual comparison rather than an accuracy score. First-run forecasts correctly show that later observations are still awaited. Save a receipt JSON to keep the record outside this tab.
<!-- /coolcode:guide -->

## Use it

- The initial watchlist contains **Halibut Bank**, **Sentry Shoal**, **Halifax Harbour** and **La Have Bank**. Change either buoy selector to compare coastal readings. The times need not match; the latest times are visible.
- Choose a measurement and observation window. Missing measurements stay missing, and chart lines break across missing values or gaps longer than three hours. Mean wind is converted from km/h to knots using 1 knot = 1.852 km/h. A 20-minute significant wave height is not the maximum wave height.
- The forecast panel retains the narrative wording, issue time, first capture time and exact source URL. Where the marine area includes subregions, the configured subregion narrows the displayed regular forecast. Extended forecasts can apply more broadly.
- **Observed after we saved it** only includes observations whose measurement time is later than the forecast's first capture and issue time. The displayed ranges cover all subsequently retained observations, even beyond the narrative period; they are not automatically paired forecast errors. This avoids claiming predictive evidence from a forecast downloaded after conditions occurred.
- **Save receipt JSON** downloads the complete retained ledger. **Import a saved receipt** validates and displays one local ledger, replacing only this tab's view. **Export observations CSV** exports all observations matching the selected buoy, capture and window.
- Source observations may be corrected. Distinct normalized revisions are retained; each dated capture uses the newest revision available at that capture. Counts on the page label revisions explicitly.

## Data, retention and meaning

Data Source: **Environment and Climate Change Canada**. Contains information licenced under the [Data Server End-use Licence of ECCC](https://eccc-msc.github.io/open-data/licence/readme_en/). This project is independent and is not endorsed by ECCC.

Primary sources:

- [Marine SWOB observation documentation](https://eccc-msc.github.io/open-data/msc-data/obs_station/readme_obs_insitu_swobdatamart_en/)
- [SWOB quality-assessment flag guide](https://dd.weather.gc.ca/today/observations/doc/SWOB-ML_Product_User_Guide_v8.17_e.pdf)
- [Marine station catalogue](https://api.weather.gc.ca/collections/swob-marine-stations/items?f=json&limit=10000)
- [Marine forecast XML documentation](https://eccc-msc.github.io/open-data/msc-data/marine-weather/readme_marine-weather-datamart_en/)
- [Forecast area catalogue](https://dd.weather.gc.ca/today/marine_weather/regionList.xml)
- [Current official forecasts and warnings](https://weather.gc.ca/marine/)

The GitHub workflow requests collection every six hours at minute 17. GitHub schedules can be late or disabled after prolonged repository inactivity. The page labels the actual capture time and flags a published collection older than 18 hours.

The collector reads the last two UTC dates by default, at most 24 files per station per day, and selects the most recently published file for each configured forecast area. Datamart dated archives use `/YYYYMMDD/WXO-DD/`; the `/today/` aliases are documentation/discovery links. Requests use a descriptive User-Agent and a maximum of four concurrent observation downloads. HTTP4xx failures, including rate limits, stop collection; bounded retries are limited to network/5xx failures. A failed required retrieval or parse never replaces the saved ledger or live deployment. A station with no files in the selected date range is explicitly recorded; other stations can still update. A forecast area must have a dated regular forecast for publication.

`web/data/ledger.json` contains observations, forecast editions and capture metadata. The default rolling retention is 90 days. Older versions remain in Git history; download JSON for your own longer archive. Identical forecast republications are deduplicated; changed content becomes a new edition even with the same issue time. The ledger capture date marks completion of a successful collection. Each newly retrieved observation and forecast has its own first-retrieval timestamp. A record capture is when the project first knew that record, not when a forecast was issued or a buoy measured it. Existing observations are not fetched repeatedly by source URL; differently named correction files are new candidates. An upstream change made in place at the same URL is not guaranteed to be detected.

Observations are provisional. Values with a provider `qa_summary` other than `100` are excluded from comparison and the quality code is retained. Fields without a supplied summary are not represented as provider-certified. Missing and unavailable fields stay null. Original units are validated before conversion. Buoys can be seasonal, offline or geographically unrepresentative of an entire forecast area. Forecast text is retained for research; this is not a navigation, current-warning or safety service.

## Expand or customize

Edit **`web/config.json`**. Presets are a watchlist, not an application limit. Add a station using the extended 5–7 digit identifier from the Datamart marine directory. Example additional station:

```json
{"id":"4600206","name":"La Perouse Bank","coast":"Pacific","forecastId":"","forecastLocation":""}
```

Fields:

| Field | Meaning |
| --- | --- |
| `id` | Datamart station directory ID; e.g. `4600146`, which corresponds to Halibut Bank's five-digit WMO ID `46146` |
| `name` | Display name |
| `coast` | Display grouping |
| `forecastId` | Optional reference to an entry in `forecasts`; blank means observation-only |
| `forecastLocation` | Exact subregion name in forecast XML; blank keeps all locations |

Add forecast areas under `forecasts`, with `id`, `domain` and `name` from the official area catalogue. A forecast-area association is your explicit research choice; this app does not automatically claim a buoy is representative of it. Set `defaultStation` and `compareStation` to existing IDs. Tune `retentionDays` (7–365), `lookbackDays` (1–3) and `maxFilesPerStationPerDay` (1–48). Safeguards cap one collection at 50 stations. The UI derives lists and counts from actual retained data; removing a station from the current watchlist does not invalidate earlier captures.

After saving config, push it to main, then run **Buoy Bench · Check and publish** in GitHub Actions with **Refresh source data** checked. A normal source push rebuilds the saved dataset without fetching. Scheduled runs refresh automatically. Locally:

```sh
python3 scripts/refresh.py
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -v
python3 scripts/build.py
```

Commit changed `web/data/` files together with configuration when collecting locally. The workflow also commits its successful refresh, then tests/builds/deploys that exact commit. Invalid refreshes fail before data replacement. Changing configuration alone does not create new observations.

## Architecture and privacy

`web/model.mjs` contains transformations; `web/app.mjs` renders text safely. No secrets, external tiles, fonts or browser API requests are needed. The browser reads only published CoolCode files; source links contact the publisher only when clicked. Imports stay in tab memory and no preferences or uploads are saved automatically. The shared CoolCode visit counter handles aggregate usage independently of inputs.

The Python standard-library collector parses official XML, stores normalized source data and provenance, and atomically replaces the ledger only after validation. The static build is offline. Browser CI checks station selection, measurement selection, receipt download, safe rendering and mobile width. Source metadata and template build checks are also tested.

<!-- schedule-reliability -->
## Schedule reliability

Public GitHub repositories can have scheduled workflows disabled after 60 days of inactivity. A separate weekly [schedule guard](.github/workflows/schedule-guard.yml) calls GitHub's enable-workflow API for an explicit list of refresh workflows and itself. It can restore workflows disabled for inactivity, preserves manually disabled workflows, and runs independently of collection failures.

This is an interim mitigation, not a scheduling guarantee: GitHub does not document active-workflow renewal as a permanent exemption, and scheduled runs can be delayed or dropped. A scheduler on our own Linux server is the planned independent trigger. The guard does not collect data, create dummy commits, or change source/check timestamps; successful collection and published data freshness still need monitoring.
<!-- /schedule-reliability -->
