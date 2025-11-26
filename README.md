# A Python package to handle XMM-Newton spectra

Downloads and organizes [XMM-Newton PPS products](https://xmm-tools.cosmos.esa.int/external/xmm_user_support/documentation/dfhb/pps.html) data using [Astroquery](https://astroquery.readthedocs.io/en/latest/). Complements Astroquery behaviour by adding observational metadata: source and background regions (PNG files), count rate curves used to extract GTI (good time intervals).

Optimized for the multiple spectra downloading.

## Input data (CSV file)

Could be retrieved from a catalog, e. g. [4XMM-DR14](http://xmmssc.irap.omp.eu/Catalogue/4XMM-DR14/4XMM_DR14.html).

| srcid | src_num | obs_id | user_srcid (optional) |
|-------|---------|--------|---------------------|
| 201237001010017 | 36 | 147510901 | 1234 |
| 201237001010017 | 39 | 147511701 | 1234 |
| 201237001015028 | 9  | 147511301 | 1430 |

## Result file structure

```bash
download_path/
├── download_meta.log      # Human-readable session log
├── download_meta.csv      # Machine-readable download status
└── srcid_user_srcid/     # Source directory (user_srcid is optional)
    ├── download.log      # Per-source download log
    └── obs_id_src_num/   # Observation directory
        └── PPS/          # Product directory
            └── PN/       # Instrument directory
                ├── *SRSPEC*.FTZ  # Source spectrum
                ├── *BGSPEC*.FTZ  # Background spectrum
                ├── *SRCARF*.FTZ  # ARF file
                └── *.rmf         # RMF file
```

## Usage

Basic download:

```bash
python -m xmm_py_spec.download_spectra data/sources.csv
```

Keep source Astroquery files for debugging:

```bash
python -m xmm_py_spec.download_spectra data/sources.csv --keep-source
```

## Logging and Validation

The package provides comprehensive logging and validation:

- **Meta Logging**: Global session log in both human-readable (.log) and CSV formats
- **Per-source Logging**: Individual download logs for each source
- **File Validation**: Automatic validation of required spectral files
- **Session Summary**: Final validation report at the end of each download session

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
│   │   ├── download_spectra.py           # Download and validation
│   │   ├── combine_spectra.py            # Combine spectra from multiple observations
│   │   ├── cluster_and_combine_spectra.py # Cluster observations and combine
│   │   ├── fit_observations.py           # Spectral fitting
│   │   ├── analyze_spectra.py            # Spectral analysis
│   │   ├── file_naming.py                # File naming conventions
│   │   ├── models.py                     # Data models
│   │   ├── logging_config.py             # Logging configuration
│   │   └── utils.py                      # Common utilities
├── tests/
│   ├── __init__.py
│   └── test_xmm_py_spec.py
├── pyproject.toml
└── README.md
```

## TODO

Fix: `data/source_201237001015035_7170_individual_PN_gap30_epicspeccombine_results.csv`