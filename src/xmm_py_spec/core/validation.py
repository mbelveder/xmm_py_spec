"""
Core validation module for XMM-Newton spectral analysis.

This module provides centralized validation functionality including:
- Custom exceptions
- File and data validation
- Validation decorators
- Structured logging integration

Key features:
- Type-safe validation methods
- Consistent error handling
- Composable validation decorators
"""

from pathlib import Path
from typing import (Dict, List)
import logging
from ..utils import InstrumentType

# Configure module logger
logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Base exception for validation errors."""
    pass


class FileValidationError(ValidationError):
    """Exception raised for file validation failures."""
    pass


class DataValidationError(ValidationError):
    """Exception raised for data validation failures."""
    pass


class SpectrumValidationError(ValidationError):
    """Exception raised for spectrum-specific validation failures."""
    pass


def file_contains_html_error(path: Path, max_bytes: int = 2048) -> bool:
    """Return True if the file content looks like an HTML error page (e.g. 404).

    Used to detect when a download returned an HTTP error body that was
    saved into a file that should contain binary or RMF data.

    Args:
        path: Path to the file to check.
        max_bytes: Maximum number of bytes to read from the start of the file.

    Returns:
        True if the content appears to be HTML (e.g. DOCTYPE, <html>, error text).
        False if the file cannot be read or does not look like HTML.
    """
    if not path.is_file():
        return False
    try:
        with open(path, 'rb') as f:
            raw = f.read(max_bytes)
    except OSError:
        return False
    if not raw:
        return False
    try:
        text = raw.decode('utf-8', errors='replace')
    except Exception:
        text = raw.decode('latin-1', errors='replace')
    text_lower = text.lower()
    if '<!doctype' in text_lower or '<html' in text_lower:
        return True
    if 'not found' in text_lower or ('error' in text_lower and '<' in text):
        return True
    return False


def validate_downloaded_files(
    dir_path: Path,
    instrument: InstrumentType,
    rmf_optional: bool = False
) -> Dict[str, bool]:
    """Validate presence of required spectral files.

    Args:
        dir_path: Directory containing spectral files
        instrument: Instrument type to validate
        rmf_optional: If True, the RMF is not treated as a required file and is
            excluded from the result. Use when the canned-response host is
            unavailable so spectra/ARF still validate without the RMF.

    Returns:
        Dict mapping file types to validation status

    Raises:
        FileValidationError: If directory doesn't exist
    """
    if not dir_path.is_dir():
        raise FileValidationError(f"Invalid directory: {dir_path}")

    required_patterns = {
        'spectrum': f'*{instrument}*SRSPEC*.FTZ',
        'background': f'*{instrument}*BGSPEC*.FTZ',
        'arf': f'*{instrument}*ARF*.FTZ',
        'rmf': '*.rmf'
    }
    if rmf_optional:
        required_patterns.pop('rmf')

    result = {}
    for file_type, pattern in required_patterns.items():
        matches = list(dir_path.glob(pattern))
        if not matches:
            result[file_type] = False
            continue
        # RMF and ARF can be HTTP-fetched; treat HTML error content as missing
        if file_type in ('rmf', 'arf'):
            result[file_type] = not any(
                file_contains_html_error(p) for p in matches
            )
        else:
            result[file_type] = True
    return result


def validate_source_position(
    dir_path: Path,
    instrument: InstrumentType,
    ra: float,
    dec: float,
    tolerance_arcsec: float = 30.0,
) -> float:
    """Verify the extracted spectrum sits at the expected catalog position.

    Guards against the silent wrong-source failure caused by XSA reprocessing:
    nxsa selects a product purely by ``sourceno`` (our ``src_num``), but a
    reprocessing pass renumbers per-observation detections, so a stale
    ``src_num`` can resolve to a *different* physical source and be downloaded
    without any error. This compares the spectrum's ``SRC_RA``/``SRC_DEC``
    header against the catalog ``ra``/``dec`` and rejects mismatches.

    Args:
        dir_path: Directory containing the staged spectral files.
        instrument: Instrument type whose spectrum to check.
        ra: Catalog right ascension of the target source, in degrees.
        dec: Catalog declination of the target source, in degrees.
        tolerance_arcsec: Maximum allowed separation. Genuine extractions sit
            within a few arcsec; wrong-source ones are hundreds of arcsec off,
            so the default cleanly separates the two.

    Returns:
        The angular separation between extracted and catalog position, in
        arcsec.

    Raises:
        SpectrumValidationError: If the spectrum is missing, lacks position
            keywords, or sits farther than ``tolerance_arcsec`` from the
            catalog position.
    """
    from astropy.io import fits
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    spec_files = list(dir_path.glob(f'*{instrument}*SRSPEC*.FTZ'))
    if not spec_files:
        raise SpectrumValidationError(
            f"No {instrument} spectrum found in {dir_path} for position check"
        )
    spec_file = spec_files[0]

    src_ra = src_dec = None
    with fits.open(spec_file) as hdul:
        for hdu in hdul:
            header = hdu.header
            if 'SRC_RA' in header and 'SRC_DEC' in header:
                src_ra = float(header['SRC_RA'])
                src_dec = float(header['SRC_DEC'])
                break
    if src_ra is None or src_dec is None:
        raise SpectrumValidationError(
            f"{spec_file.name} has no SRC_RA/SRC_DEC keywords; "
            f"cannot verify the extracted source position"
        )

    separation = (
        SkyCoord(src_ra, src_dec, unit=u.deg)
        .separation(SkyCoord(ra, dec, unit=u.deg))
        .arcsec
    )
    if separation > tolerance_arcsec:
        raise SpectrumValidationError(
            f"Extracted {instrument} source is {separation:.1f}\" from the "
            f"catalog position (> {tolerance_arcsec:.0f}\" tolerance). The "
            f"src_num likely points at the wrong source after XSA "
            f"reprocessing renumbered detections."
        )
    return separation


def validate_observation_table(obs_table: List[Dict]) -> None:
    """Validate observation table contents.

    Args:
        obs_table: List of observation dictionaries

    Raises:
        DataValidationError: If table is empty or missing required fields
    """
    if not obs_table:
        raise DataValidationError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise DataValidationError(f"Missing required fields: {required_fields}")


def validate_combine_args(args: List[str]) -> bool:
    """Validate spectral combination arguments.

    Args:
        args: List of combination arguments

    Returns:
        True if arguments are valid

    Raises:
        SpectrumValidationError: If required arguments are missing
    """
    required_params = {'pha=', 'bkg=', 'rmf=', 'arf='}
    missing = required_params - {
        param for param in required_params
        if any(arg.startswith(param) for arg in args)
    }

    if missing:
        raise SpectrumValidationError(
            f"Missing required spectral parameters: {missing}"
        )
    return True
