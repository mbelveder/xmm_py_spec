import csv
from pathlib import Path
from typing import List, Dict, Union
import warnings


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
