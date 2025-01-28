import csv
from pathlib import Path
from typing import List, Dict, Union


def load_source_list(filepath: Union[str, Path]) -> List[Dict[str, str]]:
    """Load XMM source list from CSV file

    Args:
        filepath: Path to CSV file

    Returns:
        List of dictionaries containing XMM source data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If required columns are missing
    """
    required_cols = {'obs_id', 'src_num'}

    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)

        if not required_cols.issubset(reader.fieldnames):
            print(set(reader.fieldnames))
            missing = required_cols - set(reader.fieldnames)
            raise ValueError(f"Missing required columns: {missing}")

        return list(reader)
