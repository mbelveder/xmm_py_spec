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

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)

        if not required_cols.issubset(reader.fieldnames):
            print(set(reader.fieldnames))
            missing_required = required_cols - set(reader.fieldnames)
            raise ValueError(f"Missing required columns: {missing_required}")
        if not optional_cols.issubset(reader.fieldnames):
            print(set(reader.fieldnames))
            missing_optional = optional_cols - set(reader.fieldnames)
            warnings.warn(
                f"Missing optional columns: {missing_optional}, continue...",
                UserWarning
            )

        return list(reader)


def get_instrument_filenames(
    instrument: InstrumentType,
    mode: Literal["clustered", "individual"] = "individual"
) -> Dict[str, str]:
    """Get instrument-specific filenames for spectra."""
    if mode == "clustered":
        return {
            'spectrum': f'combined_spectrum_{instrument}.ds',
            'background': f'combined_background_{instrument}.ds',
            'response': f'combined_response_{instrument}.rmf',
            'grouped': f'combined_spectrum_grouped_{instrument}.pha'
        }
    else:  # individual
        return {
            'spectrum': f'*{instrument}*SRSPEC*.FTZ',
            'background': f'*{instrument}*BGSPEC*.FTZ',
            'response': f'*{instrument.lower()}*.rmf',
            'arf': f'*{instrument}*SRCARF*.FTZ',  # Added ARF pattern
            'grouped': f'*{instrument}*grouped.pha'
        }
