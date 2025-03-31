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

    return {
        file_type: bool(list(dir_path.glob(pattern)))
        for file_type, pattern in required_patterns.items()
    }


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
