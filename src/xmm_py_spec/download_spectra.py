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

import argparse
import gzip
import json
import random
import shutil
import tarfile
import time
from datetime import datetime
from functools import wraps
from http.client import RemoteDisconnected
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Literal, Optional
from urllib.error import URLError

import pandas as pd
from requests.exceptions import ConnectionError
from rich.console import Console
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress,
    SpinnerColumn, TextColumn, TimeElapsedColumn,
)
from rich.table import Table

from astroquery.esa.xmm_newton import XMMNewton

# Workaround: astroquery hardcodes PN RMF versions and doesn't yet include 22.0.
# Prepend the current version so it's tried first.
# TODO: Remove once astroquery ships the update.
XMMNewton._rmf_versions = ("22.0",) + XMMNewton._rmf_versions

from .core.validation import (  # noqa: E402
    file_contains_html_error,
    validate_downloaded_files,
    validate_observation_table,
    validate_source_position,
    ValidationError
)
from .utils import load_source_list  # noqa: E402

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

console = Console()


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
    """Return srcid_userid or srcid subdirectory under download_path."""
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
    time_str = datetime.now().strftime('%H:%M:%S')
    if level == LEVEL_ODF:
        message = f"[{time_str}]  {obs_id:<12}  {status}\n"
    else:
        message = f"[{time_str}]  {obs_id:<12}  {src_num:<5}  {status}\n"
    with open(log_file, 'a') as f:
        f.write(message)


def mark_new_session(
    srcid: str,
    download_path: str,
    obs_data: Optional[Dict] = None,
    level: str = LEVEL
) -> None:
    """Append a session header to the source download log."""
    obs_data = obs_data or {}
    log_dir = get_source_dir(download_path, srcid, obs_data)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "download.log"
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sep = "=" * 80
    prefix = (
        "\n"
        if log_file.exists() and log_file.stat().st_size > 0
        else ""
    )
    with open(log_file, 'a') as f:
        f.write(f"{prefix}{sep}\nSession: {ts}\n{sep}\n\n")


def prepare_download(
    srcid: str,
    obs_id: str,
    src_num: int,
    download_path: str,
    obs_data: Optional[Dict] = None,
    level: str = LEVEL
) -> tuple[Path, str]:
    """Prepare download paths and normalize observation ID.

    For PPS: download_path/source_id_[user_id]/obs_id_src_num/PPS/
    For ODF: download_path/source_id_[user_id]/obs_id/ODF/
    """
    if len(obs_id) < 10:
        obs_id = f'{int(obs_id):010d}'
    source_dir = get_source_dir(download_path, srcid, obs_data or {})
    if level == LEVEL_ODF:
        output_dir = source_dir / obs_id
    else:
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
    console.print(
        f"[yellow]⚠ Attempt {attempt + 1}/{max_retries} failed:[/yellow] "
        f"{error}. Retrying in {delay:.1f}s..."
    )
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
    output_dir = output_dir.resolve()
    orig_cwd = os.getcwd()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(output_dir)
        tar_file = Path(f'{obs_id}_{LEVEL_ODF}.tar')
        XMMNewton.download_data(
            obs_id,
            level=LEVEL_ODF,
            filename=tar_file.name
        )
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
    """Download PPS data to a temporary directory, then move to output_dir."""
    import os
    output_dir = output_dir.resolve()
    orig_cwd = os.getcwd()
    with TemporaryDirectory() as tmpdir:
        try:
            os.chdir(tmpdir)
            tar_name = f'{obs_id}_{instrument}_{LEVEL_PPS}.tar'
            XMMNewton.download_data(
                obs_id,
                level=LEVEL_PPS,
                extension="FTZ,PNG,PDF,ASC",
                instname=INSTRUMENTS[instrument],
                sourceno=f'{src_num:04X}',
                filename=tar_name
            )
            tar_file = Path(tmpdir) / tar_name
            tar_gz_file = tar_file.with_suffix('.tar.gz')
            if tar_file.exists():
                actual = tar_file
            elif tar_gz_file.exists():
                actual = tar_gz_file
            else:
                raise FileNotFoundError(
                    f"Neither {tar_name} nor {tar_name[:-4]}.tar.gz was "
                    f"found after download. Check if the download succeeded."
                )
            output_dir.mkdir(parents=True, exist_ok=True)
            dest = output_dir / actual.name
            shutil.move(str(actual), str(dest))
            return dest
        finally:
            os.chdir(orig_cwd)


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
        if instrument is None:
            raise ValueError("Instrument must not be None for PPS level.")
        return _download_pps_data(obs_id, src_num, instrument, output_dir)


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
                (df['srcid'] == log_entry['srcid'])
                & (df['obs_id'] == log_entry['obs_id'])
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
        time_str = datetime.now().strftime('%H:%M:%S')
        uid = log_entry['user_srcid']
        source_label = (
            f"{log_entry['srcid']}_{uid}" if uid else log_entry['srcid']
        )
        if level == LEVEL_ODF:
            human_msg = (
                f"[{time_str}]  {source_label:<28}  "
                f"{log_entry['obs_id']:<12}  {status}\n"
            )
        else:
            human_msg = (
                f"[{time_str}]  {source_label:<28}  "
                f"{log_entry['obs_id']:<12}  {log_entry['src_num']:<5}  "
                f"{status}\n"
            )
        with open(human_log_path, 'a') as f:
            f.write(human_msg)
    except Exception as e:
        console.print(
            f"[yellow]Warning: Failed to update meta logs:[/yellow] {e}"
        )


