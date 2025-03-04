from pathlib import Path
from typing import Dict, List, Literal
import subprocess
from datetime import datetime
import logging
import argparse

# Add instrument type and mapping
InstrumentType = Literal["PN", "M1", "M2"]
INSTRUMENTS = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2"
}


def validate_combine_args(args: List[str]) -> bool:
    """Validate that essential arguments are present and properly formatted."""
    required_params = ['pha=', 'bkg=', 'rmf=', 'arf=']
    return all(
        any(arg.startswith(param) for arg in args) for param in required_params
    )


def run_spcombine(args: List[str]) -> bool:
    """Run epicspeccombine with given arguments."""
    if not validate_combine_args(args):
        logging.error("Missing required parameters in combine arguments")
        return False

    try:
        cmd_str = "epicspeccombine " + " ".join(args)
        cmd = ["docker", "exec", "xmm_py_spec_container", "sh", "-c", cmd_str]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        logging.info(f"Task completed: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return False


def run_ftgrouppha(source_dir: Path, instrument: InstrumentType) -> bool:
    """Run ftgrouppha inside container with TTY allocation."""
    try:
        spec_file = convert_to_docker_path(
            source_dir / f'combined_spectrum_{instrument}.ds'
        )
        bkg_file = convert_to_docker_path(
            source_dir / f'combined_background_{instrument}.ds'
        )
        out_file = convert_to_docker_path(
            source_dir / f'combined_spectrum_grouped_{instrument}.pha'
        )

        cmd = [
            "docker", "exec", "-it", "xmm_py_spec_container",
            "ftgrouppha",
            f"infile={spec_file}",
            f"outfile={out_file}",
            f"backfile={bkg_file}",
            "grouptype=min",
            "groupscale=15",
            "clobber=yes"
        ]

        subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        logging.info("Successfully grouped spectrum")
        return True

    except subprocess.CalledProcessError as e:
        logging.error(f"Grouping failed: {e.stderr}")
        return False


def save_debug_command(args: List[str], source_dir: Path) -> Path:
    """Save combine command to debug file."""
    debug_dir = source_dir / 'debug'
    debug_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    debug_file = debug_dir / f'combine_command_{timestamp}.txt'

    # Format command for readability
    command = "epicspeccombine \\\n" + "\\\n ".join(args)

    with open(debug_file, 'w') as f:
        f.write(command)

    return debug_file


def convert_to_docker_path(path: Path) -> str:
    """Convert local path to docker container path."""
    parts = path.parts
    try:
        # Find the index of base directory (data/)
        try:
            base_dir_idx = parts.index('data')
        except ValueError:
            raise ValueError(
                "Could not find 'data' in path structure"
            )
        # Include all parts after base_dir
        relative_path = '/'.join(parts[base_dir_idx:])
        # Prepend with app/
        docker_path = Path('/app') / relative_path
        return str(docker_path)
    except ValueError:
        raise ValueError(
            f"Path {path} does not contain 'data' directory"
        )


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

    filenames = get_instrument_filenames(instrument)
    output_path = convert_to_docker_path(source_dir)
    args.extend([
        f"filepha='{output_path}/{filenames['spectrum']}'",
        f"filebkg='{output_path}/{filenames['background']}'",
        f"filersp='{output_path}/{filenames['response']}'"
    ])

    return args


def find_spectral_files(
    src_dir: Path,
    instrument: InstrumentType = "PN"
) -> List[Dict[str, List[Path]]]:
    """
    Find all spectral files in observation directories for given instrument.
    """
    spec_files = []

    # Search for specific instrument directories
    inst_dirs = list(src_dir.glob(f'**/PPS/{instrument}'))

    if not inst_dirs:
        logging.warning(f"No {instrument} directories found in {src_dir}")
        return []

    for inst_dir in inst_dirs:
        files = {
            'spec': list(inst_dir.glob(f'*{instrument}*SRSPEC*.FTZ')),
            'bkg': list(inst_dir.glob(f'*{instrument}*BGSPEC*.FTZ')),
            'rmf': list(inst_dir.glob(f'*{instrument.lower()}*.rmf')),
            'arf': list(inst_dir.glob(f'*{instrument}*ARF*.FTZ'))
        }

        if all(files.values()):
            spec_files.append(files)
        else:
            logging.warning(
                f'Missing {instrument} files in {inst_dir}, skipping...'
            )

    return spec_files


def process_single_source(
    src_dir: Path,
    instrument: InstrumentType = "PN",
    group: bool = False
) -> bool:
    """Process a single source directory for specific instrument."""
    logging.info(
        f"Processing source directory: {src_dir} for instrument {instrument}"
    )

    try:
        spec_files = find_spectral_files(src_dir, instrument)
        if not spec_files:
            logging.warning(
                f"No complete spectral sets found for {instrument} in {src_dir}"
            )
            return False

        # Create instrument-specific output directory
        output_dir = src_dir / "combined" / instrument
        output_dir.mkdir(parents=True, exist_ok=True)

        return combine_source_spectra(output_dir, spec_files, group, instrument)
    except Exception as e:
        logging.error(f"Error processing {src_dir} ({instrument}): {str(e)}")
        return False


def combine_source_spectra(
    src_dir: Path,
    spec_files: List[Dict[str, List[Path]]],
    group: bool,
    instrument: InstrumentType = "PN"
) -> bool:
    """Combine and optionally group spectra for a single source."""
    # Build and run combine command
    args = build_combine_args(spec_files, src_dir, instrument)
    save_debug_command(args, src_dir)

    if not run_spcombine(args):
        logging.error(f"Failed to combine spectra for {src_dir}")
        return False

    logging.info(f"Successfully combined spectra in {src_dir}")

    # Handle grouping if requested
    if group:
        if not run_ftgrouppha(src_dir, instrument):
            logging.error(f"Failed to group spectra for {src_dir}")
            return False
        logging.info(f"Successfully grouped spectra in {src_dir}")

    return True


def get_instrument_filenames(instrument: InstrumentType) -> Dict[str, str]:
    """Get instrument-specific filenames for combined spectra."""
    return {
        'spectrum': f'combined_spectrum_{instrument}.ds',
        'background': f'combined_background_{instrument}.ds',
        'response': f'combined_response_{instrument}.rmf',
        'grouped': f'combined_spectrum_grouped_{instrument}.pha'
    }


def combine_spectra(
    base_dir: str = "data/downloaded_spectra",
    instruments: List[InstrumentType] = None,
    group: bool = False
) -> None:
    """Combine spectra for each source and optionally group them."""
    base_path = Path(base_dir)
    if not base_path.exists():
        logging.error(f"Base directory {base_dir} does not exist")
        return

    instruments = instruments or ["PN"]

    # Process each source directory
    for src_dir in (d for d in base_path.iterdir() if d.is_dir()):
        for instrument in instruments:
            process_single_source(src_dir, instrument, group)


def main():
    """Main entry point with command line arguments."""
    parser = argparse.ArgumentParser(
        description="Combine and optionally group XMM-Newton spectra."
    )
    parser.add_argument(
        '--base-dir',
        default="data/downloaded_spectra",
        help="Base directory for spectra (default: data/downloaded_spectra)"
    )
    parser.add_argument(
        '--group',
        action='store_true',
        help="Group combined spectra using ftgrouppha"
    )
    parser.add_argument(
        '--instruments',
        nargs='+',
        choices=list(INSTRUMENTS.keys()),
        default=["PN"],
        help="Instruments to process (default: PN)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    combine_spectra(args.base_dir, args.instruments, args.group)


if __name__ == "__main__":
    main()
