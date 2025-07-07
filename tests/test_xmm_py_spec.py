import pytest
from pathlib import Path
from xmm_py_spec.utils import load_source_list
from xmm_py_spec.download_spectra import (
    download_spectra,
    clear_log_file,
    get_source_dir,
    reorganize_extracted_files, calculate_delay, update_meta_log,
    validate_instrument, INSTRUMENTS
)

from xmm_py_spec.core.validation import (
    validate_downloaded_files,
    validate_observation_table,
    DataValidationError
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
    with pytest.raises(
        DataValidationError, match="Empty observation table provided"
    ):
        download_spectra([])


def test_clear_nonexistent_log(tmp_path):
    """Test clearing non-existent log file."""
    clear_log_file("456", tmp_path)  # Should not raise any error


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


def test_validate_downloaded_files(tmp_path):
    """Test file validation with missing and complete sets."""
    test_dir = tmp_path / "test_spectra"
    test_dir.mkdir()

    # Use PN instrument-specific file patterns
    (test_dir / "PNS001SRSPEC1000.FTZ").touch()
    (test_dir / "PNS001BGSPEC1000.FTZ").touch()
    (test_dir / "PNS001SRCARF1000.FTZ").touch()
    (test_dir / "pn.rmf").touch()

    # Test complete set with PN instrument
    validation = validate_downloaded_files(test_dir, "PN")
    assert all(validation.values())

    # Test missing file
    (test_dir / "pn.rmf").unlink()
    validation = validate_downloaded_files(test_dir, "PN")
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


def test_validate_observation_table():
    """Test observation table validation."""
    valid_table = [{'obs_id': '1', 'src_num': '1', 'srcid': '1'}]
    validate_observation_table(valid_table)  # Should not raise

    with pytest.raises(
        DataValidationError, match="Empty observation table provided"
    ):
        validate_observation_table([])

    with pytest.raises(DataValidationError, match="Missing required fields"):
        validate_observation_table([{'obs_id': '1'}])


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

    # Create test structure with instrument-specific file
    pps_dir = base_path / obs_id / "pps"
    pps_dir.mkdir(parents=True)
    test_file = pps_dir / "PNS001SRSPEC1000.FTZ"
    test_file.touch()

    # Test with cleanup (with instrument parameter)
    reorganize_extracted_files(base_path, obs_id, instrument="PN", cleanup=True)
    assert not (base_path / obs_id).exists()
    assert (base_path / "PPS" / "PN" / "PNS001SRSPEC1000.FTZ").exists()

    # Test without cleanup (with instrument parameter)
    pps_dir.mkdir(parents=True)
    test_file = pps_dir / "PNS001SRSPEC2000.FTZ"
    test_file.touch()

    reorganize_extracted_files(
        base_path, obs_id, instrument="PN", cleanup=False
    )
    assert (base_path / obs_id).exists()
    assert (base_path / "PPS" / "PN" / "PNS001SRSPEC2000.FTZ").exists()


def test_validate_instrument():
    """Test instrument validation."""
    assert validate_instrument("PN") == "PN"
    assert validate_instrument("pn") == "PN"
    assert validate_instrument("M1") == "M1"
    assert validate_instrument("m2") == "M2"

    with pytest.raises(ValueError, match="Invalid instrument"):
        validate_instrument("invalid")


def test_validate_downloaded_files_with_instrument(tmp_path):
    """Test file validation with different instruments."""
    test_dir = tmp_path / "test_spectra"
    test_dir.mkdir()

    # Test PN files
    (test_dir / "PN_SRSPEC.FTZ").touch()
    (test_dir / "PN_BGSPEC.FTZ").touch()
    (test_dir / "PN_SRCARF.FTZ").touch()
    (test_dir / "pn.rmf").touch()

    validation = validate_downloaded_files(test_dir, "PN")
    assert all(validation.values())

    # Test M1 files
    (test_dir / "M1_SRSPEC.FTZ").touch()
    (test_dir / "M1_BGSPEC.FTZ").touch()
    (test_dir / "M1_SRCARF.FTZ").touch()
    (test_dir / "m1.rmf").touch()

    validation = validate_downloaded_files(test_dir, "M1")
    assert all(validation.values())


def test_reorganize_extracted_files_with_instrument(tmp_path):
    """Test file reorganization for different instruments."""
    base_path = tmp_path
    obs_id = "test_obs"

    for instrument in INSTRUMENTS.keys():
        # Create test structure
        pps_dir = base_path / obs_id / "pps"
        pps_dir.mkdir(parents=True)
        test_file = pps_dir / f"test_{instrument}.FTZ"
        test_file.touch()

        # Test reorganization
        reorganize_extracted_files(base_path, obs_id, instrument=instrument)
        assert (
            base_path / "PPS" / instrument / f"test_{instrument}.FTZ"
        ).exists()
