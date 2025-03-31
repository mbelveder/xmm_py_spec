"""Core functionality for XMM-Newton spectral analysis."""

from .validation import (
    ValidationError, FileValidationError, DataValidationError,
    SpectrumValidationError,
    validate_downloaded_files, validate_observation_table,
    validate_combine_args
)

__all__ = [
    'ValidationError',
    'FileValidationError',
    'DataValidationError',
    'SpectrumValidationError',
    'validate_downloaded_files',
    'validate_observation_table',
    'validate_combine_args'
]
