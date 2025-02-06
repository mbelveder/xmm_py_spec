"""
XMM-Newton Science Archive Data Download Module (Astroquery-based)

Downloads and organizes spectral data using astroquery's XMMNewton interface.
"""

from astroquery.esa.xmm_newton import XMMNewton
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import shutil
from .utils import load_source_list
import argparse

from functools import wraps
import time
from urllib.error import URLError
from http.client import RemoteDisconnected
from requests.exceptions import ConnectionError
import random
import tarfile
import pandas as pd
import json

LEVEL = "PPS"
INSTNAME = "PN"

# Network-related errors that should trigger retry logic
NETWORK_ERRORS = (
    ConnectionResetError,
    RemoteDisconnected,
    URLError,
    ConnectionError
)


def get_source_dir(base_dir: str, srcid: str, obs_data: Dict) -> Path:
    """Generate source directory path based on srcid and optional user_srcid."""
    if 'user_srcid' in obs_data and obs_data['user_srcid']:
        return Path(base_dir) / f"{srcid}_{obs_data['user_srcid']}"
    return Path(base_dir) / str(srcid)


def log_download_status(
    srcid: str, obs_id: str, src_num: str, base_dir: str, status: str,
    obs_data: Dict = None
) -> None:
    """Log download attempt status to a human-readable text file."""
    obs_data = obs_data or {}
    log_dir = get_source_dir(base_dir, srcid, obs_data)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "download.log"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"[{timestamp}] obs_id {obs_id} src_num {src_num}: {status}\n"

    with open(log_file, 'a') as f:
        f.write(message)


def clear_log_file(srcid: str, base_dir: str, obs_data: Dict = None) -> None:
    """Clear existing log file for a new download session."""
    obs_data = obs_data or {}
    log_dir = get_source_dir(base_dir, srcid, obs_data)
    log_file = log_dir / "download.log"
    if log_file.exists():
        log_file.write_text('')


def prepare_download(
        srcid: str, obs_id: str, src_num: int, base_dir: str,
        obs_data: Dict = None
) -> tuple[Path, str]:
    """Prepare download paths and normalize observation ID."""
    if len(obs_id) < 10:
        obs_id = f'{int(obs_id):010d}'
    source_dir = get_source_dir(base_dir, srcid, obs_data or {})
    output_dir = source_dir / f"{obs_id}_{src_num}"
    return output_dir, obs_id


def calculate_delay(attempt: int, initial_delay: float) -> float:
    """Calculate retry delay with exponential backoff and jitter."""
    # Add randomness to prevent thundering herd problem
    base_delay = initial_delay * (2 ** attempt)
    return base_delay + random.uniform(0, 0.1 * base_delay)


def handle_retry(
        attempt: int, max_retries: int, error: Exception, delay: float
) -> None:
    """Handle retry attempt logging and delay."""
    if attempt == max_retries - 1:
        raise error
    print(f"Attempt {attempt + 1}/{max_retries} failed: {error}")
    print(f"Retrying in {delay:.1f}s...")
    time.sleep(delay)


