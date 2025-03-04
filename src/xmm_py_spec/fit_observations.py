import yaml
from pathlib import Path
from typing import Literal, List, Dict
from .analyze_spectral_variability import analyze_source
from .source import Source
from .logging_config import setup_logging
import logging
from .analyze_spectra import fix_spectrum_paths_inplace
import pandas as pd
from typing import Optional

InstrumentType = Literal["PN", "M1", "M2"]
INSTRUMENTS = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2"
}


def _get_spectra_path(source_id: str, spec_type: str, base_dir: Path) -> Path:
    """Get the path to spectra directory."""
    if spec_type == "individual":
        # For individual mode, just return the downloaded_spectra path
        return base_dir / "downloaded_spectra"
    else:
        # For clustered, go to the clusters directory
        return base_dir / "clustered_spectra" / source_id


def _get_required_files(instrument: InstrumentType) -> Dict[str, str]:
    """Get list of required files for given instrument."""
    patterns = {
        "PN": {
            'spectrum': '*PNS*SRSPEC*.FTZ',
            'background': '*PNS*BGSPEC*.FTZ',
            'response': '*pn*.rmf'
        },
        "M1": {
            'spectrum': '*M1S*SRSPEC*.FTZ',
            'background': '*M1S*BGSPEC*.FTZ',
            'response': '*m1*.rmf'
        },
        "M2": {
            'spectrum': '*M2S*SRSPEC*.FTZ',
            'background': '*M2S*BGSPEC*.FTZ',
            'response': '*m2*.rmf'
        }
    }
    return patterns[instrument]


def _verify_spectrum_files(spectrum: Path, instrument: InstrumentType) -> bool:
    """Verify that all required files exist for a spectrum."""
    required = _get_required_files(instrument)
    parent_dir = spectrum.parent

    missing = []
    for file_type, pattern in required.items():
        if not list(parent_dir.glob(pattern)):
            missing.append(f"{file_type} ({pattern})")

    if missing:
        logging.error(
            f"Missing required files for {instrument} spectrum "
            f"{spectrum}: {missing}"
        )
        return False
    return True


def _fix_spectrum_paths(spectrum: Path) -> bool:
    """Fix paths in spectrum file."""
    try:
        fix_spectrum_paths_inplace(spectrum)
        logging.info(f"Successfully fixed paths for {spectrum}")
        return True
    except Exception as e:
        logging.error(f"Failed to fix paths in {spectrum}: {e}")
        return False


def _process_spectra(source: Source, base_dir: Path) -> Optional[pd.DataFrame]:
    """Process all spectra for a source."""
    try:
        results_df = analyze_source(source, base_dir)
        if results_df.empty:
            logging.warning("No results obtained from analysis")
            return None
        return results_df
    except Exception as e:
        logging.error(f"Failed to analyze spectra: {e}")
        logging.debug("Traceback:", exc_info=True)
        return None


def analyze_source_spectra(
    source_id: str,
    params: dict,
    spec_type: Literal["individual", "clustered"],
    base_dir: Path,
    instruments: List[InstrumentType] = None
) -> None:
    """Analyze individual or clustered spectra for a source."""
    instruments = instruments or ["PN"]

    for instrument in instruments:
        spec_path = _get_spectra_path(source_id, spec_type, base_dir)
        if not spec_path.exists():
            logging.warning(
                f"No {spec_type} spectra directory found at {spec_path}"
            )
            continue

        source = Source(
            source_id=source_id,
            redshift=params["redshift"],
            base_path=spec_path,
            spec_type=spec_type,
            instrument=instrument
        )

        # Process spectra files
        for spectrum in source.observations:
            spectrum_verified = _verify_spectrum_files(spectrum, instrument)
            spectrum_paths_fixed = _fix_spectrum_paths(spectrum)
            if not spectrum_verified or not spectrum_paths_fixed:
                continue

        # Analyze and save results
        results_df = _process_spectra(source, base_dir)
        if results_df is not None:
            unique_name = f"{source_id}_{spec_type}_{instrument}"
            output_file = (
                base_dir / f"source_{unique_name}_results.csv"
            )
            results_df.to_csv(output_file, index=None)
            logging.info(f"Results saved to: {output_file}")


def main():
    """Main entry point with CLI arguments."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze XMM-Newton spectral data"
    )
    parser.add_argument(
        "--source",
        help="Source ID to process (default: all sources)"
    )
    parser.add_argument(
        "--type",
        choices=["individual", "clustered"],
        default="individual",
        help="Type of spectra to analyze"
    )
    parser.add_argument(
        "--instruments",
        nargs="+",
        choices=list(INSTRUMENTS.keys()),
        default=["PN"],
        help="Instruments to analyze (default: PN)"
    )
    args = parser.parse_args()

    base_dir = Path("data")
    log_dir = base_dir / "logs"
    setup_logging(log_dir, "fit_observations_")

    with open("config/sources.yaml") as f:
        config = yaml.safe_load(f)

    if args.source:
        if args.source not in config["sources"]:
            logging.error(f"Source {args.source} not found in config")
            return
        sources = {args.source: config["sources"][args.source]}
    else:
        sources = config["sources"]

    for source_id, params in sources.items():
        logging.info(f"\nProcessing source: {source_id}")
        analyze_source_spectra(
            source_id, params, args.type, base_dir, args.instruments
        )


if __name__ == "__main__":
    main()
