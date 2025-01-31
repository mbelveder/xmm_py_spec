"""
XMM-Newton Science Archive Data Download Module (Astroquery-based)

Downloads and organizes spectral data using astroquery's XMMNewton interface.
Maintains the same file organization as the direct download approach.
"""

from astroquery.esa.xmm_newton import XMMNewton
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import shutil
from .utils import load_source_list
import argparse


def log_download_status(srcid: str, obs_id: str, src_num: str, base_dir: str, status: str) -> None:
    """Log download attempt status to a human-readable text file."""
    log_dir = Path(base_dir) / str(srcid)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / "download.log"
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    message = f"[{timestamp}] obs_id {obs_id} src_num {src_num}: {status}\n"
    
    with open(log_file, 'a') as f:
        f.write(message)


def clear_log_file(srcid: str, base_dir: str) -> None:
    """Clear existing log file for a new download session."""
    log_dir = Path(base_dir) / str(srcid)
    log_file = log_dir / "download.log"
    if log_file.exists():
        log_file.write_text('')


def download_observation(srcid: str, obs_id: str, src_num: int, base_dir: str) -> bool:
    """Download and organize data for a single XMM-Newton observation."""
    if len(obs_id) < 10:
        obs_id = f'{int(obs_id):010d}'
    
    output_dir = Path(base_dir) / str(srcid) / f"{obs_id}_{src_num}"
    
    if output_dir.exists():
        log_download_status(srcid, obs_id, src_num, base_dir, "SKIPPED_EXISTS")
        print(f"Skipping {obs_id}_{src_num} - directory exists\n")
        return True
        
    try:
        # Download tar file
        tar_file = Path(f'{obs_id}.tar')
        XMMNewton.download_data(
            obs_id,
            level="PPS",
            extension="FTZ,PNG,PDF",
            instname="PN",
            sourceno=f'{src_num:04X}',
            filename=obs_id
        )

        # Create temporary directory for extraction
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract files (they will go to current directory due to astroquery behavior)
        XMMNewton.get_epic_spectra(
            tar_file,
            source_number=src_num,
            verbose=False,
            path=output_dir
        )

        # Move extracted files from current directory to our organized structure
        for ext in ['.FTZ', '.PNG', '.PDF']:
            for file in Path('.').glob(f'*{ext}'):
                target = output_dir / file.name
                if not target.exists():
                    shutil.move(str(file), str(target))
            
        # Cleanup
        tar_file.unlink(missing_ok=True)
        
        log_download_status(srcid, obs_id, src_num, base_dir, "SUCCESS")
        return True

    except Exception as e:
        log_download_status(srcid, obs_id, src_num, base_dir, f"ERROR: {str(e)}")
        print(f"Error processing {obs_id}_{src_num}: {str(e)}")
        return False


def download_spectra(obs_table: List[Dict], base_dir: str = "data/astroquery_spectra") -> None:
    """Download spectral data for multiple XMM-Newton observations."""
    if not obs_table:
        raise ValueError("Empty observation table provided")

    required_fields = {'obs_id', 'src_num', 'srcid'}
    if not all(field in obs_table[0] for field in required_fields):
        raise ValueError(f"Missing required fields: {required_fields}")

    # Clear logs for each unique source
    srcids = {obs['srcid'] for obs in obs_table}
    for srcid in srcids:
        clear_log_file(srcid, base_dir)

    try:
        for obs in obs_table:
            download_observation(
                obs['srcid'],
                obs['obs_id'],
                int(obs['src_num']),
                base_dir
            )
    except Exception as e:
        print(f"Download failed: {str(e)}")
        raise


def main():
    """Command-line interface for XMM-Newton data downloads."""
    parser = argparse.ArgumentParser(description="Download XMM-Newton spectra using astroquery.")
    parser.add_argument('csv_path', help="Path to CSV file with observation data")
    parser.add_argument('--base-dir', default="data/astroquery_spectra",
                       help="Base directory for downloads (default: data/astroquery_spectra)")
    
    args = parser.parse_args()
    
    try:
        obs_table = load_source_list(args.csv_path)
        print("\nStarting XMM download using astroquery...\n")
        download_spectra(obs_table, base_dir=args.base_dir)
    except Exception as e:
        print(f"Download failed: {e}")
        raise


if __name__ == "__main__":
    main()
