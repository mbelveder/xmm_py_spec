# A Python package to handle XMM-Newton spectra

Downloads and organizes [XMM-Newton PPS products](https://xmm-tools.cosmos.esa.int/external/xmm_user_support/documentation/dfhb/pps.html) data using [Astroquery](https://astroquery.readthedocs.io/en/latest/). Complements Astroquery behaviour by adding complementary PPS metadata: source and background regions (both ASC and PNG files), count rate curves used to extract GTI (good time intervals).

Optimized for the multiple spectra downloading.

## Input data (CSV file)

Source identifiers should be retrieved from a catalog, e. g. [5XMM](http://xmmssc.irap.omp.eu/) (the current release).

| srcid | src_num | obs_id | user_srcid (optional) |
|-------|---------|--------|---------------------|
| 201237001010017 | 36 | 147510901 | 1234 |
| 201237001010017 | 39 | 147511701 | 1234 |
| 201237001015028 | 9  | 147511301 | 1430 |

> [!IMPORTANT]
> **Always take `src_num` from the up-to-date XMM catalog (5XMM at the moment).**
> The PPS download selects a source purely by its per-observation number
> (`sourceno = src_num`). The ESA archive periodically reprocesses observations
> and **renumbers the detections**, so a `src_num` from an older catalogue
> (e.g. 4XMM) can silently resolve to a *different* source on the field — the
> spectra download "successfully" but belong to the wrong object. Using the
> catalogue release that matches the current archive avoids this.
>
> Include `ra` and `dec` columns (the catalogue source position, in degrees) so
> the downloader can verify each extracted spectrum against the expected
> position and reject wrong-source matches instead of keeping them silently
> (see [Logging and Validation](#logging-and-validation)).

## Result file structure

### PPS (default)

```bash
download_path/
├── download_meta.log      # Human-readable session log
├── download_meta.csv      # Machine-readable download status
└── srcid_user_srcid/      # Source directory (user_srcid is optional)
    ├── download.log       # Per-source download log
    └── obs_id_src_num/    # Observation directory
        └── PPS/           # PPS product directory
            └── PN/        # Instrument directory (PN, M1, or M2)
                ├── *SRSPEC*.FTZ  # Source spectrum
                ├── *BGSPEC*.FTZ  # Background spectrum
                ├── *SRCARF*.FTZ  # ARF file
                └── *.rmf         # RMF file
```

### ODF

```bash
download_path/
├── download_meta.log
├── download_meta.csv
└── srcid_user_srcid/
    ├── download.log
    └── obs_id/
        └── ODF/
            └── obs_id_ODF.tar.gz  # Raw observational data
```

## Usage

Download PN spectra (default):

```bash
python -m xmm_py_spec.download_spectra data/sources.csv
```

Download all instruments (PN, M1, M2):

```bash
python -m xmm_py_spec.download_spectra data/sources.csv --instruments PN M1 M2
```

Download ODF data:

```bash
python -m xmm_py_spec.download_spectra data/sources.csv --level ODF
```

Custom download path:

```bash
python -m xmm_py_spec.download_spectra data/sources.csv \
    --download-path /data/xmm_spectra
```

Keep source Astroquery files for debugging:

```bash
python -m xmm_py_spec.download_spectra data/sources.csv --keep-source
```

### CLI options

| Option | Default | Description |
|--------|---------|-------------|
| csv_path | *(required)* | Path to CSV file with observation data |
| --download-path | data/downloaded_spectra/ | Base directory for downloads |
| --instruments | PN | Instruments to download: PN, M1, M2 (PPS only) |
| --level | PPS | Data level: PPS or ODF |
| --keep-source | False | Keep original Astroquery files for debugging |
| --position-tolerance | 30 | Max arcsec between the extracted spectrum and the catalog `ra`/`dec` before a download is rejected as the wrong source (PPS only) |
| --no-position-check | False | Disable the source-position guard (not recommended) |

## Logging and Validation

The package provides comprehensive logging and validation:

- **Meta Logging**: Global session log in both human-readable (.log) and CSV formats
- **Per-source Logging**: Individual download logs for each source
- **File Validation**: Automatic validation of required spectral files (including HTML-error detection for RMF/ARF files returned as 404 pages)
- **Source-position Guard**: When the input CSV provides `ra`/`dec`, each extracted spectrum's header position is checked against the catalog position and rejected if it exceeds `--position-tolerance` (default 30″). This catches the silent wrong-source case where a stale `src_num` resolves to a different detection after archive reprocessing
- **Session Summary**: Final validation report at the end of each download session

> **Note**: The warning `More than one file found with the instrument: PN` from Astroquery is informational — it occurs when an observation has multiple exposures for the same instrument. All exposures are processed normally.

## Pipeline Commands

### Download spectra

Download PN spectra:
```bash
make download_PPS_PN OBS_LIST=sources.csv DOWNLOAD_PATH=data/downloaded_spectra
```

Download all instruments (PN, M1, M2):
```bash
make download_all_instruments OBS_LIST=sources.csv DOWNLOAD_PATH=data/downloaded_spectra
```

Download ODF data:
```bash
make download_ODF OBS_LIST=sources.csv DOWNLOAD_PATH=data/downloaded_spectra
```

### Combine spectra

Combine spectra using EPICSPECCOMBINE (default):
```bash
make combine_spectra_group_all
```

Combine spectra using ADDSPEC:
```bash
make combine_spectra_addspec_all
```

### Cluster and combine spectra

Cluster observations by time and combine (requires SOURCE_ID):
```bash
make cluster_and_combine_spectra_pn SOURCE_ID=201237001010017_5359
make cluster_and_combine_spectra_mos SOURCE_ID=201237001010017_5359
```

### Fit observations

Fit individual observations:
```bash
make fit_observations_all
```

Fit clustered observations:
```bash
make fit_clustered_observations_all
make fit_clustered_observations_pn_addspec
```

### Analyze spectra

```bash
make analyze_grouped_spectra
```

## Package structure

```bash
xmm_py_spec/
├── src/
│   ├── xmm_py_spec/
│   │   ├── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── validation.py                  # Custom exceptions and validation
│   │   ├── download_spectra.py                # Download and validation
│   │   ├── combine_spectra.py                 # Combine spectra from multiple observations
│   │   ├── cluster_and_combine_spectra.py     # Cluster observations and combine
│   │   ├── fit_observations.py                # Spectral fitting
│   │   ├── analyze_spectra.py                 # Spectral analysis
│   │   ├── analyze_spectral_variability.py    # Temporal variability analysis
│   │   ├── file_naming.py                     # File naming conventions
│   │   ├── models.py                          # Data models
│   │   ├── logging_config.py                  # Logging configuration
│   │   ├── plotting_settings.py               # Matplotlib settings
│   │   ├── source.py                          # Source utilities
│   │   └── utils.py                           # Common utilities
├── tests/
│   ├── __init__.py
│   └── test_xmm_py_spec.py
├── pyproject.toml
└── README.md
```
