from pathlib import Path
from dataclasses import dataclass
from typing import List, Literal
import logging


@dataclass
class Source:
    """Class representing an XMM-Newton source."""
    source_id: str
    redshift: float
    base_path: Path
    spec_type: Literal["individual", "clustered"] = "individual"
    observations: List[Path] = None

    def __post_init__(self):
        # For individual spectra, append source_id
        # For clustered, use base_path as is since it already includes source_id
        self.source_path = (
            self.base_path / self.source_id if self.spec_type == "individual"
            else self.base_path
        )
        self.observations = self.get_spectra()

    def get_spectra(self) -> List[Path]:
        """Get list of spectrum files based on type."""
        logging.debug(
            f"Searching for {self.spec_type} spectra in {self.source_path}"
        )

        if self.spec_type == "individual":
            pattern = "*/PPS/PN/*SRSPEC*.FTZ"
        else:
            # Look for grouped spectra in cluster directories
            pattern = "clusters/????_??/combined_spectrum_groupped.pha"

        spectra = sorted(self.source_path.glob(pattern))
        logging.debug(
            f"Found {len(spectra)} spectra matching pattern '{pattern}'"
        )

        if not spectra:
            logging.debug("Directory structure:")
            for p in sorted(self.source_path.rglob("*")):
                logging.debug(
                    f"  {'D' if p.is_dir() else 'F'} "
                    f"{p.relative_to(self.source_path)}"
                )
            raise FileNotFoundError(
                f"No {self.spec_type} spectra found in {self.source_path} "
                f"using pattern '{pattern}'"
            )
        return spectra
