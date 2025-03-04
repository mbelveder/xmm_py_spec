"""
XMM-Newton Spectral Data Download Module

This module handles the download and organization of XMM-Newton spectral data
using astroquery's XMMNewton interface. It provides functionality to:

1. Download spectral data for multiple observations
2. Organize files into a consistent directory structure
3. Validate downloads and handle network errors
4. Track download status and maintain logs

Directory Structure:
    base_dir/
    └── source_id_[user_id]/
        ├── download.log
        └── obs_id_src_num/
            └── PPS/
                └── PN/
                    ├── *SRSPEC*.FTZ  (source spectrum)
                    ├── *BGSPEC*.FTZ  (background spectrum)
                    ├── *.rmf         (response matrix)
                    └── *SRCARF*.FTZ  (ancillary response)

Required Input Format:
    The observation table must be a list of dictionaries with:
    - 'srcid': Source identifier
    - 'obs_id': XMM-Newton observation ID
    - 'src_num': Source number within observation
    - 'user_srcid' (optional): User-defined source identifier

Usage Examples:

    Basic usage:
    >>> obs_table = [
    ...     {'srcid': '123', 'obs_id': '0001', 'src_num': 1},
    ...     {'srcid': '123', 'obs_id': '0002', 'src_num': 1}
    ... ]
    >>> download_spectra(obs_table, base_dir='data/spectra')

    Command line:
    $ python -m xmm_py_spec.download_spectra data/obs_list.csv \
        --base-dir data/spectra

Error Handling:
    - Network errors trigger automatic retries with exponential backoff
    - Missing or incomplete downloads are logged
    - Download status is tracked in CSV and human-readable logs

Logging:
    - Per-source logs in download.log
    - Global metadata in download_meta.csv and download_meta.log
    - Download validation results appended to logs
"""

from astroquery.esa.xmm_newton import XMMNewton
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Literal
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
# Update instrument handling
InstrumentType = Literal["PN", "M1", "M2"]
INSTRUMENTS: Dict[InstrumentType, str] = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2"
}
DEFAULT_INSTRUMENT = "PN"

# Network-related errors that should trigger retry logic
NETWORK_ERRORS = (
    ConnectionResetError,
    RemoteDisconnected,
    URLError,
    ConnectionError
)