DOWNLOAD_THROTTLE_SECONDS = 1


def _log_and_update(
    srcid: str,
    obs_id: str,
    src_num: str,
    download_path: str,
    status: str,
    obs_data: Optional[Dict],
    level: str
) -> None:
    """Log status to per-source log and update meta CSV/log."""
    log_download_status(
        srcid, obs_id, src_num, download_path, status, obs_data, level
    )
    update_meta_log(obs_data, status, download_path, level)


def _reject_html_error_files(
    inst_dir: Path,
    instrument: InstrumentType,
    rmf_optional: bool,
) -> None:
    """Remove RMF/ARF files that hold an HTML error body and fail if fatal.

    A bad ARF is always fatal; a bad RMF is tolerable when ``rmf_optional``.
    """
    bad_files = [
        p for pat in ['*.rmf', f'*{instrument}*ARF*.FTZ']
        for p in inst_dir.glob(pat)
        if file_contains_html_error(p)
    ]
    if not bad_files:
        return
    for p in bad_files:
        p.unlink(missing_ok=True)
    arf_bad = any('ARF' in p.name.upper() for p in bad_files)
    if arf_bad or not rmf_optional:
        raise RuntimeError(
            "RMF or ARF file(s) contained HTML error response "
            "(e.g. 404); removed. Retry download later."
        )


def _validate_staged_inst_dir(
    inst_dir: Path,
    instrument: InstrumentType,
    rmf_optional: bool,
    ra: Optional[float],
    dec: Optional[float],
    pos_tol_arcsec: Optional[float],
    obs_id: str,
    src_num: int,
) -> None:
    """Check the staged dir has the required files and the right source."""
    pre_check = validate_downloaded_files(
        inst_dir, instrument=instrument, rmf_optional=rmf_optional
    ) if inst_dir.exists() else {}
    if pre_check and not all(pre_check.values()):
        missing = [k for k, v in pre_check.items() if not v]
        raise RuntimeError(
            f"Missing required {instrument} files in {inst_dir}: "
            f"{', '.join(missing)}"
        )
    if pos_tol_arcsec is None or ra is None or dec is None:
        return
    separation = validate_source_position(
        inst_dir, instrument, ra, dec, tolerance_arcsec=pos_tol_arcsec
    )
    console.print(
        f"  [green]✓[/green] {obs_id}/{src_num} [{instrument}]: "
        f"position OK ({separation:.1f}\" from catalog)"
    )


