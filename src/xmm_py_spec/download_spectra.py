# TODO: add overall progress bar
# TODO: don't try to untar if the download failed
# TODO: create a report after all downloads are finished
# TODO: explore separate pn/MOS downloading options
# TODO: explore ODF downloading options
# TODO: rerid all docs before publishing

"""
XMM-Newton Science Archive Data Download Module

Downloads and organizes spectral data from the XMM-Newton Science Archive (XSA).

Features:
- Automated download of spectral data products (FITS, PNG, PDF)
- Robust error handling and retry mechanisms
- Maintains original file structure from XSA
- Skips existing downloads
- Logs all operations

Usage:
    from xmm_py_spec.download_spectra import download_spectra

    obs_table = [
        {
            'srcid': '201237001010017',  # Source identifier
            'obs_id': '147510801',       # XMM observation ID
            'src_num': '9'               # Source number in observation
        }
    ]
    download_spectra(obs_table, base_dir='data/spectra')

File Organization:
    base_dir/
    └── srcid/
        ├── obs_id_src_num/
        │   ├── spectrum.FTZ    # FITS format spectral data
        │   ├── image.PNG      # Source image
        │   └── report.PDF     # Data quality report
        └── download.log       # Download status log
"""

import argparse
import tarfile
import tempfile
import shutil
import requests
from tqdm import tqdm
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from .utils import load_source_list
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Network configuration for downloads
NETWORK_CONFIG = {
    'timeout': 30,       # Connection timeout in seconds
    'chunk_size': 8192,  # Download chunk size in bytes
    'max_retries': 3,    # Number of download attempts
    'min_size': 1024     # Minimum valid file size in bytes
}

# XSA URL configuration
URL_CONFIG = {
    'base_fits': "https://nxsa.esac.esa.int/nxsa-sl/servlet/data-action-aio",
    'extensions': ["FTZ", "PNG", "PDF"]  # Required file extensions
}


