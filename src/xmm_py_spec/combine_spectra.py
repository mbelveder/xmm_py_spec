from pathlib import Path
from typing import Dict, List, Optional
import subprocess
from datetime import datetime
import logging
import argparse
from .utils import (
    get_instrument_filenames, InstrumentType, CombineMethod
)
import tempfile
import shutil
from .analyze_spectral_variability import ChangeDir
from contextlib import contextmanager
from .analyze_spectra import fix_spectrum_paths_inplace

# Add instrument type and mapping
INSTRUMENTS = {
    "PN": "PN",
    "M1": "M1",
    "M2": "M2",
    "MOS": "MOS"  # Add MOS instrument type
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


def run_ftgrouppha(
    source_dir: Path,
    input_filename: Optional[str] = None,
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE
) -> bool:
    """Run ftgrouppha locally for spectrum grouping.

    Args:
        source_dir: Directory containing the spectra
        input_filename: Optional custom input filename
        method: Method used for combining spectra (affects extensions)
    """
    try:
        if input_filename:
            base_name = input_filename.rsplit(".", 1)[0]
            out_file = str(source_dir / f'{base_name}_grouped.pha')

            src_ext = '.pha' if method == CombineMethod.ADDSPEC else '.ds'
            spec_file = str(source_dir / f'{base_name}{src_ext}')

            # Use appropriate extension for background file
            bkg_ext = '.bak' if method == CombineMethod.ADDSPEC else '.ds'
            bkg_name = base_name
            if method == CombineMethod.EPICSPECCOMBINE:
                bkg_name = base_name.replace('spectrum', 'background')
            bkg_file = str(source_dir / f'{bkg_name}{bkg_ext}')

            cmd = [
                "ftgrouppha",
                f"infile={spec_file}",
                f"outfile={out_file}",
                f"backfile={bkg_file}",
                "grouptype=min",
                "groupscale=15",
                "clobber=yes"
            ]

            # Save command for debugging before execution
            save_debug_command(cmd, source_dir, command_type="group")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            logging.info("Successfully grouped spectrum")
            logging.debug(f"ftgrouppha output: {result.stdout}")

            fix_spectrum_paths_inplace(out_file)
            logging.info("Successfully fixed FITS paths inplace")

            return True

    except subprocess.CalledProcessError as e:
        logging.error(f"Grouping failed: {e.stderr}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error in grouping: {str(e)}")
        return False


def save_debug_command(
    args: List[str],
    source_dir: Path,
    command_type: str = "combine"
) -> Path:
    """Save command to debug file.

    Args:
        args: Command arguments
        source_dir: Directory to save debug files
        command_type: Type of command ('combine' or 'group')

    Returns:
        Path to debug file
    """
    debug_dir = source_dir / 'debug'
    debug_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    debug_file = debug_dir / f'{command_type}_command_{timestamp}.txt'

    # Format command for readability
    if command_type == "combine":
        command = "epicspeccombine \\\n" + "\\\n ".join(args)
    else:
        command = "ftgrouppha \\\n" + "\\\n ".join(args)

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
        instrument: InstrumentType,
        output_filenames: Optional[Dict[str, str]] = None
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

    filenames = (
        output_filenames if output_filenames
        else get_instrument_filenames(instrument)
    )
    output_path = convert_to_docker_path(source_dir)
    args.extend([
        f"filepha='{output_path}/{filenames['spectrum']}'",
        f"filebkg='{output_path}/{filenames['background']}'",
        f"filersp='{output_path}/{filenames['response']}'"
    ])

    return args


def find_spectral_files(
    src_dir: Path,
    instrument: InstrumentType = "PN",
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE
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
        filenames = get_instrument_filenames(
            instrument, mode="individual", method=method
        )
        files = {
            'spec': list(inst_dir.glob(filenames['spectrum'])),
            'bkg': list(inst_dir.glob(filenames['background'])),
            'rmf': list(inst_dir.glob(filenames['response'])),
            # ARF pattern stays the same
            'arf': list(inst_dir.glob('*SRCARF*.FTZ'))
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
    gap_threshold: int,
    instrument: InstrumentType = "PN",
    group: bool = False,
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE
) -> bool:
    """Process a single source directory for specific instrument.
    
    Args:
        src_dir: Source directory path
        gap_threshold: Gap threshold for spectrum combination
        instrument: Instrument type
        group: Whether to group the output
        method: Method to use for combining spectra
    """
    logging.info(
        f"Processing source directory: {src_dir} for instrument {instrument}"
    )

    try:
        spec_files = find_spectral_files(src_dir, instrument, method=method)
        if not spec_files:
            logging.warning(
                f"No complete spectral sets found for {instrument} in {src_dir}"
            )
            return False

        output_dir = src_dir / "combined" / instrument
        output_dir.mkdir(parents=True, exist_ok=True)

        return combine_source_spectra(
            output_dir, spec_files, group, instrument,
            gap_threshold=gap_threshold, method=method
        )
    except Exception as e:
        logging.error(f"Error processing {src_dir} ({instrument}): {str(e)}")
        return False


def combine_source_spectra(
    src_dir: Path,
    spec_files: List[Dict[str, List[Path]]],
    group: bool,
    instrument: InstrumentType = "PN",
    output_filenames: Optional[Dict[str, str]] = None,
    gap_threshold: Optional[int] = None,
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE,
) -> bool:
    """Combine and optionally group spectra for a single source.

    Args:
        src_dir: Directory containing source spectra
        spec_files: List of dictionaries containing spectral file paths
        group: Whether to group the combined spectra
        instrument: Instrument type (PN, M1, M2, or MOS)
        output_filenames: Optional custom filenames for output files
        gap_threshold: Optional gap threshold for filename suffix
        method: Method to use for combining spectra

    Returns:
        bool: True if combination successful, False otherwise
    """
    if not output_filenames:
        filenames = get_instrument_filenames(instrument)
        suffix = f"_{method.suffix}"
        if gap_threshold is not None:
            suffix += f"_gap{gap_threshold}"

        if method == CombineMethod.EPICSPECCOMBINE:
            # Add .ds extension for epicspeccombine
            base_names = {
                k: v.replace('.ds', f'{suffix}.ds')
                for k, v in filenames.items()
            }
        else:
            # For addspec, use just the base name without extension
            base_name = filenames['spectrum'].rsplit('.', 1)[0]
            base_names = {'spectrum': f"{base_name}{suffix}"}
    else:
        base_names = output_filenames

    success = False
    if method == CombineMethod.EPICSPECCOMBINE:
        args = build_combine_args(spec_files, src_dir, instrument, base_names)
        save_debug_command(args, src_dir)
        success = run_spcombine(args)
    else:  # ADDSPEC
        logging.info(f"Using ADDSPEC method for {src_dir}")
        success = run_addspec(
            spec_files,
            src_dir,  # Output directory is the source directory
            base_names  # Use the same naming convention as epicspeccombine
        )

    if not success:
        logging.error(f"Failed to combine spectra for {src_dir}")
        return False

    logging.info(f"Successfully combined spectra in {src_dir}")

    if group:
        group_success = run_ftgrouppha(
            src_dir,
            input_filename=base_names.get('spectrum'),
            method=method
        )
        if not group_success:
            logging.error(f"Failed to group spectra for {src_dir}")
            return False
        logging.info(f"Successfully grouped spectra in {src_dir}")

    return True


def create_spectra_list(
    spec_files: List[Dict[str, List[Path]]],
    list_file: Path
) -> bool:
    """Create input file listing spectra for addspec."""
    try:
        content = []
        with open(list_file, 'w') as f:
            for files in spec_files:
                if not files['spec']:
                    continue
                # Only write spectrum filenames, one per line
                for spec in files['spec']:
                    f.write(f"{spec.name}\n")
                    content.append(spec.name)
        
        logging.info(f"Created spectra list at: {list_file.parent.name}/{list_file.name}")
        logging.info("Spectra list content:")
        for line_num, line in enumerate(content, 1):
            logging.info(f"  {line_num}: {line}")
        return True
    except Exception as e:
        logging.error(f"Failed to create spectra list: {e}")
        return False


@contextmanager
def TempFileManager(spec_files: List[Dict[str, List[Path]]], tmp_dir: Path):
    """Manage temporary files for addspec operation.

    Args:
        spec_files: List of dictionaries containing spectral file paths
        tmp_dir: Temporary directory path

    Yields:
        Tuple[Dict[str, List[Path]], Path]: Copied files and list file path
    """
    copied_files = {'spec': [], 'bkg': [], 'rmf': [], 'arf': []}
    list_file = tmp_dir / "spectra_list.txt"

    try:
        # First copy all files
        for files in spec_files:
            for i, spec in enumerate(files['spec']):
                # Copy spectrum file
                tmp_spec = tmp_dir / spec.name
                shutil.copy2(spec, tmp_spec)
                copied_files['spec'].append(tmp_spec)

                # Copy companion files (needed by addspec but not listed)
                companions = {
                    'bkg': files['bkg'][i] if i < len(files['bkg']) else None,
                    'rmf': files['rmf'][i] if i < len(files['rmf']) else None,
                    'arf': files['arf'][i] if i < len(files['arf']) else None
                }
                for ftype, fpath in companions.items():
                    if fpath:
                        tmp_path = tmp_dir / fpath.name
                        shutil.copy2(fpath, tmp_path)
                        copied_files[ftype].append(tmp_path)

        # Create list file with only spectrum filenames
        create_spectra_list(spec_files, list_file)
        yield copied_files, list_file

    except Exception as e:
        logging.error(f"Failed to prepare files: {str(e)}")
        raise


def run_addspec(
    spec_files: List[Dict[str, List[Path]]],
    output_dir: Path,
    output_filenames: Dict[str, str]
) -> bool:
    """Run addspec with validated input files in a temporary directory."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        logging.info(f"Created working directory: {tmp_path}")

        try:
            with TempFileManager(spec_files, tmp_path) as (copied, list_file):
                logging.info(f"Working in: {tmp_path}")
                logging.info(f"Output will be saved to: {output_dir}")

                # Run addspec in temp directory
                with ChangeDir(tmp_path):
                    # Remove .ds extension if present for addspec output
                    output_base = output_filenames['spectrum'].replace('.ds', '')
                    cmd = [
                        "addspec",
                        f"infil={list_file.name}",
                        f"outfil={output_base}",  # addspec will add extensions
                        "qaddrmf=yes",
                        "qsubback=yes",
                        "clobber=yes"
                    ]
                    logging.debug(f"Running: {' '.join(cmd)}")

                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    logging.info("addspec command completed successfully")
                    if result.stdout:
                        logging.debug(f"addspec output: {result.stdout}")

                # Handle multiple output files with different extensions
                output_base = output_filenames['spectrum'].rsplit('.', 1)[0]
                expected_files = {
                    'pha': f'{output_base}.pha',
                    'bak': f'{output_base}.bak',
                    'rsp': f'{output_base}.rsp'
                }

                logging.info("Checking addspec output files:")
                for ftype, fname in expected_files.items():
                    src = tmp_path / fname
                    logging.info(f"Looking for {ftype} file: {src.name}")
                    
                    if not src.exists():
                        logging.error(
                            f"Output {ftype} file not found: {src.name}\n"
                            f"Directory contents: "
                            f"{[p.name for p in tmp_path.glob('*')]}"
                        )
                        raise FileNotFoundError(
                            f"addspec failed to create {fname}"
                        )
                    
                    file_size = src.stat().st_size
                    logging.debug(f"{ftype} file size: {file_size} bytes")
                    
                    if file_size == 0:
                        logging.error(
                            f"Empty {ftype} file: {fname}"
                        )
                        raise ValueError(f"Empty output file: {fname}")

                    # Copy file to destination
                    dst = output_dir / fname
                    logging.info(f"Copying {ftype} to: {dst.name}")
                    try:
                        shutil.copy2(src, dst)
                        if not dst.exists():
                            raise FileNotFoundError(
                                f"Copy operation failed for {ftype}"
                            )
                        
                        dst_size = dst.stat().st_size
                        if dst_size != file_size:
                            raise ValueError(
                                f"Size mismatch for {ftype}: "
                                f"src={file_size}, dst={dst_size}"
                            )
                        logging.info(f"Successfully created {ftype} file: {dst.name}")
                    except Exception as e:
                        logging.error(
                            f"Failed to copy {ftype} file {src.name}: {str(e)}"
                        )
                        raise

                return True

        except subprocess.CalledProcessError as e:
            logging.error(
                f"addspec failed (code {e.returncode}): {e.stderr}"
            )
            return False
        except Exception as e:
            logging.error(f"Operation failed: {str(e)}")
            logging.debug("Details:", exc_info=True)
            return False


def combine_spectra(
    base_dir: str = "data/downloaded_spectra",
    gap_threshold: int = 30,
    instruments: List[InstrumentType] = None,
    group: bool = False,
    method: CombineMethod = CombineMethod.EPICSPECCOMBINE
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
            print(method)
            process_single_source(
                src_dir, gap_threshold, instrument, group, method
            )


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
    parser.add_argument(
        '--gap-threshold',
        type=int,
        default=30,
        help="Gap threshold for spectrum combination"
    )
    parser.add_argument(
        '--method',
        type=str,
        choices=[m.name for m in CombineMethod],
        default=CombineMethod.EPICSPECCOMBINE.name,
        help="Method to use for combining spectra"
    )
    args = parser.parse_args()

    method = CombineMethod[args.method]
    print(method)
    combine_spectra(
        args.base_dir, args.gap_threshold, args.instruments,
        args.group, method=method
    )


if __name__ == "__main__":
    main()
