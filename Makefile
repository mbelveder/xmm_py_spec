install:
		poetry install

download_spectra:
		poetry run python -m xmm_py_spec.download_spectra data/spectra_to_download/deep_xmm_sources_lh.csv

combine_spectra:
		poetry run python -m xmm_py_spec.combine_spectra

combine_spectra_group:
		poetry run python -m xmm_py_spec.combine_spectra --group

analyze_spectra:
		poetry run python -m xmm_py_spec.analyze_spectra

fit_observation:
		poetry run python -m xmm_py_spec.fit_observation

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