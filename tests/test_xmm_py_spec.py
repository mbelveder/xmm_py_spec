import pytest
from pathlib import Path
from xmm_py_spec.utils import load_source_list
import requests
from xmm_py_spec.download import (
    make_url,
    files_exist,
    download_spectra,
    process_tar_file,
    download_file
)


# Test proper loading of source list from valid CSV file
def test_load_source_list(csv_path):
    sources = load_source_list(csv_path)
    assert len(sources) == 1
    assert sources[0]['obs_id'] == '147510801'
    assert sources[0]['src_num'] == '9'


# Test handling of non-existent input file
def test_missing_file():
    with pytest.raises(FileNotFoundError):
        load_source_list("nonexistent.csv")


# Test handling of malformed CSV file
def test_invalid_csv(invalid_csv_path):
    with pytest.raises(ValueError):
        load_source_list(invalid_csv_path)


# Test URL generation with valid input parameters
def test_make_url_valid():
    url = make_url('123456', '9')
    assert '0000123456' in url
    assert '0009' in url
    assert 'FTZ' in url and 'PNG' in url and 'PDF' in url


# Test URL generation with invalid input parameters
def test_make_url_invalid():
    with pytest.raises(ValueError):
        make_url('', '9')
    with pytest.raises(ValueError):
        make_url('123', '')


# Test file existence checking functionality
def test_files_exist(temp_dir_with_files):
    assert files_exist(temp_dir_with_files)
    assert not files_exist(Path('/nonexistent'))


# Test handling of empty observation table
def test_download_spectra_empty_table():
    with pytest.raises(ValueError, match="Empty observation"):
        download_spectra([])


# Test handling of observation table with missing required fields
def test_download_spectra_missing_fields():
    bad_table = [{'obs_id': '123'}]
    with pytest.raises(ValueError, match="missing required fields"):
        download_spectra(bad_table)


def test_process_tar_file(tmp_path, sample_tar_bytes):
    tar_path = tmp_path / "test.tar"
    tar_path.write_bytes(sample_tar_bytes)

    dest_dir = tmp_path / "output"
    dest_dir.mkdir()

    process_tar_file(str(tar_path), dest_dir)
    assert (dest_dir / "test.FTZ").exists()


def test_process_tar_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        process_tar_file("/nonexistent.tar", tmp_path)


def test_download_file_success(tmp_path, mock_requests_get):
    result = download_file(
        url="http://test.com",
        srcid="123",
        obs_id="456",
        src_num="7",
        base_dir=str(tmp_path)
    )
    assert result is True
    assert mock_requests_get.called


def test_download_file_network_error(tmp_path, mocker):
    mocker.patch('requests.get', side_effect=requests.RequestException)
    result = download_file(
        url="http://test.com",
        srcid="123",
        obs_id="456",
        src_num="7",
        base_dir=str(tmp_path)
    )
    assert result is False