def setup_requests_session():
    """
    Configure HTTP session with retry mechanism.

    Returns:
        requests.Session: Configured session with retry handler
    """
    session = requests.Session()
    retries = Retry(
        total=NETWORK_CONFIG['max_retries'],
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session


def make_url(obs_id: str, src_num: str) -> str:
    """
    Create XSA download URL for specific observation.

    Args:
        obs_id: XMM-Newton observation ID (will be zero-padded)
        src_num: Source number within observation (will be hex-formatted)

    Returns:
        Complete URL for accessing XSA data products

    Raises:
        ValueError: If obs_id or src_num is empty
    """
    if not obs_id or not src_num:
        raise ValueError("obs_id and src_num must not be empty")

    return (
        f"{URL_CONFIG['base_fits']}?"
        f"obsno={int(obs_id):010d}&"
        f"sourceno={int(src_num):04X}&"
        f"level=PPS&extension={','.join(URL_CONFIG['extensions'])}"
    )


def files_exist(dest_dir: Path) -> bool:
    """
    Check if all required data products exist in the destination directory.

    Args:
        dest_dir: Directory to check for required files

    Returns:
        bool: True if all required files (.FTZ, .PNG, .PDF) exist
    """
    required_extensions = {'.FTZ', '.PNG', '.PDF'}
    existing_files = {f.suffix.upper() for f in dest_dir.glob('*.*')}
    return all(ext in existing_files for ext in required_extensions)


def validate_download(tar_path: str, min_size: int) -> List[tarfile.TarInfo]:
    """
    Validate downloaded tar file and identify PPS files.

    Args:
        tar_path: Path to downloaded tar file
        min_size: Minimum acceptable file size in bytes

    Returns:
        List of TarInfo objects for PPS files, empty list if invalid
    """
    try:
        if Path(tar_path).stat().st_size < min_size:
            return []
        with tarfile.open(tar_path, 'r:*') as tar:  # Auto-detect compression
            pps_files = [m for m in tar.getmembers() if 'pps' in m.name]
            return pps_files if any(
                f.name.endswith('.FTZ') for f in pps_files
            ) else []
    except (tarfile.TarError, IOError):
        return []


def download_tar_file(
        session: requests.Session, url: str, timeout: int, tmp_file
) -> bool:
    """Download tar file to temporary file."""
    try:
        with session.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with tqdm(desc="Progress", unit='iB', unit_scale=True) as pbar:
                for data in response.iter_content(
                    chunk_size=NETWORK_CONFIG['chunk_size']
                ):
                    size = tmp_file.write(data)
                    pbar.update(size)
            tmp_file.flush()
            return True
    except Exception:
        return False


def move_pps_files(pps_dir: Path, output_dir: Path) -> bool:
    """Move files from PPS directory to output directory."""
    try:
        for file_path in pps_dir.glob('*'):
            target_path = output_dir / file_path.name
            if not target_path.exists():
                shutil.move(str(file_path), str(output_dir))
        return True
    except Exception:
        return False


def extract_tar_files(
        tar_path: str, output_dir: Path, pps_files: List[tarfile.TarInfo]
) -> Path:
    """Extract files from tar archive and return PPS directory path."""
    with tarfile.open(tar_path, 'r:*') as tar:
        tar.extractall(path=output_dir, members=pps_files)
    return next(output_dir.glob('*/pps'), None)


def extract_and_organize(
        tar_path: str, output_dir: Path, pps_files: List[tarfile.TarInfo]
) -> bool:
    """
    Extract and organize PPS files from tar archive.

    Args:
        tar_path: Path to tar file
        output_dir: Directory for extracted files
        pps_files: List of PPS files to extract

    Returns:
        True if extraction and organization successful

    Note:
        Creates directory structure and moves files to final location
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        pps_dir = extract_tar_files(tar_path, output_dir, pps_files)

        if not pps_dir or not move_pps_files(pps_dir, output_dir):
            return False

        shutil.rmtree(pps_dir.parent)
        return files_exist(output_dir)
    except Exception:
        return False


def prepare_download(
        srcid: str, obs_id: str, src_num: str, base_dir: str
) -> tuple[Path, bool]:
    """
    Prepare download by checking existing files and creating output directory.
    """
    output_dir = Path(base_dir) / str(srcid) / f"{obs_id}_{src_num}"
    exists = output_dir.exists() and files_exist(output_dir)
    return output_dir, exists


def process_download(
    url: str,
    srcid: str,
    obs_id: str,
    src_num: str,
    output_dir: Path,
    base_dir: str
) -> bool:
    """Process download and extraction of files."""
    session = setup_requests_session()
    with tempfile.NamedTemporaryFile(suffix='.tar', delete=False) as tmp_file:
        tmp_path = tmp_file.name
        if not download_tar_file(
            session, url, NETWORK_CONFIG['timeout'], tmp_file
        ):
            raise requests.RequestException("Download failed")
        print('\n')

    try:
        pps_files = validate_download(tmp_path, NETWORK_CONFIG['min_size'])
        if not pps_files:
            log_download_status(
                srcid, obs_id, src_num, base_dir, "INVALID_CONTENT"
            )
            print(f"Skipping {obs_id}_{src_num} - invalid content\n")
            return False

        success = extract_and_organize(tmp_path, output_dir, pps_files)
        status = "SUCCESS" if success else "EXTRACTION_FAILED"
        log_download_status(srcid, obs_id, src_num, base_dir, status)
        return success
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def download_file(
        url: str, srcid: str, obs_id: str, src_num: str, base_dir: str
) -> bool:
    """
    Download and process data for a single XMM-Newton observation.

    Creates a directory structure: base_dir/srcid/obs_id_src_num/
    Downloads and extracts FTZ (spectral data), PNG (observation images),
    and PDF (spectra plots, rates etc.) files.

    Args:
        url: XSA download URL
        srcid: Source identifier
        obs_id: Observation ID
        src_num: Source number
        base_dir: Base directory for file storage

    Returns:
        bool: True if download and processing successful, False otherwise

    Note:
        Skips download if files already exist in destination directory
    """
    output_dir, exists = prepare_download(srcid, obs_id, src_num, base_dir)

    if exists:
        log_download_status(srcid, obs_id, src_num, base_dir, "SKIPPED_EXISTS")
        print(f"Skipping {obs_id}_{src_num} - files already exist\n")
        return True

    try:
        print(f"URL: {url}")
        return process_download(
            url, srcid, obs_id, src_num, output_dir, base_dir
        )
    except requests.RequestException as e:
        log_download_status(
            srcid, obs_id, src_num, base_dir, f"NETWORK_ERROR: {str(e)}"
        )
        return False
    except Exception as e:
        log_download_status(
            srcid, obs_id, src_num, base_dir, f"ERROR: {str(e)}"
        )
        return False


def log_download_status(
    srcid: str,
    obs_id: str,
    src_num: str,
    base_dir: str,
    status: str
) -> None:
    """Log download attempt status to a human-readable text file."""
    log_dir = Path(base_dir) / str(srcid)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "download.log"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    message = (
        f"[{timestamp}] obs_id {obs_id} src_num {src_num}: {status}\n"
    )

    with open(log_file, 'a') as f:
        f.write(message)


def clear_log_file(srcid: str, base_dir: str) -> None:
    """Clear existing log file for a new download session."""
    log_dir = Path(base_dir) / str(srcid)
    log_file = log_dir / "download.log"
    if log_file.exists():
        log_file.write_text('')


def download_spectra(
        obs_table: List[Dict], base_dir: str = "data/downloaded_spectra"
) -> None:
    """
    Download spectral data for multiple XMM-Newton observations.

    Args:
        obs_table: List of observation details
            Required keys:
            - srcid: Source identifier
            - obs_id: XMM observation ID
            - src_num: Source number in observation
        base_dir: Root directory for downloads

    Raises:
        ValueError: If obs_table is empty or missing required fields

    Note:
        - Creates directory structure: base_dir/srcid/obs_id_src_num/
        - Logs operations to base_dir/srcid/download.log
        - Skips existing downloads
    """
    if not obs_table:
        raise ValueError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise ValueError(
            f"Observation table missing required fields: {required_fields}"
        )

    # Get unique source IDs
    srcids = {obs['srcid'] for obs in obs_table}

    # Clear log files for each source
    for srcid in srcids:
        clear_log_file(srcid, base_dir)

    for obs in obs_table:
        url = make_url(obs['obs_id'], obs['src_num'])
        download_file(
            url,
            obs['srcid'],
            obs['obs_id'],
            obs['src_num'],
            base_dir
        )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Download XMM-Newton spectra data."
    )
    parser.add_argument(
        'csv_path',
        type=str,
        help="Path to the CSV file containing observation data."
    )
    parser.add_argument(
        '--base-dir',
        type=str,
        default="data/downloaded_spectra",
        help=(
            "Base directory for downloaded files"
            "(default: data/downloaded_spectra)"
        )
    )
    return parser.parse_args()


def main():
    """
    Command-line interface for XMM-Newton data downloads.

    Input:
        CSV file with columns: srcid, obs_id, src_num

    Example:
        python -m xmm_py_spec.download_spectra sources.csv --base-dir data/
    """
    args = parse_args()
    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download...\n")
        download_spectra(obs_table, base_dir=args.base_dir)
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()

# def read_fits_header_field(filepath, field_name):
#     with fits.open(filepath) as hdul:
#         # Get header info
#         header = hdul[1].header

#     return header[field_name]
