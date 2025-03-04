install:
		poetry install

download_spectra:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_sources_lh.csv

download_spectra_full_list:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_lh_full.csv

download_all_instruments:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_sources_lh.csv --instruments PN M1 M2

download_mos:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_lh_Ms.csv --instruments M1 M2

combine_spectra:
		poetry run python -m xmm_py_spec.combine_spectra

combine_spectra_all:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2

combine_spectra_mos:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2

combine_spectra_group:
		poetry run python -m xmm_py_spec.combine_spectra --group

combine_spectra_all_group:
		poetry run python -m xmm_py_spec.combine_spectra --instruments PN M1 M2 --group

combine_spectra_mos_group:
		poetry run python -m xmm_py_spec.combine_spectra --instruments M1 M2 --group

analyze_grouped_spectra:
		poetry run python -m xmm_py_spec.analyze_spectra

fit_observations:
		poetry run python -m xmm_py_spec.fit_observations

fit_observations_all:
		poetry run python -m xmm_py_spec.fit_observations --instruments PN M1 M2

fit_observations_mos:
		poetry run python -m xmm_py_spec.fit_observations --instruments M1 M2

cluster_and_combine_spectra:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra 201237001010017_5359 --group

cluster_and_combine_spectra_mos1:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra 201237001010017_5359 --instrument M1 --group

cluster_and_combine_spectra_mos2:
		poetry run python -m xmm_py_spec.cluster_and_combine_spectra 201237001010017_5359 --instrument M2 --group

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