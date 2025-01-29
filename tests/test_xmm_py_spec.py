import pytest
from xmm_py_spec.utils import load_source_list


def test_load_source_list(csv_path):
    sources = load_source_list(csv_path)
    assert len(sources) == 1
    assert sources[0]['obs_id'] == '147510801'
    assert sources[0]['src_num'] == '9'


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_source_list("nonexistent.csv")


def test_invalid_csv(invalid_csv_path):
    with pytest.raises(ValueError):
        load_source_list(invalid_csv_path)
