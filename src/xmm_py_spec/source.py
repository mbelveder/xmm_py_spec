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
        """Find all observation directories for this source"""
        obs_pattern = f"*{self.source_id}/PPS/PN/spectrum.FTZ"
        return list(self.source_path.glob(obs_pattern))