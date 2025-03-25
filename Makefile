# Define a variable for source_id that can be overridden
# SOURCE_ID ?= $(SOURCE_ID)

install:
		poetry install

download_spectra:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_sources_lh.csv

download_spectra_full_list:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_lh_full.csv

download_all_instruments:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_sources_lh.csv --instruments PN M1 M2

download_m1_m2:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_lh_Ms.csv --instruments M1 M2

combine_spectra:
		poetry run python -m xmm_py_spec.combine_spectra

combine_spectra_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2

combine_spectra_m1_m2:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2

combine_spectra_group:
		poetry run python -m xmm_py_spec.combine_spectra --group

combine_spectra_group_pn:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN --group --method EPICSPECCOMBINE

combine_spectra_group_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2 --group

combine_spectra_group_m1_m2:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2 --group

analyze_grouped_spectra:
		poetry run python -m xmm_py_spec.analyze_spectra

analyze_grouped_spectra_5359:
		poetry run python -m xmm_py_spec.analyze_spectra --source $(SOURCE_ID)

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

fit_clustered_observations_all:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN M1 M2 --type clustered

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

cluster_and_combine_spectra_pn:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument PN --group

cluster_and_combine_spectra_m1:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M1 --group

cluster_and_combine_spectra_m2:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument M2 --group

cluster_and_combine_spectra_mos:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument MOS --group

cluster_and_combine_spectra_pn_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument PN --group --method ADDSPEC

cluster_and_combine_spectra_mos_addspec:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra $(SOURCE_ID) --instrument MOS --group --method ADDSPEC

publish:
		poetry publish --dry-run

package-install:
		python3 -m pip install --user dist/*.whl

package-force-reinstall:
		python3 -m pip install --user --force-reinstall dist/*.whl

test:
		poetry run pytest

test-verbose:
		poetry run pytest -vv

pytest-cov:
		poetry run pytest --cov=src/xmm_py_spec

test-coverage:
		poetry run pytest --cov=src/xmm_py_spec --cov-report xml

test-missed:
		poetry run pytest --cov=src/xmm_py_spec --cov-report term-missing --cov-report html

lint:
		poetry run flake8 src/xmm_py_spec

selfcheck:
		poetry check

check: selfcheck test lint

build: check
		poetry build