def validate_instrument(instrument: str) -> InstrumentType:
    """Validate and normalize instrument name."""
    if instrument.upper() in INSTRUMENTS:
        return instrument.upper()  # type: InstrumentType
    raise ValueError(
        f"Invalid instrument: {instrument}. "
        f"Must be one of {list(INSTRUMENTS.keys())}"
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
def download_xmm_data(
    obs_id: str,
    src_num: int,
    instrument: InstrumentType = DEFAULT_INSTRUMENT
) -> Path:
    """Download XMM data for a specific observation and source.

    Args:
        obs_id: XMM-Newton observation ID
        src_num: Source number within observation
        instrument: Instrument name (PN, M1, or M2)

    Returns:
        Path to downloaded tar file

    Raises:
        Network errors are automatically retried
        Other errors propagate to caller
    """
    tar_file = Path(f'{obs_id}_{instrument}.tar')
    XMMNewton.download_data(
        obs_id,
        level=LEVEL,
        extension="FTZ,PNG,PDF",
        instname=INSTRUMENTS[instrument],
        sourceno=f'{src_num:04X}',
        filename=f"{obs_id}_{instrument}"
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
    base_path: Path,
    obs_id: str,
    instrument: InstrumentType = DEFAULT_INSTRUMENT,
    cleanup: bool = True
) -> None:
    """Copy files from astroquery's structure to our directory structure."""
    source_dir = base_path / obs_id / "pps"
    if not source_dir.exists():
        return

    target_dir = base_path / LEVEL / instrument
    target_dir.mkdir(parents=True, exist_ok=True)

    # Map instrument names to their file patterns
    inst_patterns = {
        "PN": "*PN*",  # PN patterns
        "M1": "*M1*",  # MOS1 patterns
        "M2": "*M2*"   # MOS2 patterns
    }

    # Copy instrument-specific files
    pattern = inst_patterns[instrument]
    for file_path in source_dir.glob(pattern):
        target_path = target_dir / file_path.name
        shutil.copy2(str(file_path), str(target_path))

    # Copy common files (RMFs, etc.)
    for file_path in source_dir.glob("*.rmf"):
        target_path = target_dir / file_path.name
        shutil.copy2(str(file_path), str(target_path))

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


def validate_download_files(
    dir_path: Path,
    instrument: InstrumentType = DEFAULT_INSTRUMENT
) -> Dict[str, bool]:
    """Validate presence of required spectral files."""
    inst_suffix = instrument
    required_patterns = {
        'spectrum': f'*{inst_suffix}*SRSPEC*.FTZ',
        'background': f'*{inst_suffix}*BGSPEC*.FTZ',
        'arf': f'*{inst_suffix}*ARF*.FTZ',
        'rmf': '*.rmf'
    }

    validation = {}
    for file_type, pattern in required_patterns.items():
        files = list(dir_path.glob(pattern))
        validation[file_type] = bool(files)

    return validation


def download_observation(
    srcid: str, obs_id: str, src_num: int, base_dir: str,
    obs_data: Dict = None, instruments: List[InstrumentType] = None,
    cleanup: bool = True
) -> bool:
    """Download and organize data for a single XMM-Newton observation."""
    instruments = instruments or [DEFAULT_INSTRUMENT]
    output_dir, obs_id = prepare_download(
        srcid, obs_id, src_num, base_dir, obs_data
    )

    if output_dir.exists():
        # Check each instrument directory
        all_empty = all(
            is_directory_empty(output_dir / LEVEL / inst)
            for inst in instruments
            if (output_dir / LEVEL / inst).exists()
        )
        if not all_empty:
            status = "SKIPPED_EXISTS"
            log_download_status(
                srcid, obs_id, src_num, base_dir, status, obs_data
            )
            update_meta_log(obs_data, status, base_dir)
            print(
                f"Skipping {obs_id}_{src_num} - directory exists with files\n"
            )
            return True

    success = True
    for instrument in instruments:
        try:
            tar_file = download_xmm_data(obs_id, src_num, instrument)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Extract all files first
            XMMNewton.get_epic_spectra(
                tar_file,
                source_number=src_num,
                verbose=False,
                path=output_dir,
                instrument=[INSTRUMENTS[instrument]]
            )
            extract_all_files(tar_file, output_dir)

            # Allow time for file system operations
            reorganize_extracted_files(
                output_dir, obs_id, instrument=instrument, cleanup=cleanup
            )
            tar_file.unlink(missing_ok=True)

            # Add small delay before validation to ensure files are settled
            import time
            time.sleep(1)

            # Now validate
            validation = validate_download_files(
                output_dir / LEVEL / instrument,
                instrument=instrument
            )
            if all(validation.values()):
                status = f"SUCCESS ({instrument})"
            else:
                missing = [k for k, v in validation.items() if not v]
                status = (
                    f"INCOMPLETE ({instrument}): "
                    f"Missing {', '.join(missing)}"
                )

            log_download_status(
                srcid, obs_id, src_num, base_dir, status, obs_data
            )
            update_meta_log(obs_data, status, base_dir)

        except Exception as e:
            success = False
            status = f"ERROR ({instrument}): {str(e)}"
            log_download_status(
                srcid, obs_id, src_num, base_dir, status, obs_data
            )
            update_meta_log(obs_data, status, base_dir)
            print(f"Error processing {obs_id}_{src_num}: {str(e)}\n")

    return success


def process_downloads(
        obs_table: List[Dict], base_dir: str, instruments: List[InstrumentType],
        cleanup: bool = True
) -> None:
    """Process all downloads from the observation table."""
    for obs in obs_table:
        download_observation(
            obs['srcid'],
            obs['obs_id'],
            int(obs['src_num']),
            base_dir,
            obs,
            instruments=instruments,
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

    for pps_dir in base_path.glob(f"**/{LEVEL}/{DEFAULT_INSTRUMENT}/"):
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
    instruments: List[InstrumentType] = None,
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
        process_downloads(
            obs_table, base_dir, instruments=instruments, cleanup=cleanup
        )
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
    parser.add_argument(
        '--instruments',
        nargs='+',
        choices=list(INSTRUMENTS.keys()),
        default=[DEFAULT_INSTRUMENT],
        help="Instruments to download (default: PN)"
    )

    args = parser.parse_args()

    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download using astroquery...\n")
        download_spectra(
            obs_table,
            base_dir=args.base_dir,
            instruments=args.instruments,
            cleanup=not args.keep_source
        )
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()
