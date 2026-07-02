import csv
from pathlib import Path
from typing import List, Dict, Union, Literal
import warnings
from enum import Enum, auto

InstrumentType = Literal["PN", "M1", "M2"]


class CombineMethod(Enum):
    """Spectra combination method."""
    EPICSPECCOMBINE = auto()
    ADDSPEC = auto()

    @property
    def suffix(self) -> str:
        """Get filename suffix for this method."""
        return self.name.lower()


def load_source_list(filepath: Union[str, Path]) -> List[Dict[str, str]]:
    """Load XMM source list from CSV file

    Args:
        filepath: Path to CSV file

    Returns:
        List of dictionaries containing XMM source identificators

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns are missing
    """
    required_cols = {'obs_id', 'src_num', 'srcid'}
    optional_cols = {'user_srcid'}

    # skipinitialspace strips whitespace after the delimiter, so CSVs written
    # with ", " separators don't leak leading spaces into values such as
    # obs_id (e.g. " 0022740101"), which would otherwise be sent verbatim to
    # the archive and rejected. Header names are stripped explicitly.
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f, skipinitialspace=True)

        fieldnames = [
            name.strip() for name in (reader.fieldnames or [])
        ]
        if not required_cols.issubset(fieldnames):
            missing_required = required_cols - set(fieldnames)
            raise ValueError(f"Missing required columns: {missing_required}")
        if not optional_cols.issubset(fieldnames):
            missing_optional = optional_cols - set(fieldnames)
            warnings.warn(
                f"Missing optional columns: {missing_optional}, continue...",
                UserWarning
            )

        return [
            {
                (k.strip() if k else k):
                    (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
            }
            for row in reader
        ]


def get_instrument_filenames(
    instrument: InstrumentType,
    mode: Literal["clustered", "individual"] = "individual",
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE
) -> Dict[str, str]:
    """Get instrument-specific filenames for spectra.

    Args:
        instrument: Type of instrument (PN, M1, M2)
        mode: Whether files are for clustered or individual spectra
        method: Method used for combining spectra
    """
    if mode == "clustered":
        # For addspec mode, use specific extensions
        if method == CombineMethod.ADDSPEC:
            return {
                'spectrum': 'combined_spectrum_*_addspec.pha',
                'background': 'combined_spectrum_*_addspec.bak',
                'response': 'combined_spectrum_*_addspec.rsp',
                'grouped': 'combined_spectrum_*_addspec_grouped.pha'
            }
        # Default epicspeccombine mode
        return {
            'spectrum': f'combined_spectrum_{instrument}.ds',
            'background': f'combined_background_{instrument}.ds',
            'response': f'combined_response_{instrument}.rmf',
            'grouped': f'combined_spectrum_grouped_{instrument}.pha'
        }
    elif mode == "individual":
        return {
            # 'spectrum': 'spectrum_{instrument}_addspec.pha',
            # 'background': 'spectrum_{instrument}_addspec.bak',
            # 'response': 'spectrum_{instrument}_addspec.rsp',
            # 'grouped': 'spectrum_{instrument}_addspec_grouped.pha'
            'spectrum': f'*{instrument}*SRSPEC*.FTZ',
            'background': f'*{instrument}*BGSPEC*.FTZ',
            'response': f'*{instrument.lower()}*.rmf',
            'arf': f'*{instrument}*SRCARF*.FTZ',  # Added ARF pattern
            'grouped': f'*{instrument}*grouped.pha'
        }
