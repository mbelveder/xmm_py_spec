from pathlib import Path
import logging
from typing import List, Optional
import xspec
from astropy.io import fits
import argparse
from .analyze_spectral_variability import ChangeDir


def fix_spectrum_paths_inplace(spectrum_file: Path) -> None:
    """Update FITS header keywords to use local paths.

    Args:
        spectrum_file: Path to spectrum file
        spectra_type: Type of spectra being processed
    """
    with fits.open(spectrum_file, mode='update') as hdul:
        for hdu in hdul:
            for key in ['BACKFILE', 'RESPFILE', 'ANCRFILE']:
                if key not in hdu.header:
                    continue

                # Get just the filename from the full path
                current_path = Path(hdu.header[key])
                hdu.header[key] = current_path.name

        hdul.flush()


def setup_and_save_spectrum(spectrum_path: Path) -> bool:
    """Load, setup and save Xspec session for a spectrum."""
    try:
        # Clear any existing XSPEC state
        xspec.AllData.clear()
        xspec.AllModels.clear()

        xspec.Xset.chatter = 10
        xspec.Fit.statMethod = "cstat"

        with ChangeDir(spectrum_path.parent):
            fix_spectrum_paths_inplace(spectrum_file=spectrum_path.name)

            # Load single spectrum - use filename only
            # since we're in correct dir
            s = xspec.Spectrum(str(spectrum_path.name))
            logging.info(f"Spectrum loaded: {s.fileName}")

            # Setup basic parameters
            s.ignore("bad")
            s.ignore("**-0.3 11.0-**")

            # Load model
            # model_str = 'ph*zph*zpo'
            # TODO: replace hardcoded redshift
            # model = setup_model(model_str, rshift=0.99)
            # model.zphabs.nH.values = 0
            # model.zphabs.nH.frozen = True
            model_str = 'powerlaw'
            _ = xspec.Model(model_str)
            logging.info("Loaded model")

            # Log spectrum details
            logging.info(
                "Energy range: "
                f"{s.energies[0][0]:.2f}-{s.energies[-1][1]:.2f} keV"
            )

            # Save session - ensure clean state by removing existing file
            session_path = Path(
                f"{spectrum_path.stem}_{model_str.replace('*', '_')}.xcm"
            )
            if session_path.exists():
                session_path.unlink()
            xspec.Xset.save(str(session_path), info='a')
            logging.info(f"Session saved to: {session_path}")

            # Append plotting commands to the session file
            # TODO: shoul differ for mo1 and mo2
            with open(session_path, 'a') as f:
                f.write(
                    '\ncpd /xw\nsetpl en\nsetpl r 10 10\nquery yes'
                    '\nfit\npl eeufs\nshow all'
                    # '\nfit\nthaw 2\nfit\npl eeufs\nshow all'
                )

        return True

    except Exception as e:
        logging.error(f"Failed to process spectrum: {str(e)}")
        return False


def _process_cluster_dir(cluster_dir: Path) -> List[Path]:
    """Process a cluster directory and find grouped spectra.

    Args:
        cluster_dir: Path to cluster directory

    Returns:
        List of paths to grouped spectrum files
    """
    if not cluster_dir.is_dir():
        return []

    logging.info(f"Searching in cluster: {cluster_dir}")
    pattern = "combined_spectrum_*_*_*_grouped.pha"
    cluster_spectrum = list(cluster_dir.glob(pattern))

    if cluster_spectrum:
        logging.info(
            f"Found clustered spectrum: {cluster_spectrum[0].name} "
            f"in {cluster_dir}"
        )
    else:
        logging.info(f"No files matching '{pattern}' found in {cluster_dir}")
        logging.debug("Directory contents:")
        for item in cluster_dir.iterdir():
            logging.debug(f"  {item.name}")

    return cluster_spectrum


def _process_source_dir(
    src_dir: Path,
    source_id: Optional[str] = None
) -> List[Path]:
    """Process a source directory and find all grouped spectra.

    Args:
        src_dir: Path to source directory
        source_id: Optional source ID to filter by

    Returns:
        List of paths to grouped spectrum files
    """
    if not src_dir.is_dir() or (source_id and src_dir.name != source_id):
        return []

    logging.info(f"Checking source directory: {src_dir}")
    spectra = []
    clusters_dir = src_dir / "clusters"

    if clusters_dir.exists():
        logging.info(f"Found clusters directory: {clusters_dir}")
        for cluster_dir in clusters_dir.iterdir():
            spectra.extend(_process_cluster_dir(cluster_dir))
    else:
        logging.debug(f"No clusters directory in {src_dir}")

    return spectra


def find_grouped_spectra(
        base_dir: str = "data/downloaded_spectra",
        source_id: Optional[str] = None
) -> List[Path]:
    """
    Find grouped spectra in both regular and clustered directories.

    Args:
        base_dir: Base directory containing source directories
        source_id: Optional source ID to filter results

    Returns:
        List of paths to grouped spectrum files (.pha)
    """
    base_path = Path(base_dir)
    spectra = []
    logging.info(f"Searching for grouped spectra in {base_path}")

    for src_dir in base_path.iterdir():
        spectra.extend(_process_source_dir(src_dir, source_id))

    if not spectra:
        logging.warning(f"No grouped spectra found in {base_dir}")
        logging.debug("Base directory structure:")
        for p in sorted(base_path.rglob("*")):
            rel_path = p.relative_to(base_path)
            file_type = 'D' if p.is_dir() else 'F'
            logging.debug(f"  {file_type} {rel_path}")

    return spectra


def analyze_spectra(
    base_dir: str = "data/clustered_spectra",  # Changed from downloaded_spectra
    source_id: Optional[str] = None
) -> None:
    """
    Analyze all grouped spectra using PyXspec.

    Args:
        base_dir: Base directory containing source directories
        source_id: Optional source ID to analyze
    """
    logging.info("Starting spectral analysis...")

    spectra = find_grouped_spectra(base_dir, source_id)
    if not spectra:
        logging.warning("No grouped spectra found")
        return

    for spectrum in spectra:
        logging.info(f"Processing spectrum: {spectrum}")
        if not setup_and_save_spectrum(spectrum):
            logging.error(f"Failed to process {spectrum}")


def main():
    """Main entry point with basic logging configuration."""
    parser = argparse.ArgumentParser(
        description="Analyze XMM-Newton spectral files."
    )
    parser.add_argument(
        "--base-dir",
        default="data/clustered_spectra",  # Changed from downloaded_spectra
        help="Base directory for spectra"
    )
    parser.add_argument(
        "--source",
        help="Source ID to analyze (default: analyze all)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    analyze_spectra(args.base_dir, args.source)


if __name__ == "__main__":
    main()
