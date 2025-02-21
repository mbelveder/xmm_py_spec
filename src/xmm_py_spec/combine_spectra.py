from pathlib import Path
from typing import Dict, List
import subprocess
from datetime import datetime
import logging
import argparse


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


def run_ftgrouppha(source_dir: Path) -> bool:
    """Run ftgrouppha inside container with TTY allocation."""
    try:
        spec_file = convert_to_docker_path(source_dir / 'combined_spectrum.ds')
        bkg_file = convert_to_docker_path(source_dir / 'combined_background.ds')
        out_file = convert_to_docker_path(
            source_dir / 'combined_spectrum_groupped.pha'
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
        spec_files: List[Dict[str, List[Path]]], source_dir: Path
) -> List[str]:
    """Build epicspeccombine arguments with docker paths.

    Args:
        spec_files: List of dictionaries containing paths to spectral files
        source_dir: Directory where combined files will be saved

    Returns:
        List of formatted arguments for epicspeccombine
    """
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

    # Add output files
    output_path = convert_to_docker_path(source_dir)
    args.extend([
        f"filepha='{output_path}/combined_spectrum.ds'",
        f"filebkg='{output_path}/combined_background.ds'",
        f"filersp='{output_path}/combined_response.rmf'"
    ])

    return args


def find_spectral_files(src_dir: Path) -> List[Dict[str, List[Path]]]:
    """Find all spectral files in observation directories."""
    spec_files = []

    pn_dirs = list(src_dir.glob('**/PPS/PN'))

    if not pn_dirs:
        print(f"No PN directories found in {src_dir}")
        return []

    # Directory with file paths for every source
    for pn_dir in pn_dirs:
        files = {
            'spec': list(pn_dir.glob('*SRSPEC*.FTZ')),
            'bkg': list(pn_dir.glob('*BGSPEC*.FTZ')),
            'rmf': list(pn_dir.glob('*.rmf')),
            'arf': list(pn_dir.glob('*SRCARF*.FTZ'))
        }

        if all(files.values()):  # All required files exist
            spec_files.append(files)
        else:
            print(f'Missing files in {pn_dir}, skipping...')
            continue

    return spec_files


def process_single_source(src_dir: Path, group: bool = False) -> bool:
    """Process a single source directory."""
    logging.info(f"Processing source directory: {src_dir}")

    try:
        spec_files = find_spectral_files(src_dir)
        if not spec_files:
            logging.warning(f"No complete spectral sets found in {src_dir}")
            return False

        return combine_source_spectra(src_dir, spec_files, group)
    except Exception as e:
        logging.error(f"Error processing {src_dir}: {str(e)}")
        return False


def combine_source_spectra(
    src_dir: Path, spec_files: List[Dict[str, List[Path]]], group: bool
) -> bool:
    """Combine and optionally group spectra for a single source."""
    # Build and run combine command
    args = build_combine_args(spec_files, src_dir)
    save_debug_command(args, src_dir)

    if not run_spcombine(args):
        logging.error(f"Failed to combine spectra for {src_dir}")
        return False

    logging.info(f"Successfully combined spectra in {src_dir}")

    # Handle grouping if requested
    if group:
        if not run_ftgrouppha(src_dir):
            logging.error(f"Failed to group spectra for {src_dir}")
            return False
        logging.info(f"Successfully grouped spectra in {src_dir}")

    return True


def combine_spectra(
    base_dir: str = "data/downloaded_spectra", group: bool = False
) -> None:
    """Combine spectra for each source and optionally group them."""
    base_path = Path(base_dir)
    if not base_path.exists():
        logging.error(f"Base directory {base_dir} does not exist")
        return

    # Process each source directory
    for src_dir in (d for d in base_path.iterdir() if d.is_dir()):
        process_single_source(src_dir, group)


def main():
    """Main entry point with basic logging configuration."""
    parser = argparse.ArgumentParser(
        description="Combine and optionally group XMM-Newton spectra."
    )
    parser.add_argument(
        '--base-dir',
        default="data/downloaded_spectra/test",
        help="Base directory for spectra (default: data/downloaded_spectra/test)"
    )
    parser.add_argument(
        '--group',
        action='store_true',
        help="Group combined spectra using ftgrouppha"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    combine_spectra(args.base_dir, args.group)


if __name__ == "__main__":
    main()
