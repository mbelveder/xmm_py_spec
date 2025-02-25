"""
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
import json
import pandas as pd

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
        # Add visual divider before clearing
        with open(log_file, 'a') as f:
            f.write("\n" + "=" * 80 + "\n\n")


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


def reorganize_extracted_files(
        base_path: Path, obs_id: str, cleanup: bool = True
) -> None:
    """
    Copy files from astroquery's structure to our directory structure.
    Optionally preserve original files for debugging.

    Args:
        base_path: Base directory path
        obs_id: Observation ID
        cleanup: Whether to remove source files after copying (default: True)
    """
    source_dir = base_path / obs_id / "pps"
    if not source_dir.exists():
        return

    target_dir = base_path / LEVEL / INSTNAME
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy all files, preserving original structure
    for file_path in source_dir.glob('*'):
        target_path = target_dir / file_path.name
        shutil.copy2(str(file_path), str(target_path))

    # Optionally cleanup source directory
    if cleanup and source_dir.exists():
        shutil.rmtree(source_dir.parent)


def is_directory_empty(path: Path) -> bool:
    """Check if directory is empty."""
    return not any(path.iterdir())


def extract_all_files(tar_file: Path, output_dir: Path) -> None:
    """Extract all files from tarfile to output directory."""
    target_extensions = ['.FTZ', '.PNG', '.PDF']
    with tarfile.open(tar_file, 'r') as tar:
        for member in tar.getmembers():
            if any(member.name.endswith(ext) for ext in target_extensions):
                tar.extract(member, output_dir)


def update_meta_log(obs_data: Dict, status: str, base_dir: str) -> None:
    """Update both CSV and human-readable meta log files."""
    base_path = Path(base_dir)
    csv_path = base_path / "download_meta.csv"
    human_log_path = base_path / "download_meta.log"

    # Prepare log entry
    log_entry = {
        'srcid': obs_data['srcid'],
        'obs_id': obs_data['obs_id'],
        'src_num': obs_data['src_num'],
        'user_srcid': obs_data.get('user_srcid', ''),
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'details': json.dumps(obs_data)
    }

    try:
        # Update CSV log
        if csv_path.exists():
            df = pd.read_csv(csv_path)
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

        df.to_csv(csv_path, index=False)

        # Update human-readable log
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        human_msg = (
            f"[{timestamp}] "
            f"Source: {obs_data['srcid']} "
            f"(User ID: {obs_data.get('user_srcid', 'N/A')}) "
            f"ObsID: {obs_data['obs_id']} "
            f"SrcNum: {obs_data['src_num']} "
            f"Status: {status}\n"
        )

        with open(human_log_path, 'a') as f:
            f.write(human_msg)

    except Exception as e:
        print(f"Warning: Failed to update meta logs: {e}")


def validate_download_files(dir_path: Path) -> Dict[str, bool]:
    """Validate presence of required spectral files.

    Returns:
        Dict with file types and their presence status
    """
    required_patterns = {
        'spectrum': '*SRSPEC*.FTZ',
        'background': '*BGSPEC*.FTZ',
        'arf': '*SRCARF*.FTZ',
        'rmf': '*.rmf'
    }

    validation = {}
    for file_type, pattern in required_patterns.items():
        files = list(dir_path.glob(pattern))
        validation[file_type] = bool(files)

    return validation


def download_observation(
    srcid: str, obs_id: str, src_num: int, base_dir: str,
    obs_data: Dict = None, cleanup: bool = True
) -> bool:
    """Download and organize data for a single XMM-Newton observation."""
    output_dir, obs_id = prepare_download(
        srcid, obs_id, src_num, base_dir, obs_data
    )

    if output_dir.exists():
        # Only skip if directory has content, retry if empty
        if not is_directory_empty(output_dir):
            status = "SKIPPED_EXISTS"
            log_download_status(
                srcid, obs_id, src_num, base_dir, status, obs_data
            )
            update_meta_log(obs_data, status, base_dir)
            print(
                f"Skipping {obs_id}_{src_num} - directory exists with files\n"
            )
            return True
        else:
            status = "RETRY_EMPTY_DIR"
            log_download_status(
                srcid, obs_id, src_num, base_dir, status, obs_data
            )
            update_meta_log(obs_data, status, base_dir)
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

        reorganize_extracted_files(output_dir, obs_id, cleanup=cleanup)

        tar_file.unlink(missing_ok=True)

        # Validate downloaded files
        validation = validate_download_files(output_dir / LEVEL / INSTNAME)
        if all(validation.values()):
            status = "SUCCESS"
        else:
            missing = [k for k, v in validation.items() if not v]
            status = f"INCOMPLETE: Missing {', '.join(missing)}"

        log_download_status(srcid, obs_id, src_num, base_dir, status, obs_data)
        update_meta_log(obs_data, status, base_dir)
        return True

    except Exception as e:
        status = f"ERROR: {str(e)}"
        log_download_status(
            srcid, obs_id, src_num, base_dir, status, obs_data
        )
        update_meta_log(obs_data, status, base_dir)
        print(f"Error processing {obs_id}_{src_num}: {str(e)}\n")
        return False


def process_downloads(
        obs_table: List[Dict], base_dir: str, cleanup: bool = True
) -> None:
    """Process all downloads from the observation table."""
    for obs in obs_table:
        download_observation(
            obs['srcid'],
            obs['obs_id'],
            int(obs['src_num']),
            base_dir,
            obs,
            cleanup=cleanup
        )


def validate_obs_table(obs_table: List[Dict]) -> None:
    """Validate observation table contents."""
    if not obs_table:
        raise ValueError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise ValueError(f"Missing required fields: {required_fields}")


def find_incomplete_downloads(base_path: Path) -> List[str]:
    """Find and return list of incomplete downloads."""
    incomplete = []

    for pps_dir in base_path.glob(f"**/{LEVEL}/{INSTNAME}/"):
        validation = validate_download_files(pps_dir)
        if not all(validation.values()):
            missing = [k for k, v in validation.items() if not v]
            incomplete.append(
                f"{pps_dir.parent.name}: Missing {', '.join(missing)}"
            )

    return incomplete


def log_validation_results(log_path: Path, incomplete_dirs: List[str]) -> None:
    """Log validation results to file."""
    with open(log_path, 'a') as f:
        f.write("\nFinal validation of downloaded files:\n")
        f.write("-" * 40 + "\n")

        if incomplete_dirs:
            f.write("Incomplete downloads found:\n")
            for dir_info in incomplete_dirs:
                f.write(f"- {dir_info}\n")
        else:
            f.write("All downloads complete and validated successfully\n")

        f.write("\nDownload session completed.\n")
        f.write("=" * 80 + "\n")


def validate_all_downloads(base_dir: str) -> None:
    """Double check all downloaded files after session completion."""
    base_path = Path(base_dir)
    incomplete = find_incomplete_downloads(base_path)
    log_validation_results(base_path / "download_meta.log", incomplete)


def download_spectra(
    obs_table: List[Dict],
    base_dir: str = "data/downloaded_spectra",
    cleanup: bool = True
) -> None:
    """Download spectral data for multiple XMM-Newton observations."""
    validate_obs_table(obs_table)

    # Add session divider to human-readable log
    human_log_path = Path(base_dir) / "download_meta.log"
    with open(human_log_path, 'a') as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"Starting new download session at {datetime.now()}\n\n")

    # Clear CSV meta log for new session
    csv_path = Path(base_dir) / "download_meta.csv"
    if csv_path.exists():
        csv_path.unlink()

    # Clear individual logs
    seen_sources = set()
    for obs in obs_table:
        source_key = (obs['srcid'], obs.get('user_srcid'))
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            clear_log_file(obs['srcid'], base_dir, obs)

    try:
        process_downloads(obs_table, base_dir, cleanup=cleanup)
        validate_all_downloads(base_dir)  # Add final validation
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
        default="data/downloaded_spectra/",
        help="Base directory for downloads (default: data/downloaded_spectra)")
    parser.add_argument(
        '--keep-source',
        action='store_true',
        help="Keep original astroquery files (useful for debugging)"
    )

    args = parser.parse_args()

    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download using astroquery...\n")
        download_spectra(
            obs_table,
            base_dir=args.base_dir,
            cleanup=not args.keep_source
        )
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()
