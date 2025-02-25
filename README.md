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
base_dir/
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

## Package structure

```bash
xmm_py_spec/
├── src/
│   ├── xmm_py_spec/
│   │   ├── __init__.py
│   │   ├── download_spectra.py  # Download and validation
│   │   └── utils.py             # Common utilities
├── tests/
│   ├── __init__.py
│   └── test_xmm_py_spec.py
├── pyproject.toml
└── README.md
