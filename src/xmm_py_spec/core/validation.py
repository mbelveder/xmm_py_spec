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
    instrument: InstrumentType
) -> Dict[str, bool]:
    """Validate presence of required spectral files.

    Args:
        dir_path: Directory containing spectral files
        instrument: Instrument type to validate

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
