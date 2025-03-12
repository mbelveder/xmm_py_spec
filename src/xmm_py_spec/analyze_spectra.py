from pathlib import Path
import logging
from typing import List
import xspec
from astropy.io import fits


def get_companion_filename(
    spec_prefix: str, file_type: str, spectrum_file: Path
) -> str:
    """Get companion filename based on file type."""
    if file_type == 'BACKFILE':
        return spec_prefix.replace('SRSPEC', 'BGSPEC') + '.FTZ'
    elif file_type == 'RESPFILE':
        instrument = spec_prefix[11:13].lower()
        rmf_files = list(spectrum_file.parent.glob(f'*{instrument}*.rmf'))
        if not rmf_files:
            raise FileNotFoundError(f"No RMF file found for {instrument}")
        return rmf_files[0].name
    else:  # ANCRFILE
        return spec_prefix.replace('SRSPEC', 'SRCARF') + '.FTZ'


def fix_spectrum_paths_inplace(spectrum_file: Path) -> None:
    """Update FITS header keywords to use local paths."""
    is_clustered = "combined_spectrum" in str(spectrum_file)

    with fits.open(spectrum_file, mode='update') as hdul:
        for hdu in hdul:
            for key in ['BACKFILE', 'RESPFILE', 'ANCRFILE']:
                if key not in hdu.header:
                    continue

                if is_clustered:
                    # Extract both instrument and date suffix if present
                    parts = spectrum_file.stem.split('_')
                    if len(parts) > 3 and parts[-2].isdigit():  # MOS_YYYY_MM
                        instrument = parts[-3]  # MOS
                        date_suffix = f"_{parts[-2]}_{parts[-1]}"  # _YYYY_MM
                    else:
                        instrument = parts[-1]  # M1/M2/PN
                        date_suffix = ""

                    companion_files = {
                        'BACKFILE': (
                            f'combined_background_{instrument}{date_suffix}.ds'
                        ),
                        'RESPFILE': (
                            f'combined_response_{instrument}{date_suffix}.rmf'
                        ),
                        'ANCRFILE': (
                            f'combined_arf_{instrument}{date_suffix}.arf'
                        )
                    }
                    hdu.header[key] = companion_files[key]
                else:
                    spec_prefix = spectrum_file.stem
                    hdu.header[key] = get_companion_filename(
                        spec_prefix, key, spectrum_file
                    )
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
