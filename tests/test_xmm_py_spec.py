# TODO: add fixtures

import pytest
from xmm_py_spec.utils import load_source_list


def test_load_source_list(tmp_path):
    csv_content = (
        "obs_id,src_num\n"
        "147510801,9"
    )
    csv_path = tmp_path / "test_sources.csv"
    csv_path.write_text(csv_content)

    sources = load_source_list(csv_path)
    assert len(sources) == 1
    assert sources[0]['obs_id'] == '147510801'
    assert sources[0]['src_num'] == '9'


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_source_list("nonexistent.csv")


def test_invalid_csv(tmp_path):
    bad_csv = "iauname,detid\n4XMM,123"
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(bad_csv)

    with pytest.raises(ValueError):
        load_source_list(csv_path)
