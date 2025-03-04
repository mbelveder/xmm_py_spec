from pathlib import Path
import logging
from typing import List
import xspec
from astropy.io import fits


def fix_spectrum_paths_inplace(spectrum_file: Path) -> None:
    """Update FITS header keywords to use local paths."""
    companion_files = {
        'BACKFILE': 'combined_background_{instrument}.ds',
        'RESPFILE': 'combined_response_{instrument}.rmf',
        'ANCRFILE': 'combined_arf_{instrument}.arf'
    }

    with fits.open(spectrum_file, mode='update') as hdul:
        # Extract instrument from filename (e.g., combined_spectrum_M1.ds -> M1)
        instrument = spectrum_file.stem.split('_')[-1]

        for hdu in hdul:
            for key in companion_files:
                if key in hdu.header:
                    # Use only the base filename without path
                    filename = companion_files[key].format(
                        instrument=instrument
                    )
                    hdu.header[key] = filename
        hdul.flush()


def setup_and_save_spectrum(spectrum_path: Path) -> bool:
    """Load, setup and save Xspec session for a spectrum."""
    try:
        # Clear any existing XSPEC state
        xspec.AllData.clear()
        xspec.AllModels.clear()

        xspec.Xset.chatter = 10
        xspec.Fit.statMethod = "cstat"

        fix_spectrum_paths_inplace(spectrum_path)

        # Cleanup existing session
        session_path = spectrum_path.parent / f"{spectrum_path.stem}.xcm"
        if session_path.exists():
            logging.info(f"Removing existing session file: {session_path}")
            session_path.unlink()

        # Load single spectrum
        s = xspec.Spectrum(str(spectrum_path))
        logging.info(f"Spectrum loaded: {s.fileName}")

        # Setup basic parameters
        s.ignore("bad")
        s.ignore("**-0.3 11.0-**")

        # Load model
        _ = xspec.Model("powerlaw")
        logging.info("Loaded powerlaw model")

        # Log spectrum details
        logging.info(
            f"Energy range: {s.energies[0][0]:.2f}-{s.energies[-1][1]:.2f} keV"
        )

        # Save session
        xspec.Xset.save(str(session_path), info='a')
        logging.info(f"Session saved to: {session_path}")

        # Append plotting commands to the session file
        with open(session_path, 'a') as f:
            f.write(
                '\ncpd /xw\nsetpl en\nsetpl r 10 10\nquery yes'
                '\nfit\npl eeufs\nshow all'
            )

        return True

    except Exception as e:
        logging.error(f"Failed to process spectrum: {str(e)}")
        return False


def find_grouped_spectra(
        base_dir: str = "data/downloaded_spectra"
) -> List[Path]:
    """Find one grouped spectrum per source directory."""
    base_path = Path(base_dir)
    spectra = []

    # Process each source directory
    for src_dir in base_path.iterdir():
        if not src_dir.is_dir():
            continue

        # Look for combined spectrum in source directory
        spectrum = src_dir / "combined_spectrum_grouped.pha"
        if spectrum.exists():
            spectra.append(spectrum)
        else:
            logging.warning(f"No grouped spectrum found in {src_dir}")

    return spectra


def analyze_spectra(base_dir: str = "data/downloaded_spectra") -> None:
    """Analyze all grouped spectra using PyXspec."""
    logging.info("Starting spectral analysis...")

    spectra = find_grouped_spectra(base_dir)
    if not spectra:
        logging.warning("No grouped spectra found")
        return

    for spectrum in spectra:
        logging.info(f"Processing spectrum: {spectrum}")
        if not setup_and_save_spectrum(spectrum):
            logging.error(f"Failed to process {spectrum}")


def main():
    """Main entry point with basic logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    analyze_spectra()


if __name__ == "__main__":
    main()
