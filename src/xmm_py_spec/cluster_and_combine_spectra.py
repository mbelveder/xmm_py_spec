"""
XMM-Newton Spectra Time-based Clustering and Combination Module

This module provides functionality to group XMM-Newton observations by
time proximity and combine their spectra.

The process consists of two main steps:
1. Time-based clustering of observations
2. Combining spectra within each cluster
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import shutil
from .combine_spectra import (
    combine_source_spectra, find_spectral_files, convert_to_docker_path
)
import argparse
from .logging_config import get_logger, setup_basic_logging
from .utils import get_instrument_filenames, InstrumentType

# Initialize basic logging configuration
setup_basic_logging()
logger = get_logger(__name__)

INSTRUMENTS = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2",
    "MOS": "MOS"  # Combined MOS1+MOS2 mode
}


def copy_spectral_files(source_dir: Path, target_dir: Path) -> List[str]:
    """Copy spectral files with verification."""
    copied_files = []
    spectral_patterns = {
        'spectrum': '*SRSPEC*.FTZ',
        'background': '*BGSPEC*.FTZ',
        'response': '*.rmf',
        'arf': '*SRCARF*.FTZ'
    }

    logger.info(f"Creating target directory: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    for file_type, pattern in spectral_patterns.items():
        files = list(source_dir.glob(pattern))
        logger.info(f"Found {len(files)} {file_type} files matching {pattern}")

        if not files:
            logger.warning(f"No {file_type} files found matching {pattern}")
            continue

        for source_file in files:
            target_file = target_dir / source_file.name
            try:
                logger.info(f"Copying {file_type}: {source_file.name}")
                shutil.copy2(source_file, target_file)
                target_size = target_file.stat().st_size
                source_size = source_file.stat().st_size
                if not target_file.exists() or target_size != source_size:
                    raise IOError(
                        f"File verification failed for {source_file.name}"
                    )
                copied_files.append(source_file.name)
                logger.info(
                    f"Successfully copied and verified: {source_file.name}"
                )
            except Exception as e:
                logger.error(f"Failed to copy {source_file}: {e}")

    logger.info(f"Total files copied: {len(copied_files)}")
    return copied_files


def _process_cluster_copying(
    current_cluster: Dict,
    spectra_dir: Path,
    output_dir: Path,
    source_user_id: str,
    instrument: InstrumentType = "PN"
) -> None:
    """Process file copying for a cluster."""
    if not (spectra_dir and output_dir and source_user_id):
        logger.debug(
            "Skipping file operations - missing required parameters: "
            f"spectra_dir={bool(spectra_dir)}, "
            f"output_dir={bool(output_dir)}, "
            f"source_user_id={bool(source_user_id)}"
        )
        return

    start_date = pd.to_datetime(
        current_cluster['observations'][0]['ons_start_date']
    )
    cluster_id = start_date.strftime('%Y_%m')
    cluster_dir = output_dir / source_user_id / 'clusters' / cluster_id

    current_cluster['cluster_dir'] = cluster_dir
    current_cluster['start_date'] = start_date
    current_cluster['end_date'] = pd.to_datetime(
        current_cluster['observations'][-1]['ons_start_date']
    )

    # Copy files for each observation in cluster
    for obs in current_cluster['observations']:
        obs_id = obs['obs_id']
        obs_path_id = str(obs_id).rjust(10, '0')
        src_num = obs['src_num']
        source_dir = (
            spectra_dir / source_user_id / f"{obs_path_id}_{src_num}"
            / "PPS" / instrument
        )
        logger.info(
            f"Checking source directory: {source_dir} "
            f"(exists: {source_dir.exists()})"
        )
        if source_dir.exists():
            target_dir = (
                cluster_dir / f"{obs_path_id}_{src_num}" / "PPS" / instrument
            )
            copied = copy_spectral_files(source_dir, target_dir)
            current_cluster['copied_files'][f"{obs_path_id}_{src_num}"] = copied
        else:
            logger.warning(f"Source directory not found: {source_dir}")


def _init_cluster() -> Dict:
    """Initialize an empty cluster structure."""
    return {
        'observations': [],
        'start_date': None,
        'end_date': None,
        'cluster_dir': None,
        'copied_files': {}
    }


def _process_observation(
    row: pd.Series,
    current_cluster: Dict,
    last_date: pd.Timestamp,
    gap_threshold: int
) -> Tuple[Dict, pd.Timestamp, bool]:
    """Process a single observation and update cluster state."""
    new_cluster_needed = False

    if last_date is None:
        current_cluster['observations'].append(row.to_dict())
    elif (row['ons_start_date'] - last_date).days <= gap_threshold:
        current_cluster['observations'].append(row.to_dict())
    else:
        new_cluster_needed = True

    return current_cluster, row['ons_start_date'], new_cluster_needed


def cluster_observations(
    obs_data: pd.DataFrame,
    gap_threshold: int,
    spectra_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    source_user_id: Optional[str] = None,
    instrument: InstrumentType = "PN"
) -> List[Dict]:
    """Group observations into clusters based on time gaps."""
    if obs_data.empty:
        raise ValueError("Empty observation data provided")
    if 'ons_start_date' not in obs_data.columns:
        raise ValueError("Missing required column: ons_start_date")

    obs_data = obs_data.sort_values(by='ons_start_date').copy()
    logger.info(f"Processing {len(obs_data)} observations")

    clusters = []
    current_cluster = _init_cluster()
    last_date = None

    for _, row in obs_data.iterrows():
        current_cluster, last_date, new_cluster = _process_observation(
            row, current_cluster, last_date, gap_threshold
        )

        if new_cluster and current_cluster['observations']:
            _process_cluster_copying(
                current_cluster, spectra_dir, output_dir,
                source_user_id, instrument
            )
            clusters.append(current_cluster)
            logger.info(
                f"Formed cluster with {len(current_cluster['observations'])} "
                "observations"
            )
            current_cluster = _init_cluster()
            current_cluster['observations'].append(row.to_dict())

    # Handle last cluster
    if current_cluster['observations']:
        _process_cluster_copying(
            current_cluster, spectra_dir, output_dir, source_user_id, instrument
        )
        clusters.append(current_cluster)
        logger.info(
            f"Formed final cluster with "
            f"{len(current_cluster['observations'])} observations"
        )

    logger.info(f"Created {len(clusters)} clusters")
    return clusters


def load_observation_data(csv_path: Path, source_user_id: str) -> pd.DataFrame:
    """Load and validate observation data from CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    obs_data = pd.read_csv(csv_path)
    required_cols = {'obs_id', 'src_num', 'ons_start_date'}
    missing_cols = required_cols - set(obs_data.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    if 'srcid' in obs_data.columns:
        source_id = source_user_id.split('_')[0]
        obs_data = obs_data[obs_data['srcid'] == int(source_id)]
        if obs_data.empty:
            raise ValueError(
                f"No observations found for source "
                f"{source_id} ({obs_data['srcid']})"
            )

    obs_data['ons_start_date'] = pd.to_datetime(
        obs_data['ons_start_date'], errors='coerce'
    )
    if obs_data['ons_start_date'].isna().any():
        raise ValueError("Invalid date format found in ons_start_date column")

    return obs_data


def cluster(
    source_user_id: str,
    csv_path: Path,
    gap_threshold: int,
    spectra_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    instrument: InstrumentType = "PN"
) -> List[Dict]:
    """
    Cluster XMM-Newton observations based on their observation times.

    Args:
        source_user_id: Source identifier
        csv_path: Path to CSV file containing observation data
        gap_threshold: Maximum days between observations in same cluster
        spectra_dir: Optional directory containing spectrum files
        output_dir: Optional directory to save clustered files
        instrument: Instrument to process (default: PN)
    """

    try:
        obs_data = load_observation_data(csv_path, source_user_id)

        # Only attempt file operations if both paths are provided
        if bool(spectra_dir) != bool(output_dir):
            logger.warning(
                "Both spectra_dir and output_dir must be provided "
                "for file operations"
            )
            spectra_dir = output_dir = None

        clusters = cluster_observations(
            obs_data,
            gap_threshold,
            spectra_dir=spectra_dir,
            output_dir=output_dir,
            source_user_id=source_user_id,
            instrument=instrument
        )

        if not clusters:
            logger.warning("No clusters formed - check gap threshold")
        else:
            logger.info(f"Created {len(clusters)} clusters")
            for i, cluster in enumerate(clusters, 1):
                logger.info(
                    f"Cluster {i}: {len(cluster['observations'])} observations "
                    f"from {cluster['start_date']} to {cluster['end_date']}"
                )

        return clusters

    except Exception as e:
        logger.error(
            f"Failed to cluster source {source_user_id}: {e}", exc_info=True
        )
        raise


def build_combine_args(
    spec_files: List[Dict[str, List[Path]]],
    source_dir: Path,
    instrument: InstrumentType
) -> List[str]:
    """Build epicspeccombine arguments with docker paths."""
    # Initialize with empty lists for each file type
    files_by_type = {
        'spec': ('pha', []),
        'bkg': ('bkg', []),
        'rmf': ('rmf', []),
        'arf': ('arf', [])
    }

    # Collect all files
    for observation in spec_files:
        for file_type in files_by_type:
            files_by_type[file_type][1].extend(observation[file_type])

    # Build arguments list
    args = [
        f"{param}='{' '.join(convert_to_docker_path(f) for f in files)}'"
        for _, (param, files) in files_by_type.items()
    ]

    filenames = get_instrument_filenames(instrument, mode="clustered")
    output_path = convert_to_docker_path(source_dir)
    args.extend([
        f"filepha='{output_path}/{filenames['spectrum']}'",
        f"filebkg='{output_path}/{filenames['background']}'",
        f"filersp='{output_path}/{filenames['response']}'"
    ])

    return args


def _process_single_cluster(
    cluster: Dict,
    index: int,
    total: int,
    group: bool,
    instrument: InstrumentType = "PN"
) -> Optional[Tuple[str, Path]]:
    """Process a single cluster and return its combined spectrum path."""
    if not cluster.get('cluster_dir') or not cluster.get('start_date'):
        logger.warning(f"Skipping cluster {index} - missing required data")
        return None

    logger.info(
        f"Processing cluster {index}/{total} from {cluster['start_date']}"
    )

    spec_files = find_spectral_files(cluster['cluster_dir'], instrument)
    if not spec_files:
        logger.warning(f"No complete spectral sets in cluster {index}")
        return None

    # Set up instrument-specific filenames with cluster ID
    cluster_id = cluster['start_date'].strftime('%Y_%m')
    output_filenames = {
        'spectrum': f'combined_spectrum_{instrument}_{cluster_id}.ds',
        'background': f'combined_background_{instrument}_{cluster_id}.ds',
        'response': f'combined_response_{instrument}_{cluster_id}.rmf'
    }

    success = combine_source_spectra(
        cluster['cluster_dir'],
        spec_files,
        group,
        instrument=instrument,
        output_filenames=output_filenames
    )

    if not success:
        logger.error(f"Failed to combine cluster {index}")
        return None

    combined_path = cluster['cluster_dir'] / output_filenames['spectrum']
    return cluster_id, combined_path


def combine_mos_spectra(
    cluster: Dict,
    group: bool = False
) -> Optional[Tuple[str, Path]]:
    """
    Combine MOS1 and MOS2 spectra within a cluster.

    Args:
        cluster: Cluster dictionary containing observation data
        group: Whether to group the combined spectra

    Returns:
        Tuple of (cluster_id, combined_spectrum_path) or None if failed
    """
    if not cluster.get('cluster_dir') or not cluster.get('start_date'):
        logger.warning("Skipping MOS combination - missing cluster data")
        return None

    cluster_id = cluster['start_date'].strftime('%Y_%m')
    logger.info(f"Combining MOS spectra for cluster {cluster_id}")

    # Get spectral files for both MOS instruments
    m1_files = find_spectral_files(cluster['cluster_dir'], "M1")
    m2_files = find_spectral_files(cluster['cluster_dir'], "M2")

    if not m1_files and not m2_files:
        logger.warning("No MOS spectral files found in cluster")
        return None

    # Log observation counts
    logger.info(
        f"M1 observations: {len(m1_files)} "
        f"({', '.join(f'obs{i+1}' for i in range(len(m1_files)))})"
    )
    logger.info(
        f"M2 observations: {len(m2_files)} "
        f"({', '.join(f'obs{i+1}' for i in range(len(m2_files)))})"
    )

    # Combine all MOS files
    all_mos_files = m1_files + m2_files
    if not all_mos_files:
        logger.warning("No MOS files to combine")
        return None

    # Set up MOS-specific filenames
    mos_filenames = {
        'spectrum': f'combined_spectrum_MOS_{cluster_id}.ds',
        'background': f'combined_background_MOS_{cluster_id}.ds',
        'response': f'combined_response_MOS_{cluster_id}.rmf'
    }

    success = combine_source_spectra(
        cluster['cluster_dir'],
        all_mos_files,
        group,
        instrument="MOS",
        output_filenames=mos_filenames
    )

    if not success:
        logger.error("Failed to combine MOS spectra")
        return None

    combined_path = cluster['cluster_dir'] / mos_filenames['spectrum']
    return cluster_id, combined_path


def combine_clustered(
    clusters: List[Dict],
    source_user_id: str,
    instrument: InstrumentType = "PN",
    group: bool = False
) -> Dict[str, Path]:
    """Combine clustered observations using epicspeccombine."""
    if not clusters:
        raise ValueError("No clusters provided")

    combined_spectra = {}
    failed_clusters = []

    try:
        for i, cluster in enumerate(clusters, 1):
            if instrument == "MOS":
                result = combine_mos_spectra(
                    cluster,
                    group
                )
            else:
                result = _process_single_cluster(
                    cluster, i, len(clusters), group, instrument
                )

            if result:
                cluster_id, path = result
                combined_spectra[cluster_id] = path
            else:
                failed_clusters.append(f"Cluster {i}")

        if failed_clusters:
            logger.warning(f"Failed clusters: {', '.join(failed_clusters)}")

        return combined_spectra

    except Exception as e:
        logger.error(
            f"Failed to combine clusters for {source_user_id}: {e}",
            exc_info=True
        )
        raise


def cluster_and_combine_spectra(
    source_user_id: str,
    csv_path: Path,
    spectra_dir: Path,
    output_dir: Path,
    instrument: InstrumentType = "PN",
    gap_threshold: int = 90,
    group: bool = False
) -> Dict[str, Path]:
    """Main function that orchestrates clustering and combination."""
    logger.info(
        f"Starting processing for source {source_user_id} "
        f"with instrument {instrument}"
    )
    logger.debug(f"Parameters: gap_threshold={gap_threshold}, group={group}")

    try:
        clusters = cluster(
            source_user_id=source_user_id,
            csv_path=csv_path,
            gap_threshold=gap_threshold,
            spectra_dir=spectra_dir,
            output_dir=output_dir,
            instrument=instrument
        )
        if not clusters:
            return {}

        combined = combine_clustered(
            clusters, source_user_id, instrument, group
        )

        if not combined:
            logger.warning("No spectra were successfully combined")

        return combined

    except Exception as e:
        logger.error(f"Failed to process source {source_user_id}: {e}")
        raise


def main():
    """Command-line interface for clustering and combining spectra."""
    parser = argparse.ArgumentParser(
        description="Cluster and combine XMM-Newton observations by time"
    )
    parser.add_argument(
        'source_user_id',
        help="Source identifier"
    )
    parser.add_argument(
        '--csv-path',
        type=Path,
        default=Path("data/spectra_to_download/deep_xmm_lh_full.csv"),
        help="Path to CSV file with observation data"
    )
    parser.add_argument(
        '--spectra-dir',
        type=Path,
        default=Path("data/downloaded_spectra"),
        help="Directory containing spectrum files"
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path("data/clustered_spectra"),
        help="Directory to save combined spectra"
    )
    parser.add_argument(
        '--gap-threshold',
        type=int,
        default=90,
        help="Maximum days between observations in same cluster"
    )
    parser.add_argument(
        '--group',
        action='store_true',
        help="Group the combined spectra"
    )
    parser.add_argument(
        '--cluster-only',
        action='store_true',
        help="Only perform clustering without combining"
    )
    parser.add_argument(
        '--instrument',
        choices=list(INSTRUMENTS.keys()),
        default="PN",
        help="Instrument to process (default: PN, options: PN,M1,M2,MOS)"
    )

    args = parser.parse_args()

    try:
        clusters = cluster(
            source_user_id=args.source_user_id,
            csv_path=args.csv_path,
            gap_threshold=args.gap_threshold,
            spectra_dir=args.spectra_dir,
            output_dir=args.output_dir,
            instrument=args.instrument
        )
        logger.info(
            f"Created {len(clusters)} clusters for source {args.source_user_id}"
        )

        if not args.cluster_only:
            combined = combine_clustered(
                clusters=clusters,
                source_user_id=args.source_user_id,
                instrument=args.instrument,
                group=args.group
            )
            logger.info(
                f"Successfully combined {len(combined)} clusters"
            )

    except Exception as e:
        logger.error(f"Process failed: {e}")
        raise


if __name__ == "__main__":
    main()
