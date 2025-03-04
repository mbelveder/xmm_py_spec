from pathlib import Path
from dataclasses import dataclass
from typing import List, Literal
import logging

InstrumentType = Literal["PN", "M1", "M2"]


@dataclass
class Source:
    """Class representing an XMM-Newton source."""
    source_id: str
    redshift: float
    base_path: Path
    spec_type: Literal["individual", "clustered"] = "individual"
    observations: List[Path] = None
    instrument: InstrumentType = "PN"

    def __post_init__(self):
        """Initialize source paths and load observations."""
        # Avoid duplicate source_id in path
        self.source_path = (
            self.base_path
            if str(self.base_path).endswith(self.source_id)
            else self.base_path / self.source_id
        )
        self.observations = self.get_spectra()

    def get_spectra(self) -> List[Path]:
        """Get list of spectrum files based on type and instrument."""
        logging.debug(
            f"Searching for {self.spec_type} spectra "
            f"({self.instrument}) in {self.source_path}"
        )

        if self.spec_type == "individual":
            pattern = (
                f"**/PPS/{self.instrument}/*{self.instrument}S*SRSPEC*.FTZ"
            )
        else:
            pattern = (
                f"clusters/*/combined_spectrum_grouped_{self.instrument}.pha"
            )

        spectra = sorted(self.source_path.glob(pattern))
        logging.info(
            f"Found {len(spectra)} {self.instrument} spectra "
            f"matching '{pattern}'"
        )

        if not spectra:
            self._log_directory_structure()
            raise FileNotFoundError(
                f"No {self.spec_type} {self.instrument} spectra found in "
                f"{self.source_path}"
            )
        return spectra

    def _log_directory_structure(self) -> None:
        """Log directory structure for debugging."""
        logging.debug("Directory structure:")
        for p in sorted(self.source_path.rglob("*")):
            rel_path = p.relative_to(self.source_path)
            file_type = 'D' if p.is_dir() else 'F'
            logging.debug(f"  {file_type} {rel_path}")
