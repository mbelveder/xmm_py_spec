from pathlib import Path
import logging
from typing import List
import xspec
from xspec import AllData
from astropy.io import fits


def fix_spectrum_paths_inplace(spectrum_file: Path) -> None:
    """Update FITS header keywords to use local paths."""
    with fits.open(spectrum_file, mode='update') as hdul:
        for hdu in hdul:
            for key in ['BACKFILE', 'RESPFILE', 'ANCRFILE']:
                if key in hdu.header:
                    old_path = hdu.header[key]
                    if old_path.startswith('/app/data/'):
                        new_path = str(spectrum_file.parent / Path(old_path).name)
                        hdu.header[key] = new_path
        hdul.flush()


def setup_and_save_spectrum(spectrum_path: Path) -> bool:
    """Load, setup and save XSpec session for a spectrum."""
    try:
        fix_spectrum_paths_inplace(spectrum_path)

        # Cleanup existing session
        session_path = spectrum_path.parent / f"{spectrum_path.stem}.xcm"
        if session_path.exists():
            logging.info(f"Removing existing session file: {session_path}")
            session_path.unlink()

        # Clear any existing data and load single spectrum
        AllData.clear()
        s = xspec.Spectrum(str(spectrum_path))
        logging.info(f"Loaded spectrum: {spectrum_path.name}")

        # Setup basic parameters
        s.ignore("bad")
        s.ignore("**-0.3 11.0-**")
        xspec.Xset.chatter = 10
        xspec.Fit.statMethod = "cstat"

        # Load model
        model_str = 'phabs*po'
        powerlaw_model = xspec.Model(model_str)
        powerlaw_model.phabs.nH.frozen = True
        powerlaw_model.phabs.nH.values = 7e-3
        # powerlaw_model.powerlaw.PhoIndex.values = [
        #     1.0, 0.05, -10.0, -10.0, 10.0, 10.0
        #     ]

        print(powerlaw_model.show())

        xspec.Fit.query = "yes"
        try:
            xspec.Fit.perform()
        except Exception:
            return None
        logging.info("Loaded powerlaw model")

        # Save session
        xspec.Xset.save(str(session_path), info='a')
        logging.info(f"Session saved to: {session_path}")

        # Append plotting commands to the session file
        with open(session_path, 'a') as f:
            f.write(
                '\ncpd /xw\nsetpl en\nsetpl r 10 10\nfit\npl eeufs\nshow all'
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

    for src_dir in base_path.iterdir():
        if not src_dir.is_dir():
            continue

        # Look for the specific combined grouped spectrum
        spectrum = src_dir / "combined_spectrum_groupped.pha"
        if spectrum.exists():
            spectra.append(spectrum)
            logging.info(f"Found grouped spectrum in {src_dir.name}")
        else:
            logging.warning(f"No grouped spectrum found in {src_dir.name}")

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
