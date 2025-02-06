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
    """Build epicspeccombine arguments with docker paths."""
    combined_files = {
        'spec': [],
        'bkg': [],
        'rmf': [],
        'arf': []
    }

    # Collect all files from each observation
    for files in spec_files:
        for key in combined_files:
            combined_files[key].extend(files[key])

    args = []
    # Join docker paths with spaces for each file type
    for key, files in combined_files.items():
        docker_paths = [convert_to_docker_path(f) for f in files]
        if key == 'spec':
            args.append(f"pha='{' '.join(docker_paths)}'")
        elif key == 'bkg':
            args.append(f"bkg='{' '.join(docker_paths)}'")
        elif key == 'rmf':
            args.append(f"rmf='{' '.join(docker_paths)}'")
        elif key == 'arf':
            args.append(f"arf='{' '.join(docker_paths)}'")

    # Add output files with app/ prefix
    output_docker_path = convert_to_docker_path(source_dir)
    args.extend([
        f"filepha='{output_docker_path}/combined_spectrum.ds'",
        f"filebkg='{output_docker_path}/combined_background.ds'",
        f"filersp='{output_docker_path}/combined_response.rmf'"
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


def combine_spectra(
        base_dir: str = "data/downloaded_spectra", group: bool = False
) -> None:
    """Combine spectra for each source and optionally group them."""
    base_path = Path(base_dir)
    if not base_path.exists():
        logging.error(f"Base directory {base_dir} does not exist")
        return

    for src_dir in base_path.iterdir():
        if not src_dir.is_dir():
            continue

        try:
            spec_files = find_spectral_files(src_dir)
            if not spec_files:
                logging.warning(f"No complete spectral sets found in {src_dir}")
                continue

            args = build_combine_args(spec_files, src_dir)
            save_debug_command(args, src_dir)

            if run_spcombine(args):
                logging.info(f"Successfully combined spectra in {src_dir}")
                if group:
                    if run_ftgrouppha(src_dir):
                        logging.info(f"Successfully grouped spectra in {src_dir}")
                    else:
                        logging.error(f"Failed to group spectra for {src_dir}")
            else:
                logging.error(f"Failed to combine spectra for {src_dir}")

        except Exception as e:
            logging.error(f"Error processing {src_dir}: {str(e)}")
            continue


def main():
    """Main entry point with basic logging configuration."""
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
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    combine_spectra(args.base_dir, args.group)


if __name__ == "__main__":
    main()