def retry_on_network_error(max_retries=3, initial_delay=1):
    """Retry function execution on network errors with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except NETWORK_ERRORS as e:
                    delay = calculate_delay(attempt, initial_delay)
                    handle_retry(attempt, max_retries, e, delay)
        return wrapper
    return decorator


@retry_on_network_error()
def download_xmm_data(obs_id: str, src_num: int) -> Path:
    """Download XMM data using astroquery."""
    tar_file = Path(f'{obs_id}.tar')
    XMMNewton.download_data(
        obs_id,
        level=LEVEL,
        extension="FTZ,PNG,PDF",
        instname=INSTNAME,
        sourceno=f'{src_num:04X}',
        filename=obs_id
    )
    return tar_file


def organize_files(output_dir: Path) -> None:
    """Move downloaded files to their final location."""
    for ext in ['.FTZ', '.PNG', '.PDF']:
        for file in Path('.').glob(f'*{ext}'):
            target = output_dir / file.name
            if not target.exists():
                shutil.move(str(file), str(target))


def reorganize_extracted_files(base_path: Path, obs_id: str) -> None:
    """
    Reorganize files from astroquery's structure into our desired structure.

    Moves files from:
        base_path/{obs_id}/pps/*
    To:
        base_path/{LEVEL}/{INSTNAME}/*
    """
    # Source directory (astroquery's structure)
    source_dir = base_path / obs_id / "pps"
    if not source_dir.exists():
        return

    # Target directory (our desired structure)
    target_dir = base_path / LEVEL / INSTNAME
    target_dir.mkdir(parents=True, exist_ok=True)

    # Move all files
    for file_path in source_dir.glob('*'):
        target_path = target_dir / file_path.name
        shutil.move(str(file_path), str(target_path))

    # Cleanup original directory structure
    shutil.rmtree(base_path / obs_id)


def is_directory_empty(path: Path) -> bool:
    """Check if directory is empty."""
    return not any(path.iterdir())


def extract_all_files(tar_file: Path, output_dir: Path) -> None:
    """Extract all files from tarfile to output directory."""
    extentions = ['.FTZ', '.PNG', '.PDF']
    with tarfile.open(tar_file, 'r') as tar:
        for member in tar.getmembers():
            if any(member.name.endswith(ext) for ext in extentions):
                tar.extract(member, output_dir)


def update_meta_log(obs_data: Dict, status: str, base_dir: str) -> None:
    """Update the meta log file with observation status."""
    meta_log_path = Path(base_dir) / "download_meta.csv"

    # Prepare log entry
    log_entry = {
        'srcid': obs_data['srcid'],
        'obs_id': obs_data['obs_id'],
        'src_num': obs_data['src_num'],
        'user_srcid': obs_data.get('user_srcid', ''),
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'details': json.dumps(obs_data)  # Store full observation data
    }

    try:
        # Load existing log or create new
        if meta_log_path.exists():
            df = pd.read_csv(meta_log_path)
            # Update existing entry or append new one
            mask = (df['srcid'] == obs_data['srcid']) & \
                   (df['obs_id'] == obs_data['obs_id']) & \
                   (df['src_num'] == obs_data['src_num'])
            if mask.any():
                df.loc[mask, ['status', 'timestamp']] = [
                    status, log_entry['timestamp']
                ]
            else:
                df = pd.concat(
                    [df, pd.DataFrame([log_entry])], ignore_index=True
                )
        else:
            df = pd.DataFrame([log_entry])

        # Save updated log
        df.to_csv(meta_log_path, index=False)
    except Exception as e:
        print(f"Warning: Failed to update meta log: {e}")


def download_observation(
    srcid: str, obs_id: str, src_num: int, base_dir: str, obs_data: Dict = None
) -> bool:
    """Download and organize data for a single XMM-Newton observation."""

    obs_data = obs_data or {
        'srcid': srcid, 'obs_id': obs_id, 'src_num': src_num
    }

    output_dir, obs_id = prepare_download(
        srcid, obs_id, src_num, base_dir, obs_data
    )

    if output_dir.exists():
        # Only skip if directory has content, retry if empty
        if not is_directory_empty(output_dir):
            update_meta_log(obs_data, "SKIPPED_EXISTS", base_dir)
            log_download_status(
                srcid, obs_id, src_num, base_dir, "SKIPPED_EXISTS", obs_data
            )
            print(
                f"Skipping {obs_id}_{src_num} - directory exists with files\n"
            )
            return True
        else:
            log_download_status(
                srcid, obs_id, src_num, base_dir, "RETRY_EMPTY_DIR", obs_data
            )
            print(f"Retrying {obs_id}_{src_num} - directory exists but empty\n")

    try:
        tar_file = download_xmm_data(obs_id, src_num)
        output_dir.mkdir(parents=True, exist_ok=True)

        # First extract spectral files using XMMNewton utility
        XMMNewton.get_epic_spectra(
            tar_file, source_number=src_num, verbose=False, path=output_dir
        )
        print('\n')

        # Then extract remaining files
        extract_all_files(tar_file, output_dir)

        reorganize_extracted_files(output_dir, obs_id)

        tar_file.unlink(missing_ok=True)
        update_meta_log(obs_data, "SUCCESS", base_dir)
        log_download_status(
            srcid, obs_id, src_num, base_dir, "SUCCESS", obs_data
        )
        return True

    except Exception as e:
        error_msg = str(e)
        update_meta_log(obs_data, f"ERROR: {error_msg}", base_dir)
        log_download_status(
            srcid, obs_id, src_num, base_dir, f"ERROR: {error_msg}", obs_data
        )
        print(f"Error processing {obs_id}_{src_num}: {error_msg}\n")
        return False


def process_downloads(obs_table: List[Dict], base_dir: str) -> None:
    """Process all downloads from the observation table."""
    for obs in obs_table:
        download_observation(
            obs['srcid'],
            obs['obs_id'],
            int(obs['src_num']),
            base_dir,
            obs
        )


def validate_obs_table(obs_table: List[Dict]) -> None:
    """Validate observation table contents."""
    if not obs_table:
        raise ValueError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise ValueError(f"Missing required fields: {required_fields}")


def download_spectra(
    obs_table: List[Dict], base_dir: str = "data/downloaded_spectra"
) -> None:
    """Download spectral data for multiple XMM-Newton observations."""
    validate_obs_table(obs_table)

    # Create base directory if it doesn't exist
    Path(base_dir).mkdir(parents=True, exist_ok=True)

    # Initialize meta log if needed
    meta_log_path = Path(base_dir) / "download_meta.csv"
    if not meta_log_path.exists():
        pd.DataFrame(columns=[
            'srcid', 'obs_id', 'src_num', 'user_srcid',
            'status', 'timestamp', 'details'
        ]).to_csv(meta_log_path, index=False)

    # Clear logs for each unique source/user combination
    seen_sources = set()
    for obs in obs_table:
        source_key = (obs['srcid'], obs.get('user_srcid'))
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            clear_log_file(obs['srcid'], base_dir, obs)

    try:
        process_downloads(obs_table, base_dir)
    except Exception as e:
        print(f"Download failed: {str(e)}")
        raise


def main():
    """Command-line interface for XMM-Newton data downloads."""
    parser = argparse.ArgumentParser(
        description="Download XMM-Newton spectra using astroquery."
    )
    parser.add_argument(
        'csv_path', help="Path to CSV file with observation data"
    )
    parser.add_argument(
        '--base-dir',
        default="data/downloaded_spectra",
        help="Base directory for downloads (default: data/downloaded_spectra)")

    args = parser.parse_args()

    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download using astroquery...\n")
        download_spectra(obs_table, base_dir=args.base_dir)
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()
