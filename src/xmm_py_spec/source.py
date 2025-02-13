from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class Source:
    source_id: str
    redshift: float
    base_path: Path
    observations: List[Path] = None

    def __post_init__(self):
        self.source_path = self.base_path / self.source_id
        self.observations = self._find_observations()

    def _find_observations(self) -> List[Path]:
        """
        Find all observation spectra for this source.
        Looks for spectrum files in observation directories like:
        source_id/0022740201_28/PPS/PN/spectrum.FTZ
        """
        # Pattern to find all observation directories
        obs_pattern = "*/PPS/PN/*SRSPEC*.FTZ"
        spectra = list(self.source_path.glob(obs_pattern))

        if not spectra:
            raise FileNotFoundError(
                "No spectra found for source "
                f"{self.source_id} in {self.source_path}"
            )

        return sorted(spectra)  # Sort to ensure consistent ordering
