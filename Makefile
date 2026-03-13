# ============================================================
# XMM-Newton Spectra Pipeline
# ============================================================
# Required variables (pass on the command line):
#   OBS_LIST      - CSV filename inside data/spectra_to_download/
#   DOWNLOAD_PATH - destination directory for downloaded products
#   SOURCE_ID     - srcid_user_srcid for per-source targets
#
# Example:
#   make download_PPS_PN OBS_LIST=sources.csv DOWNLOAD_PATH=data/spectra
# ============================================================

# ---- Setup --------------------------------------------------

install:
		poetry install

# ---- Download -----------------------------------------------
# Download PPS spectral products for PN only (default instrument)
download_PPS_PN:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/$(OBS_LIST) --download-path $(DOWNLOAD_PATH)

# Download PPS spectral products for all three EPIC instruments (PN, MOS1, MOS2)
download_all_instruments:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/$(OBS_LIST) --download-path $(DOWNLOAD_PATH) --instruments PN M1 M2

# Download raw Observation Data Files (ODF tarballs, no extraction)
download_ODF:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/$(OBS_LIST) --download-path $(DOWNLOAD_PATH) --level ODF

# Download PPS spectral products for MOS1 and MOS2 only
download_m1_m2:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/$(OBS_LIST) --instruments M1 M2

# ---- Combine spectra ----------------------------------------
# Combine PN spectra from multiple observations using EPICSPECCOMBINE (default)
combine_spectra:
		poetry run python -m xmm_py_spec.combine_spectra

# Combine PN spectra using ADDSPEC (no time-gap grouping)
combine_spectra_pn_addspec:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN --method ADDSPEC --gap-threshold none

# Combine all instruments using ADDSPEC (no time-gap grouping) with grouping
combine_spectra_addspec_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2 --method ADDSPEC --gap-threshold none  --group

# Combine all instruments using EPICSPECCOMBINE
combine_spectra_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2

# Combine MOS1 and MOS2 spectra using EPICSPECCOMBINE
combine_spectra_m1_m2:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2

# Combine PN spectra with spectral grouping (EPICSPECCOMBINE)
combine_spectra_group:
		poetry run python -m xmm_py_spec.combine_spectra --group

# Combine and group PN spectra using EPICSPECCOMBINE
combine_spectra_group_pn:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN --group --method EPICSPECCOMBINE

# Combine and group all instruments using EPICSPECCOMBINE
combine_spectra_group_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2 --group

# Combine and group MOS1 and MOS2 using EPICSPECCOMBINE
combine_spectra_group_m1_m2:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2 --group

# ---- Cluster and combine ------------------------------------
# Cluster observations by time then combine with grouping; requires SOURCE_ID
cluster_and_combine_spectra_pn:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument PN --group

cluster_and_combine_spectra_m1:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M1 --group

cluster_and_combine_spectra_m2:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M2 --group

# Cluster and combine MOS1+MOS2 as a joint MOS spectrum
cluster_and_combine_spectra_mos:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument MOS --group

# ADDSPEC variants of cluster-and-combine
cluster_and_combine_spectra_pn_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument PN --group --method ADDSPEC

cluster_and_combine_spectra_m1_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M1 --group --method ADDSPEC

cluster_and_combine_spectra_m2_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M2 --group --method ADDSPEC

cluster_and_combine_spectra_mos_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument MOS --group --method ADDSPEC

# ---- Fit observations ---------------------------------------
# Fit individual (non-clustered) spectra per instrument
fit_observations_pn:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN

fit_observations_m1_m2:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1 M2

fit_observations_m1:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1

fit_observations_m2:
		poetry run python -m xmm_py_spec.fit_observations --instruments M2

fit_observations_all:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN M1 M2

# Fit time-clustered combined spectra
fit_clustered_observations_all:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN M1 M2 MOS --type clustered

fit_clustered_observations_pn:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN --type clustered

fit_clustered_observations_m1_m2:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1 M2 --type clustered

fit_clustered_observations_m1:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1 --type clustered

fit_clustered_observations_m2:
		poetry run python -m xmm_py_spec.fit_observations --instruments M2 --type clustered

fit_clustered_observations_mos:
		poetry run python -m xmm_py_spec.fit_observations --instruments MOS --type clustered

# ADDSPEC variants of clustered fitting
fit_clustered_observations_all_addspec:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN M1 M2 MOS --type clustered --method addspec

fit_clustered_observations_pn_addspec:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN --type clustered --method addspec

fit_clustered_observations_m1_m2_addspec:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1 M2 --type clustered --method addspec

fit_clustered_observations_mos_addspec:
		poetry run python -m xmm_py_spec.fit_observations --instruments MOS --type clustered --method addspec

# ---- Analyze ------------------------------------------------
# Analyze all grouped spectra
analyze_grouped_spectra:
		poetry run python -m xmm_py_spec.analyze_spectra

# Analyze spectra for a specific source (requires SOURCE_ID)
analyze_grouped_spectra_5359:
		poetry run python -m xmm_py_spec.analyze_spectra --source $(SOURCE_ID)

# ---- Package ------------------------------------------------

publish:
		poetry publish --dry-run

package-install:
		python3 -m pip install --user dist/*.whl

package-force-reinstall:
		python3 -m pip install --user --force-reinstall dist/*.whl

# ---- Quality ------------------------------------------------

test:
		poetry run pytest

test-verbose:
		poetry run pytest -vv

# Generate coverage summary to stdout
pytest-cov:
		poetry run pytest --cov=src/xmm_py_spec

# Generate XML coverage report (for CI)
test-coverage:
		poetry run pytest --cov=src/xmm_py_spec --cov-report xml

# Generate coverage with missing-line detail and HTML report
test-missed:
		poetry run pytest --cov=src/xmm_py_spec --cov-report term-missing --cov-report html

lint:
		poetry run flake8 src/xmm_py_spec

selfcheck:
		poetry check

# Run selfcheck + tests + lint
check: selfcheck test lint

# Run check then build wheel/sdist
build: check
		poetry build
