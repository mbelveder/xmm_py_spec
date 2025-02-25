import pytest
from pathlib import Path
from xmm_py_spec.utils import load_source_list
from xmm_py_spec.download_spectra import (
    download_spectra,
    clear_log_file,
    validate_download_files, get_source_dir, validate_obs_table,
    reorganize_extracted_files, calculate_delay, update_meta_log
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


# Test handling of empty observation table
def test_download_spectra_empty_table():
    with pytest.raises(ValueError, match="Empty observation"):
        download_spectra([])


# # Test handling of observation table with missing required fields
# def test_download_spectra_missing_fields():
#     bad_table = [{'obs_id': '123'}]
#     with pytest.raises(ValueError, match="missing required fields"):
#         download_spectra(bad_table)


# def test_clear_log_file(tmp_path):
#     """Test log file clearing functionality."""
#     log_dir = tmp_path / "123"
#     log_dir.mkdir()
#     log_file = log_dir / "download.log"

#     # Create log with content
#     log_file.write_text("old content")

#     clear_log_file("123", tmp_path)
#     assert log_file.read_text() == ""


def test_clear_nonexistent_log(tmp_path):
    """Test clearing non-existent log file."""
    clear_log_file("456", tmp_path)  # Should not raise any error


# def test_download_spectra_clears_logs(tmp_path):
#     """Test that download_spectra clears existing logs."""
#     # Create existing log
#     log_dir = tmp_path / "123"
#     log_dir.mkdir(parents=True)
#     log_file = log_dir / "download.log"
#     log_file.write_text("old content")

#     obs_table = [{'srcid': '123', 'obs_id': '456', 'src_num': '7'}]
#     download_spectra(obs_table, base_dir=str(tmp_path))

#     assert log_file.exists()
#     assert "old content" not in log_file.read_text()


def test_download_spectra_logs_append(tmp_path):
    """Test that download_spectra properly appends to logs."""
    # Create existing log
    log_dir = tmp_path / "123"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "download.log"
    log_file.write_text("old content\n")

    obs_table = [{'srcid': '123', 'obs_id': '456', 'src_num': '7'}]
    download_spectra(obs_table, base_dir=str(tmp_path))

    log_content = log_file.read_text()
    assert log_file.exists()
    assert "old content" in log_content
    assert "456" in log_content  # New download info should be present


def test_validate_download_files(tmp_path):
    """Test file validation with missing and complete sets."""
    # Create test files
    test_dir = tmp_path / "test_spectra"
    test_dir.mkdir()
    (test_dir / "test_SRSPEC.FTZ").touch()
    (test_dir / "test_BGSPEC.FTZ").touch()
    (test_dir / "test_SRCARF.FTZ").touch()
    (test_dir / "test.rmf").touch()

    # Test complete set
    validation = validate_download_files(test_dir)
    assert all(validation.values())

    # Test missing file
    (test_dir / "test.rmf").unlink()
    validation = validate_download_files(test_dir)
    assert not validation['rmf']
    assert validation['spectrum']


def test_get_source_dir():
    """Test source directory path generation."""
    base_dir = "test_data"
    srcid = "123456"

    # Test without user_srcid
    path = get_source_dir(base_dir, srcid, {})
    assert path == Path("test_data/123456")

    # Test with user_srcid
    path = get_source_dir(base_dir, srcid, {'user_srcid': '789'})
    assert path == Path("test_data/123456_789")


def test_validate_obs_table():
    """Test observation table validation."""
    valid_table = [{'obs_id': '1', 'src_num': '1', 'srcid': '1'}]
    validate_obs_table(valid_table)  # Should not raise

    with pytest.raises(ValueError, match="Empty observation table"):
        validate_obs_table([])

    with pytest.raises(ValueError, match="Missing required fields"):
        validate_obs_table([{'obs_id': '1'}])


def test_calculate_delay():
    """Test retry delay calculation."""
    initial_delay = 1.0

    # Test exponential backoff
    assert 1.0 <= calculate_delay(0, initial_delay) <= 1.1
    assert 2.0 <= calculate_delay(1, initial_delay) <= 2.2
    assert 4.0 <= calculate_delay(2, initial_delay) <= 4.4


@pytest.fixture
def mock_obs_data():
    return {
        'srcid': 'test123',
        'obs_id': 'obs456',
        'src_num': '1',
        'user_srcid': 'user789'
    }


def test_meta_logging(tmp_path, mock_obs_data):
    """Test meta logging functionality."""
    base_dir = tmp_path
    status = "SUCCESS"

    # Test initial log creation
    update_meta_log(mock_obs_data, status, base_dir)

    log_path = base_dir / "download_meta.log"
    csv_path = base_dir / "download_meta.csv"

    assert log_path.exists()
    assert csv_path.exists()

    # Verify CSV content
    import pandas as pd
    df = pd.read_csv(csv_path)
    assert len(df) == 1
    assert df.iloc[0]['status'] == status
    assert df.iloc[0]['srcid'] == mock_obs_data['srcid']


def test_reorganize_extracted_files(tmp_path):
    """Test file reorganization with cleanup."""
    base_path = tmp_path
    obs_id = "test_obs"

    # Create test structure
    pps_dir = base_path / obs_id / "pps"
    pps_dir.mkdir(parents=True)
    test_file = pps_dir / "test.FTZ"
    test_file.touch()

    # Test with cleanup
    reorganize_extracted_files(base_path, obs_id, cleanup=True)
    assert not (base_path / obs_id).exists()
    assert (base_path / "PPS" / "PN" / "test.FTZ").exists()

    # Test without cleanup
    pps_dir.mkdir(parents=True)
    test_file = pps_dir / "test2.FTZ"
    test_file.touch()

    reorganize_extracted_files(base_path, obs_id, cleanup=False)
    assert (base_path / obs_id).exists()
    assert (base_path / "PPS" / "PN" / "test2.FTZ").exists()
