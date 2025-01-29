import pytest


@pytest.fixture
def valid_csv_content():
    return ("obs_id,src_num\n"
            "147510801,9")


@pytest.fixture
def invalid_csv_content():
    return "iauname,detid\n4XMM,123"


@pytest.fixture
def csv_path(tmp_path, valid_csv_content):
    path = tmp_path / "test_sources.csv"
    path.write_text(valid_csv_content)
    return path


@pytest.fixture
def invalid_csv_path(tmp_path, invalid_csv_content):
    path = tmp_path / "bad.csv"
    path.write_text(invalid_csv_content)
    return path
