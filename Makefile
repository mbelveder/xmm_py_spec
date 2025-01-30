install:
		poetry install

download:
		poetry run download

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