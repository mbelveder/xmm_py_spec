
# TODO: add overall progress bar
# TODO: don't try to untar if the download failed
# TODO: create a report after all downloads are finished
# TODO: explore ODF downloading options
# TODO: rerid all docs before publishing

"""
XMM-Newton Science Archive Data Download Module

This module provides functionality to download spectral data from the XMM-Newton
Science Archive (XSA). It handles the following tasks:
- URL construction for XSA data access
- Download of spectral data files (FTZ, PNG, PDF)
- Extraction of Pipeline Processing System (PPS) files
- Organization of downloaded files into a structured directory hierarchy

Usage:
    from xmm_py_spec.download_spectra import download_spectra

    obs_table = [
        {'srcid': '123', 'obs_id': '456', 'src_num': '7'}
    ]
    download_spectra(obs_table)
"""

import argparse
import tarfile
import tempfile
import shutil
import requests
from tqdm import tqdm
from pathlib import Path
from typing import Dict, List
from astropy.io import fits
from .utils import load_source_list

BASE_URL = "https://nxsa.esac.esa.int/nxsa-sl/servlet/data-action-aio"
TIMEOUT = 30  # seconds
CHUNK_SIZE = 8192  # optimal chunk size for downloads


def make_url(obs_id: str, src_num: str) -> str:
    """
    Create a URL for downloading XMM-Newton spectral data.

    Args:
        obs_id: Observation ID from XMM-Newton archive
        src_num: Source number within the observation

    Returns:
        str: Complete URL for downloading the data products

    Raises:
        ValueError: If obs_id or src_num is empty
    """
    if not obs_id or not src_num:
        raise ValueError("obs_id and src_num must not be empty")

    extensions = ["FTZ", "PNG", "PDF"]

    # Transform values for the URL creation
    # URL needs obs_id to be a 10-digit number
    obs_id_padded = f"{int(obs_id):010d}"
    # src_num needs to be in a hexadecimal format
    src_num_hex = format(int(src_num), '04X')

    # Construct the combined URL based on transformed values
    combined_url = (
        f"{BASE_URL}?obsno={obs_id_padded}&sourceno={src_num_hex}&"
        f"level=PPS&extension={','.join(extensions)}"
    )

    return combined_url


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


def process_tar_file(tar_path, dest_dir):
    """
    Extract PPS files from downloaded tar archive.

    Args:
        tar_path: Path to the downloaded tar file
        dest_dir: Directory where files should be extracted

    Raises:
        FileNotFoundError: If tar file is missing
        RuntimeError: If PPS directory is not found after extraction
    """
    with tarfile.open(tar_path) as tar:
        # Get all members that contain 'pps' directory
        pps_files = [m for m in tar.getmembers() if 'pps' in m.name]
        tar.extractall(path=dest_dir, members=pps_files)

    # Move files from pps subdirectory to destination
    pps_dir = next(Path(dest_dir).glob('*/pps'))
    for file_path in pps_dir.glob('*'):
        shutil.move(str(file_path), dest_dir)

    # Cleanup temporary extraction directory
    shutil.rmtree(next(Path(dest_dir).glob('*[0-9]')))


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
    output_dir = Path(base_dir) / str(srcid) / f"{obs_id}_{src_num}"

    if output_dir.exists() and files_exist(output_dir):
        print(f"Skipping {obs_id}_{src_num} - files already exist")
        return True

    try:
        with tempfile.NamedTemporaryFile(suffix='.tar') as tmp_file:
            response = requests.get(url, stream=True, timeout=TIMEOUT)
            response.raise_for_status()

            total = int(response.headers.get('content-length', 0))
            desc = f"Downloading {obs_id}_{src_num}"

            with tqdm(
                desc=desc, total=total, unit='iB', unit_scale=True
            ) as pbar:
                for data in response.iter_content(chunk_size=CHUNK_SIZE):
                    size = tmp_file.write(data)
                    pbar.update(size)
            tmp_file.flush()  # Ensure all data is written

            # Create directory structure
            output_dir.mkdir(parents=True, exist_ok=True)

            # Process tar file
            process_tar_file(tmp_file.name, output_dir)

        return True
    except requests.RequestException as e:
        print(f"Network error for {obs_id}_{src_num}: {str(e)}")
        return False
    except Exception as e:
        print(f"Error processing {obs_id}_{src_num}: {str(e)}")
        return False


def download_spectra(
        obs_table: List[Dict], base_dir: str = "data/downloaded_spectra"
) -> None:
    """
    Download spectral data for multiple XMM-Newton observations.

    Args:
        obs_table: List of dictionaries containing observation details.
                  Each dictionary must have 'obs_id', 'src_num',
                  and 'srcid' keys.
        base_dir: Base directory for storing downloaded files

    Raises:
        ValueError: If obs_table is empty or missing required fields

    Example:
        obs_table = [
            {
                'srcid': '201237001010017',
                'obs_id': '147510801',
                'src_num': '9'
            }
        ]
        download_spectra(obs_table)
    """
    if not obs_table:
        raise ValueError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise ValueError(
            f"Observation table missing required fields: {required_fields}"
        )

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


def read_fits_header_field(filepath, field_name):
    with fits.open(filepath) as hdul:
        # Get header info
        header = hdul[1].header

    return header[field_name]


def main():
    """
    Command-line entry point for the download functionality.

    Reads source list from CSV file and initiates download of spectral data.
    CSV must contain columns: srcid, obs_id, src_num
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
