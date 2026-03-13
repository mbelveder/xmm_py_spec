"""
XMM-Newton Spectral Data Download Module

This module handles the download and organization of XMM-Newton spectral data
using astroquery's XMMNewton interface. It provides functionality to:

1. Download spectral data for multiple observations
2. Organize files into a consistent directory structure
3. Validate downloads and handle network errors
4. Track download status and maintain logs

Directory Structure:
    download_path/
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
    >>> download_spectra(obs_table, download_path='data/spectra')

    Command line:
    $ python -m xmm_py_spec.download_spectra data/obs_list.csv \
        --download-path data/spectra

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

# Workaround: astroquery hardcodes PN RMF versions and doesn't yet include 22.0.
# Prepend the current version so it's tried first.
# TODO: Remove once astroquery ships the update.
XMMNewton._rmf_versions = ("22.0",) + XMMNewton._rmf_versions
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Literal, Optional
import shutil
from .utils import load_source_list
from .core.validation import (
    file_contains_html_error,
    validate_downloaded_files,
    validate_observation_table,
    ValidationError
)
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
import gzip

LEVEL_PPS = "PPS"
LEVEL_ODF = "ODF"
LEVEL = LEVEL_PPS  # Default
# Update instrument handling
InstrumentType = Literal["PN", "M1", "M2"]
INSTRUMENTS: Dict[InstrumentType, str] = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2"
}
DEFAULT_INSTRUMENT = "PN"
SUPPORTED_LEVELS = [LEVEL_PPS, LEVEL_ODF]

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


def get_source_dir(
    download_path: str,
    srcid: str,
    obs_data: Optional[Dict]
) -> Path:
    """Return download_path/srcid_userid or download_path/srcid if no user_srcid."""
    user_srcid = obs_data.get('user_srcid') if obs_data else None
    if user_srcid:
        return Path(download_path) / f"{srcid}_{user_srcid}"
    return Path(download_path) / f"{srcid}"


def log_download_status(
    srcid: str,
    obs_id: str,
    src_num: str,
    download_path: str,
    status: str,
    obs_data: Optional[Dict] = None,
    level: str = LEVEL
) -> None:
    """Log download attempt status to a human-readable text file."""
    obs_data = obs_data or {}
    log_dir = get_source_dir(download_path, srcid, obs_data)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "download.log"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if level == LEVEL_ODF:
        message = f"[{timestamp}] obs_id {obs_id}: {status}\n"
    else:
        message = (
            f"[{timestamp}] obs_id {obs_id} src_num {src_num}: {status}\n"
        )
    with open(log_file, 'a') as f:
        f.write(message)


def clear_log_file(
    srcid: str,
    download_path: str,
    obs_data: Optional[Dict] = None,
    level: str = LEVEL
) -> None:
    """Clear existing log file for a new download session."""
    obs_data = obs_data or {}
    log_dir = get_source_dir(download_path, srcid, obs_data)
    log_file = log_dir / "download.log"
    if log_file.exists():
        with open(log_file, 'a') as f:
            f.write("\n" + "=" * 80 + "\n\n")


def prepare_download(
    srcid: str,
    obs_id: str,
    src_num: int,
    download_path: str,
    obs_data: Optional[Dict] = None,
    level: str = LEVEL
) -> tuple[Path, str]:
    """Prepare download paths and normalize observation ID.

    For PPS: download_path/source_id_[user_id]/PPS/obs_id_src_num
    For ODF: download_path/source_id_[user_id]/ODF/obs_id
    """
    if len(obs_id) < 10:
        obs_id = f'{int(obs_id):010d}'
    source_dir = get_source_dir(download_path, srcid, obs_data or {})
    if level == LEVEL_ODF:
        output_dir = source_dir / "ODF" / obs_id
    else:
        output_dir = source_dir / "PPS" / f"{obs_id}_{src_num}"
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
    print(f"Attempt {attempt + 1}/{max_retries} failed: {error}. Retrying in {delay:.1f}s...")
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


def _download_odf_data(obs_id: str, output_dir: Path) -> Path:
    """Download ODF data directly to output directory by changing CWD."""
    import os
    
    # Save current working directory
    orig_cwd = os.getcwd()
    try:
        # Create output directory and change to it
        output_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(output_dir)
        
        # Download directly to output directory (now CWD)
        tar_file = Path(f'{obs_id}_{LEVEL_ODF}.tar')
        XMMNewton.download_data(
            obs_id,
            level=LEVEL_ODF,
            filename=tar_file.name
        )
        
        # Check for both .tar and .tar.gz files
        tar_gz_file = tar_file.with_suffix('.tar.gz')
        
        if tar_file.exists():
            return output_dir / tar_file.name
        elif tar_gz_file.exists():
            return output_dir / tar_gz_file.name
        else:
            raise FileNotFoundError(
                f"Neither {tar_file} nor {tar_gz_file} was found after "
                f"download. Check if the download succeeded and the output "
                f"path is correct."
            )
    finally:
        # Restore original working directory
        os.chdir(orig_cwd)


def _download_pps_data(
    obs_id: str,
    src_num: int,
    instrument: InstrumentType,
    output_dir: Path
) -> Path:
    """Download PPS data to current directory (existing behavior)."""
    tar_file = Path(f'{obs_id}_{instrument}_{LEVEL_PPS}.tar')
    XMMNewton.download_data(
        obs_id,
        level=LEVEL_PPS,
        extension="FTZ,PNG,PDF,ASC",
        instname=INSTRUMENTS[instrument],
        sourceno=f'{src_num:04X}',
        filename=str(tar_file)
    )
    tar_gz_file = tar_file.with_suffix('.tar.gz')
    
    # Only move to output_dir if all files exist
    if tar_file.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tar_file), str(output_dir / tar_file.name))
        return output_dir / tar_file.name
    elif tar_gz_file.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tar_gz_file), str(output_dir / tar_gz_file.name))
        return output_dir / tar_gz_file.name
    else:
        raise FileNotFoundError(
            f"Neither {tar_file} nor {tar_gz_file} was found after "
            f"download. Check if the download succeeded and the output "
            f"path is correct."
        )


@retry_on_network_error()
def download_xmm_data(
    obs_id: str,
    src_num: Optional[int] = None,
    instrument: Optional[InstrumentType] = None,
    level: str = LEVEL,
    output_dir: Optional[Path] = None
) -> Path:
    """Download XMM data for a specific observation and source.

    For ODF mode: Uses temporary directory to keep root directory clean.
    For PPS mode: Downloads to current directory (existing behavior).

    Args:
        obs_id: XMM-Newton observation ID
        src_num: Source number within observation
        instrument: Instrument name (PN, M1, or M2)
        level: Data level (PPS or ODF)
        output_dir: Directory to save the downloaded file

    Returns:
        Path to downloaded tar file

    Raises:
        Network errors are automatically retried
        FileNotFoundError if no tar file is found after download
        Other errors propagate to caller
    """
    if output_dir is None:
        output_dir = Path('.')
    
    if level == LEVEL_ODF:
        return _download_odf_data(obs_id, output_dir)
    else:
        # PPS mode: existing behavior (download to current directory)
        if instrument is None:
            raise ValueError("Instrument must not be None for PPS level.")
        try:
            return _download_pps_data(obs_id, src_num, instrument, output_dir)
        except Exception:
            # Do not move or organize files or create output_dir if any error occurs
            raise


def organize_files(output_dir: Path) -> None:
    """Move downloaded files to their final location."""
    for ext in ['.FTZ', '.PNG', '.PDF', '.ASC']:
        for file in Path('.').glob(f'*{ext}'):
            target = output_dir / file.name
            if not target.exists():
                shutil.move(str(file), str(target))


def reorganize_extracted_files(
    base_path: Path,
    obs_id: str,
    instrument: InstrumentType = DEFAULT_INSTRUMENT,
    cleanup: bool = True,
    level: str = LEVEL
) -> None:
    """Copy files from astroquery's structure to our directory structure.

    Args:
        base_path: Base directory for the observation.
        obs_id: XMM-Newton observation ID.
        instrument: Instrument name (PN, M1, or M2).
        cleanup: If True, remove the original astroquery extraction directory
            after copying files. Set to False to keep the original files for
            debugging or inspection.
        level: Data level (PPS or ODF).
    """
    source_dir = base_path / obs_id / level.lower()
    if not source_dir.exists():
        return
    target_dir = base_path / level / instrument
    target_dir.mkdir(parents=True, exist_ok=True)
    inst_patterns = {
        "PN": "*PN*",
        "M1": "*M1*",
        "M2": "*M2*"
    }
    pattern = inst_patterns[instrument]
    for file_path in source_dir.glob(pattern):
        target_path = target_dir / file_path.name
        shutil.copy2(str(file_path), str(target_path))
    for file_path in source_dir.glob("*.rmf"):
        target_path = target_dir / file_path.name
        shutil.copy2(str(file_path), str(target_path))
    if cleanup and source_dir.exists():
        shutil.rmtree(source_dir.parent)


def is_directory_empty(path: Path) -> bool:
    """Check if directory is empty."""
    return not any(path.iterdir())


def ensure_tar_file(tar_path: Path) -> Path:
    """Ensure a .tar file exists, decompress .tar.gz if needed.

    Args:
        tar_path: Path to the expected .tar file.

    Returns:
        Path to the .tar file.
    """
    tar_gz_path = tar_path.with_suffix('.tar.gz')
    if not tar_path.exists() and tar_gz_path.exists():
        with gzip.open(tar_gz_path, 'rb') as f_in:
            with open(tar_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
    return tar_path


def extract_all_files(tar_file: Path, output_dir: Path) -> None:
    """Extract all files from tarfile to output directory."""
    tar_file = ensure_tar_file(tar_file)
    target_extensions = ['.FTZ', '.PNG', '.PDF', '.ASC']
    with tarfile.open(tar_file, 'r') as tar:
        for member in tar.getmembers():
            if any(member.name.endswith(ext) for ext in target_extensions):
                tar.extract(member, output_dir)


def update_meta_log(
    obs_data: Optional[Dict],
    status: str,
    download_path: str,
    level: str = LEVEL
) -> None:
    """Update both CSV and human-readable meta log files."""
    base_path = Path(download_path)
    csv_path = base_path / "download_meta.csv"
    human_log_path = base_path / "download_meta.log"
    log_entry = {
        'srcid': obs_data['srcid'] if obs_data else '',
        'obs_id': obs_data['obs_id'] if obs_data else '',
        'src_num': (
            obs_data['src_num'] if obs_data and level != LEVEL_ODF else ''
        ),
        'user_srcid': obs_data.get('user_srcid', '') if obs_data else '',
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'details': json.dumps(obs_data) if obs_data else ''
    }
    try:
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            mask = (
                (df['srcid'] == log_entry['srcid']) &
                (df['obs_id'] == log_entry['obs_id'])
            )
            if level != LEVEL_ODF:
                mask = mask & (df['src_num'] == log_entry['src_num'])
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
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if level == LEVEL_ODF:
            human_msg = (
                f"[{timestamp}] "
                f"Source: {log_entry['srcid']} "
                f"(User ID: {log_entry['user_srcid']}) "
                f"ObsID: {log_entry['obs_id']} "
                f"Status: {status}\n"
            )
        else:
            human_msg = (
                f"[{timestamp}] "
                f"Source: {log_entry['srcid']} "
                f"(User ID: {log_entry['user_srcid']}) "
                f"ObsID: {log_entry['obs_id']} "
                f"SrcNum: {log_entry['src_num']} "
                f"Status: {status}\n"
            )
        with open(human_log_path, 'a') as f:
            f.write(human_msg)
    except Exception as e:
        print(f"Warning: Failed to update meta logs: {e}")


def validate_pn_files(output_dir: Path) -> bool:
    """Check if all required PN files are present in the output directory."""
    required_patterns = [
        '*SRSPEC*.FTZ',
        '*BGSPEC*.FTZ',
        '*SRCARF*.FTZ',
        '*.rmf',
    ]
    for pattern in required_patterns:
        if not list(output_dir.glob(pattern)):
            return False
    return True


def download_observation(
    srcid: str,
    obs_id: str,
    src_num: int,
    download_path: str,
    obs_data: Optional[Dict] = None,
    instruments: Optional[List[InstrumentType]] = None,
    cleanup: bool = True,
    level: str = LEVEL
) -> bool:
    """Download and organize data for a single XMM-Newton observation."""
    if level == LEVEL_PPS:
        instruments = instruments or [DEFAULT_INSTRUMENT]
    output_dir, obs_id = prepare_download(
        srcid, obs_id, src_num, download_path, obs_data, level
    )
    try:
        validate_observation_table([
            {'srcid': srcid, 'obs_id': obs_id, 'src_num': src_num}
        ])
        if level == LEVEL_PPS:
            if output_dir.exists():
                all_empty = all(
                    is_directory_empty(output_dir / level / inst)
                    for inst in (instruments or [])
                    if (output_dir / level / inst).exists()
                )
                if not all_empty:
                    status = "SKIPPED_EXISTS"
                    log_download_status(
                        srcid, obs_id, str(src_num), download_path, status, obs_data, level
                    )
                    update_meta_log(obs_data, status, download_path, level)
                    print(f"Skipping {obs_id}/{src_num} (already downloaded)")
                    return True
            success = True
            for instrument in (instruments or []):
                print(f"Downloading {obs_id}/{src_num} [{instrument}]...")
                try:
                    tar_file = download_xmm_data(
                        obs_id, src_num, instrument, level, output_dir
                    )
                    with TemporaryDirectory() as tmpdir:
                        tmp_path = Path(tmpdir)
                        try:
                            XMMNewton.get_epic_spectra(
                                tar_file,
                                source_number=src_num,
                                verbose=False,
                                path=str(tmp_path),
                                instrument=[INSTRUMENTS[instrument]]
                            )
                            extract_all_files(tar_file, tmp_path)
                            reorganize_extracted_files(
                                tmp_path, obs_id, instrument=instrument,
                                cleanup=cleanup, level=level
                            )
                            inst_dir = tmp_path / level / instrument
                            # Detect HTML error content in HTTP-fetched files
                            check_patterns = ['*.rmf', f'*{instrument}*ARF*.FTZ']
                            bad_files = []
                            for pat in check_patterns:
                                for p in inst_dir.glob(pat):
                                    if file_contains_html_error(p):
                                        bad_files.append(p)
                            if bad_files:
                                for p in bad_files:
                                    p.unlink(missing_ok=True)
                                raise RuntimeError(
                                    "RMF or ARF file(s) contained HTML error "
                                    "response (e.g. 404); removed. Retry "
                                    "download later."
                                )
                            pn_dir = inst_dir
                            if instrument == 'PN' and not validate_pn_files(pn_dir):
                                raise RuntimeError(
                                    f"Missing required PN files in {pn_dir}, not moving to output."
                                )
                            for sub in (pn_dir.iterdir() if pn_dir.exists() else []):
                                target = output_dir / level / instrument
                                target.mkdir(parents=True, exist_ok=True)
                                shutil.move(str(sub), str(target / sub.name))
                        except Exception as e:
                            if output_dir.exists():
                                shutil.rmtree(output_dir)
                            raise
                    tar_file.unlink(missing_ok=True)
                    time.sleep(1)
                    validation = validate_downloaded_files(
                        output_dir / level / instrument,
                        instrument=instrument
                    )
                    if all(validation.values()):
                        status = f"SUCCESS ({instrument})"
                        print(f"  Done: {obs_id}/{src_num} [{instrument}]")
                    else:
                        missing = [k for k, v in validation.items() if not v]
                        status = (
                            f"INCOMPLETE ({instrument}): "
                            f"Missing {', '.join(missing)}"
                        )
                        print(
                            f"  Incomplete: {obs_id}/{src_num} [{instrument}] "
                            f"— missing {', '.join(missing)}"
                        )
                    log_download_status(
                        srcid, obs_id, str(src_num), download_path, status,
                        obs_data, level
                    )
                    update_meta_log(obs_data, status, download_path, level)
                except Exception as e:
                    success = False
                    status = f"ERROR ({instrument}): {str(e)}"
                    log_download_status(
                        srcid, obs_id, str(src_num), download_path, status,
                        obs_data, level
                    )
                    update_meta_log(obs_data, status, download_path, level)
                    print(f"  Error: {obs_id}/{src_num} [{instrument}]: {e}")
            return success
        else:
            # ODF or other non-PPS level
            tar_file = output_dir / f'{obs_id}_{level}.tar.gz'
            if tar_file.exists():
                status = "SKIPPED_EXISTS"
                log_download_status(
                    srcid, obs_id, '', download_path, status, obs_data, level
                )
                update_meta_log(obs_data, status, download_path, level)
                print(f"Skipping {obs_id} (ODF tarball already exists)")
                return True
            print(f"Downloading {obs_id} [{level}]...")
            try:
                tar_file = download_xmm_data(
                    obs_id, level=level, output_dir=output_dir
                )
                status = "SUCCESS (ODF)"
                log_download_status(
                    srcid, obs_id, '', download_path, status, obs_data, level
                )
                update_meta_log(obs_data, status, download_path, level)
                print(f"  Done: {obs_id} [{level}]\n")
                return True
            except Exception as e:
                status = f"ERROR (ODF): {str(e)}"
                log_download_status(
                    srcid, obs_id, '', download_path, status, obs_data, level
                )
                update_meta_log(obs_data, status, download_path, level)
                print(f"  Error: {obs_id} [{level}]: {e}")
                return False
    except ValidationError as e:
        print(f"Validation error: {e}")
        return False


def process_downloads(
    obs_table: List[Dict],
    download_path: str,
    instruments: Optional[List[InstrumentType]],
    cleanup: bool = True,
    level: str = LEVEL
) -> None:
    """Process all downloads from the observation table."""
    for obs in obs_table:
        download_observation(
            obs['srcid'],
            obs['obs_id'],
            int(obs['src_num']),
            download_path,
            obs,
            instruments=instruments,
            cleanup=cleanup,
            level=level
        )


def find_incomplete_downloads(base_path: Path) -> List[str]:
    """Find and return list of incomplete downloads with relative paths."""
    incomplete = []
    for pps_dir in base_path.glob(f"**/{LEVEL}/{DEFAULT_INSTRUMENT}/"):
        validation = validate_downloaded_files(
            pps_dir, instrument=DEFAULT_INSTRUMENT
        )
        if not all(validation.values()):
            missing = [k for k, v in validation.items() if not v]
            rel_path = pps_dir.relative_to(base_path)
            incomplete.append(
                f"{rel_path}: Missing {', '.join(missing)}"
            )
    return incomplete


def log_validation_results(log_path: Path, incomplete_dirs: List[str]) -> None:
    """Log validation results to file."""
    with open(log_path, 'a') as f:
        f.write("\nFinal validation of downloaded files:\n")
        f.write("-" * 40 + "\n")
        if incomplete_dirs:
            f.write("Incomplete downloads found for the following observations:\n")
            for dir_info in incomplete_dirs:
                f.write(f"- {dir_info}\n")
        else:
            f.write("All downloads complete and validated successfully\n")
        f.write("\nDownload session completed.\n")
        f.write("=" * 80 + "\n")


def validate_all_downloads(download_path: str) -> None:
    """Double check all downloaded files after session completion."""
    base_path = Path(download_path)
    incomplete = find_incomplete_downloads(base_path)
    log_validation_results(base_path / "download_meta.log", incomplete)


def download_spectra(
    obs_table: List[Dict],
    download_path: str = "data/downloaded_spectra",
    instruments: Optional[List[InstrumentType]] = None,
    cleanup: bool = True,
    level: str = LEVEL
) -> None:
    """Download spectral data for multiple XMM-Newton observations.

    Creates the download_path if it does not exist.
    """
    Path(download_path).mkdir(parents=True, exist_ok=True)
    validate_observation_table(obs_table)
    human_log_path = Path(download_path) / "download_meta.log"
    with open(human_log_path, 'a') as f:
        f.write(f"\n{'=' * 80}\n")
        f.write(f"Starting new download session at {datetime.now()}\n\n")
    csv_path = Path(download_path) / "download_meta.csv"
    if csv_path.exists():
        csv_path.unlink()
    seen_sources = set()
    for obs in obs_table:
        source_key = (obs['srcid'], obs.get('user_srcid'))
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            clear_log_file(obs['srcid'], download_path, obs, level)
    try:
        process_downloads(
            obs_table, download_path, instruments=instruments,
            cleanup=cleanup, level=level
        )
        validate_all_downloads(download_path)  # Add final validation
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
        '--download-path',
        default="data/downloaded_spectra/",
        help="Base directory for downloads (default: data/downloaded_spectra)"
    )
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
        help="Instruments to download (default: PN). Only used for PPS."
    )
    parser.add_argument(
        '--level',
        type=str,
        choices=SUPPORTED_LEVELS,
        default=LEVEL_PPS,
        help="Data level to download (PPS or ODF; default: PPS)"
    )
    args = parser.parse_args()
    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download using astroquery...\n")
        # Only use instruments for PPS
        if args.level == LEVEL_PPS:
            instruments = args.instruments
        else:
            instruments = None
        download_spectra(
            obs_table,
            download_path=args.download_path,
            instruments=instruments,
            cleanup=not args.keep_source,
            level=args.level
        )
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()
