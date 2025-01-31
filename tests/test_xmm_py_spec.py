import pytest
from pathlib import Path
from xmm_py_spec.utils import load_source_list
# from astropy.io import fits
from xmm_py_spec.download_spectra import (
    make_url,
    files_exist,
    download_spectra,
    clear_log_file
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


def test_clear_log_file(tmp_path):
    """Test log file clearing functionality."""
    log_dir = tmp_path / "123"
    log_dir.mkdir()
    log_file = log_dir / "download.log"

    # Create log with content
    log_file.write_text("old content")

    clear_log_file("123", tmp_path)
    assert log_file.read_text() == ""


def test_clear_nonexistent_log(tmp_path):
    """Test clearing non-existent log file."""
    clear_log_file("456", tmp_path)  # Should not raise any error


def test_download_spectra_clears_logs(tmp_path):
    """Test that download_spectra clears existing logs."""
    # Create existing log
    log_dir = tmp_path / "123"
    log_dir.mkdir(parents=True)
    log_file = log_dir / "download.log"
    log_file.write_text("old content")

    obs_table = [{'srcid': '123', 'obs_id': '456', 'src_num': '7'}]
    download_spectra(obs_table, base_dir=str(tmp_path))

    assert log_file.exists()
    assert "old content" not in log_file.read_text()


# def test_read_fits_header_field(tmp_path):
#     # Create test FITS file
#     test_file = tmp_path / "test.fits"
#     # Primary HDU
#     primary_hdu = fits.PrimaryHDU()
#     primary_hdu.header['TELESCOP'] = 'XMM'

#     # Extension HDU
#     ext_hdu = fits.ImageHDU()
#     ext_hdu.header['RESPFILE'] = 'epn_e1_ff20_sdY8.rmf'

#     # Create HDUList and write to file
#     hdul = fits.HDUList([primary_hdu, ext_hdu])
#     hdul.writeto(test_file)

#     # Test reading existing field
#     assert read_fits_header_field(
#         test_file, 'RESPFILE') == 'epn_e1_ff20_sdY8.rmf'

#     # Test reading non-existent field
#     with pytest.raises(KeyError):
#         read_fits_header_field(test_file, 'NONEXISTENT')

#     # Test reading from non-existent file
#     with pytest.raises(FileNotFoundError):
#         read_fits_header_field(tmp_path / "nonexistent.fits", 'RESPFILE')