def _extract_and_stage(
    tar_file: Path,
    tmp_path: Path,
    obs_id: str,
    src_num: int,
    instrument: InstrumentType,
    cleanup: bool,
    level: str,
    rmf_optional: bool = False,
    ra: Optional[float] = None,
    dec: Optional[float] = None,
    pos_tol_arcsec: Optional[float] = None,
) -> Path:
    """Extract tar, reorganize files, validate. Returns staged inst_dir.

    ``get_epic_spectra`` is the only step that fetches the RMF (a canned
    response not present in the tar). When ``rmf_optional`` is True and that
    fetch fails (e.g. the response host is down), the failure is logged and
    extraction continues so the spectra/background/ARF from the tar are kept.

    When ``pos_tol_arcsec`` is set and catalog ``ra``/``dec`` are available,
    the staged spectrum's header position is checked against the catalog so a
    stale ``src_num`` pointing at the wrong source (after XSA reprocessing) is
    rejected rather than silently kept.
    """
    try:
        XMMNewton.get_epic_spectra(
            tar_file,
            source_number=src_num,
            verbose=False,
            path=str(tmp_path),
            instrument=[INSTRUMENTS[instrument]]
        )
    except Exception as e:
        if not rmf_optional:
            raise
        console.print(
            f"  [yellow]⚠[/yellow] {obs_id}/{src_num} [{instrument}]: "
            f"RMF fetch failed ({e}); keeping spectra/ARF without RMF"
        )
    extract_all_files(tar_file, tmp_path)
    reorganize_extracted_files(
        tmp_path, obs_id, instrument=instrument,
        cleanup=cleanup, level=level
    )
    inst_dir = tmp_path / level / instrument
    _reject_html_error_files(inst_dir, instrument, rmf_optional)
    _validate_staged_inst_dir(
        inst_dir, instrument, rmf_optional,
        ra=ra, dec=dec, pos_tol_arcsec=pos_tol_arcsec,
        obs_id=obs_id, src_num=src_num,
    )
    return inst_dir


def _move_staged_files(
    inst_dir: Path,
    output_dir: Path,
    level: str,
    instrument: InstrumentType
) -> None:
    """Move staged files from temp dir to final output location."""
    target = output_dir / level / instrument
    target.mkdir(parents=True, exist_ok=True)
    try:
        for sub in inst_dir.iterdir():
            shutil.move(str(sub), str(target / sub.name))
    except Exception:
        if target.exists():
            shutil.rmtree(target)
        raise


def _build_status(
    validation: Dict[str, bool],
    instrument: InstrumentType,
    obs_id: str,
    src_num: int,
    rmf_missing: bool = False
) -> str:
    """Return a status string and print progress for a completed download."""
    if all(validation.values()):
        note = " [no rmf]" if rmf_missing else ""
        console.print(
            f"  [green]✓[/green] {obs_id}/{src_num} [{instrument}]{note}"
        )
        return f"SUCCESS ({instrument}){note}"
    missing = [k for k, v in validation.items() if not v]
    console.print(
        f"  [yellow]⚠[/yellow] Incomplete: {obs_id}/{src_num} [{instrument}]"
        f" — missing {', '.join(missing)}"
    )
    return f"INCOMPLETE ({instrument}): Missing {', '.join(missing)}"


