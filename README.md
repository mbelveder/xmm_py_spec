## A Python package to handle XMM-Newton spectra

### Package structure
```bash
xmm_py_spec/
├── src/
│   ├── xmm_py_spec/
│   │   ├── __init__.py
│   │   ├── download_spectra.py  # Download functions
│   │   └── utils.py             # Common utilities
├── tests/
│   ├── __init__.py
│   └── test_xmm_py_spec.py
├── pyproject.toml
└── README.md
```

Input CSV:

| srcid | src_num | obs_id |
|-------|---------|---------|
| 201237001010017 | 36 | 147510901 |
| 201237001010017 | 39 | 147511701 |
| 201237001010017 | 94 | 147511101 |
| 201237001015028 | 9 | 147511301 |
| 201237001015028 | 11 | 147511201 |
| 201237001015028 | 12 | 147511101 |


### Result file structure

```bash
base_dir/
└── srcid/
    └── obs_id_src_num/
        └── PPS/
            └── PN/
                ├── spectrum.FTZ
                ├── image.PNG
                └── report.PDF
```

### TODO

- Check why .rmf files are missing for some observations