def _parse_coord(value) -> Optional[float]:
    """Parse a coordinate value to float, returning None if not numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _download_pps_observation(
    srcid: str,
    obs_id: str,
    src_num: int,
    download_path: str,
    output_dir: Path,
    obs_data: Optional[Dict],
    instruments: List[InstrumentType],
    cleanup: bool,
    level: str,
    rmf_optional: bool = False,
    pos_tol_arcsec: Optional[float] = None,
    _progress=None,
    _task_id=None,
) -> List[str]:
    """Handle PPS download for all requested instruments.

    Returns a list of status strings, one per instrument.
    """
    ra = _parse_coord(obs_data.get('ra')) if obs_data else None
    dec = _parse_coord(obs_data.get('dec')) if obs_data else None

    def _desc(phase: str) -> None:
        if _progress is not None and _task_id is not None:
            _progress.update(
                _task_id,
                description=(
                    f"[cyan]{obs_id}/{src_num} [{instrument}] {phase}[/cyan]"
                )
            )

    if output_dir.exists():
        all_empty = all(
            is_directory_empty(output_dir / level / inst)
            for inst in instruments
            if (output_dir / level / inst).exists()
        )
        if not all_empty:
            _log_and_update(
                srcid, obs_id, str(src_num), download_path,
                "SKIPPED_EXISTS", obs_data, level
            )
            console.print(
                f"  [yellow]→[/yellow] Skipping {obs_id}/{src_num}"
                " (already downloaded)"
            )
            return ["SKIPPED_EXISTS"] * len(instruments)
    statuses = []
    for instrument in instruments:
        try:
            _desc("downloading")
            tar_file = download_xmm_data(
                obs_id, src_num, instrument, level, output_dir
            )
            _desc("extracting")
            with TemporaryDirectory() as tmpdir:
                inst_dir = _extract_and_stage(
                    tar_file, Path(tmpdir), obs_id, src_num,
                    instrument, cleanup, level, rmf_optional,
                    ra=ra, dec=dec, pos_tol_arcsec=pos_tol_arcsec,
                )
                _move_staged_files(inst_dir, output_dir, level, instrument)
            tar_file.unlink(missing_ok=True)
            time.sleep(DOWNLOAD_THROTTLE_SECONDS)
            final_dir = output_dir / level / instrument
            validation = validate_downloaded_files(
                final_dir, instrument=instrument, rmf_optional=rmf_optional
            )
            rmf_missing = rmf_optional and not any(final_dir.glob('*.rmf'))
            status = _build_status(
                validation, instrument, obs_id, src_num, rmf_missing
            )
            _log_and_update(
                srcid, obs_id, str(src_num), download_path,
                status, obs_data, level
            )
        except Exception as e:
            status = f"ERROR ({instrument}): {str(e)}"
            _log_and_update(
                srcid, obs_id, str(src_num), download_path,
                status, obs_data, level
            )
            console.print(
                f"  [red]✗[/red] {obs_id}/{src_num} [{instrument}]: {e}"
            )
        statuses.append(status)
    return statuses


def _download_odf_observation(
    srcid: str,
    obs_id: str,
    download_path: str,
    output_dir: Path,
    obs_data: Optional[Dict],
    level: str,
    _progress=None,
    _task_id=None,
) -> str:
    """Handle ODF download for a single observation.

    Returns a status string.
    """
    odf_dir = output_dir / level
    tar_file = odf_dir / f'{obs_id}_{level}.tar.gz'
    if tar_file.exists():
        _log_and_update(
            srcid, obs_id, '', download_path,
            "SKIPPED_EXISTS", obs_data, level
        )
        console.print(
            f"  [yellow]→[/yellow] Skipping {obs_id}"
            " (ODF tarball already exists)"
        )
        return "SKIPPED_EXISTS"
    if _progress is not None and _task_id is not None:
        _progress.update(
            _task_id,
            description=f"[cyan]{obs_id} [{level}] downloading[/cyan]"
        )
    try:
        download_xmm_data(obs_id, level=level, output_dir=odf_dir)
        _log_and_update(
            srcid, obs_id, '', download_path,
            "SUCCESS (ODF)", obs_data, level
        )
        console.print(f"  [green]✓[/green] {obs_id} [{level}]")
        return "SUCCESS (ODF)"
    except Exception as e:
        status = f"ERROR (ODF): {str(e)}"
        _log_and_update(
            srcid, obs_id, '', download_path, status, obs_data, level
        )
        console.print(f"  [red]✗[/red] {obs_id} [{level}]: {e}")
        return status


def download_observation(
    srcid: str,
    obs_id: str,
    src_num: int,
    download_path: str,
    obs_data: Optional[Dict] = None,
    instruments: Optional[List[InstrumentType]] = None,
    cleanup: bool = True,
    level: str = LEVEL,
    rmf_optional: bool = False,
    pos_tol_arcsec: Optional[float] = None,
    _progress=None,
    _task_id=None,
) -> List[str]:
    """Download and organize data for a single XMM-Newton observation.

    Returns a list of status strings (one per instrument for PPS, one for ODF).
    """
    output_dir, obs_id = prepare_download(
        srcid, obs_id, src_num, download_path, obs_data, level
    )
    try:
        validate_observation_table([
            {'srcid': srcid, 'obs_id': obs_id, 'src_num': src_num}
        ])
        if level == LEVEL_PPS:
            return _download_pps_observation(
                srcid, obs_id, src_num, download_path, output_dir,
                obs_data, instruments or [DEFAULT_INSTRUMENT],
                cleanup, level, rmf_optional, pos_tol_arcsec,
                _progress, _task_id,
            )
        return [_download_odf_observation(
            srcid, obs_id, download_path, output_dir, obs_data, level,
            _progress, _task_id,
        )]
    except ValidationError as e:
        console.print(f"[red]Validation error:[/red] {e}")
        return [f"ERROR: {e}"]


def _print_session_summary(all_statuses: List[str]) -> None:
    """Print a summary table of download results to the console."""
    counts = {
        'Success': sum(
            1 for s in all_statuses if s.startswith('SUCCESS')
        ),
        'Skipped': sum(
            1 for s in all_statuses if s.startswith('SKIPPED')
        ),
        'Incomplete': sum(
            1 for s in all_statuses if s.startswith('INCOMPLETE')
        ),
        'Error': sum(
            1 for s in all_statuses if s.startswith('ERROR')
        ),
    }
    styles = {
        'Success': 'green', 'Skipped': 'yellow',
        'Incomplete': 'yellow', 'Error': 'red',
    }
    table = Table(title="[bold]Download Session Summary[/bold]")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    for label, count in counts.items():
        color = styles[label]
        table.add_row(f"[{color}]{label}[/{color}]", str(count))
    console.print(table)


def process_downloads(
    obs_table: List[Dict],
    download_path: str,
    instruments: Optional[List[InstrumentType]],
    cleanup: bool = True,
    level: str = LEVEL,
    rmf_optional: bool = False,
    pos_tol_arcsec: Optional[float] = None,
) -> List[str]:
    """Process all downloads from the observation table.

    Returns a list of all status strings collected during the session.
    """
    all_statuses: List[str] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"[cyan]Downloading {level}[/cyan]", total=len(obs_table)
        )
        for obs in obs_table:
            statuses = download_observation(
                obs['srcid'],
                obs['obs_id'],
                int(obs['src_num']),
                download_path,
                obs,
                instruments=instruments,
                cleanup=cleanup,
                level=level,
                rmf_optional=rmf_optional,
                pos_tol_arcsec=pos_tol_arcsec,
                _progress=progress,
                _task_id=task,
            )
            all_statuses.extend(statuses)
            progress.advance(task)
        progress.update(task, description="[green]Done[/green]")
    _print_session_summary(all_statuses)
    return all_statuses


def find_incomplete_downloads(
    base_path: Path, rmf_optional: bool = False
) -> List[str]:
    """Find and return list of incomplete downloads with relative paths."""
    incomplete = []
    for pps_dir in base_path.glob(f"**/{LEVEL}/{DEFAULT_INSTRUMENT}/"):
        validation = validate_downloaded_files(
            pps_dir, instrument=DEFAULT_INSTRUMENT, rmf_optional=rmf_optional
        )
        if not all(validation.values()):
            missing = [k for k, v in validation.items() if not v]
            rel_path = pps_dir.relative_to(base_path)
            incomplete.append(
                f"{rel_path}: Missing {', '.join(missing)}"
            )
    return incomplete


def log_validation_results(
    log_path: Path,
    incomplete_dirs: List[str],
    session_statuses: Optional[List[str]] = None
) -> None:
    """Log session summary and final validation results to file."""
    with open(log_path, 'a') as f:
        f.write("\n" + "-" * 80 + "\n")
        if session_statuses is not None:
            success = sum(
                1 for s in session_statuses if s.startswith('SUCCESS')
            )
            skipped = sum(
                1 for s in session_statuses if s.startswith('SKIPPED')
            )
            incomplete = sum(
                1 for s in session_statuses if s.startswith('INCOMPLETE')
            )
            error = sum(
                1 for s in session_statuses if s.startswith('ERROR')
            )
            f.write(
                f"Session summary:  SUCCESS={success}  SKIPPED={skipped}"
                f"  INCOMPLETE={incomplete}  ERROR={error}\n"
            )
        f.write("\nFinal validation:\n")
        if incomplete_dirs:
            f.write("  Incomplete downloads:\n")
            for dir_info in incomplete_dirs:
                f.write(f"  - {dir_info}\n")
        else:
            f.write("  All downloads complete and validated successfully\n")
        f.write("=" * 80 + "\n")


def validate_all_downloads(
    download_path: str,
    session_statuses: Optional[List[str]] = None,
    rmf_optional: bool = False
) -> None:
    """Double check all downloaded files after session completion."""
    base_path = Path(download_path)
    incomplete = find_incomplete_downloads(base_path, rmf_optional=rmf_optional)
    log_validation_results(
        base_path / "download_meta.log", incomplete, session_statuses
    )


def download_spectra(
    obs_table: List[Dict],
    download_path: str = "data/downloaded_spectra",
    instruments: Optional[List[InstrumentType]] = None,
    cleanup: bool = True,
    level: str = LEVEL,
    rmf_optional: bool = False,
    pos_tol_arcsec: Optional[float] = 30.0,
) -> None:
    """Download spectral data for multiple XMM-Newton observations.

    Creates the download_path if it does not exist.

    ``pos_tol_arcsec`` enables a position guard (PPS only): each extracted
    spectrum is checked against the catalog ra/dec and rejected if it sits
    farther than the tolerance, catching stale-``src_num`` wrong-source
    downloads. Pass ``None`` to disable.
    """
    Path(download_path).mkdir(parents=True, exist_ok=True)
    validate_observation_table(obs_table)
    human_log_path = Path(download_path) / "download_meta.log"
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    n_sources = len({
        (obs['srcid'], obs.get('user_srcid')) for obs in obs_table
    })
    sep = "=" * 80
    with open(human_log_path, 'a') as f:
        f.write(f"\n{sep}\n")
        f.write(f"Download Session: {ts}\n")
        f.write(
            f"Level: {level}   Sources: {n_sources}"
            f"   Observations: {len(obs_table)}"
        )
        if instruments:
            f.write(f"   Instruments: {', '.join(instruments)}")
        if rmf_optional:
            f.write("   RMF: optional")
        if level == LEVEL_PPS:
            f.write(
                f"   Position check: {pos_tol_arcsec:.0f}\""
                if pos_tol_arcsec is not None
                else "   Position check: off"
            )
        f.write(f"\n{sep}\n\n")
    seen_sources = set()
    for obs in obs_table:
        source_key = (obs['srcid'], obs.get('user_srcid'))
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            mark_new_session(obs['srcid'], download_path, obs, level)
    try:
        all_statuses = process_downloads(
            obs_table, download_path, instruments=instruments,
            cleanup=cleanup, level=level, rmf_optional=rmf_optional,
            pos_tol_arcsec=pos_tol_arcsec,
        )
        validate_all_downloads(
            download_path, session_statuses=all_statuses,
            rmf_optional=rmf_optional
        )
    except Exception as e:
        console.print(f"[red]Download failed:[/red] {e}")
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
    parser.add_argument(
        '--rmf-optional',
        action='store_true',
        help="Treat the RMF as non-fatal: keep spectra/ARF even when the "
             "response host fails to deliver the RMF (PPS only)."
    )
    parser.add_argument(
        '--position-tolerance',
        type=float,
        default=30.0,
        help="Max arcsec between the extracted spectrum and the catalog "
             "position before a download is rejected as the wrong source "
             "(PPS only; default: 30)."
    )
    parser.add_argument(
        '--no-position-check',
        action='store_true',
        help="Disable the source-position guard (PPS only). Not recommended: "
             "it is what catches stale-src_num wrong-source downloads."
    )
    args = parser.parse_args()
    try:
        obs_table = load_source_list(args.csv_path)
        console.print(
            "\n[bold cyan]Starting XMM download using astroquery..."
            "[/bold cyan]\n"
        )
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
            level=args.level,
            rmf_optional=args.rmf_optional
        )
    except Exception as e:
        console.print(f"[red]Download failed:[/red] {e}")
        raise


if __name__ == "__main__":
    main()
