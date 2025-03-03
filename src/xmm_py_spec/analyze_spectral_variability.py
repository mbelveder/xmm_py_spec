import logging
from .models import mo2_fit_xmm
from .source import Source
from pathlib import Path
from astropy.io import fits
from datetime import datetime
import pandas as pd
import os
import traceback
from typing import Literal, Dict


class ChangeDir:
    """
    Context manager for changing the current working directory
    and then return back to the one you started from. Prevents from
    unwanted change of the working derictory.
    """
    def __init__(self, new_path):
        self.new_path = os.path.expanduser(new_path)

    def __enter__(self):
        self.saved_path = os.getcwd()
        os.chdir(self.new_path)

    def __exit__(self, *_):
        os.chdir(self.saved_path)


data_path = Path(
    '/Users/mike/Docker/mywork/1430/time_groups/all_groups/'
)


def extract_title(spectrum_name):

    with fits.open(spectrum_name) as hdul:
        # Access the primary header
        header = hdul[0].header

        date_obs = header['DATE-OBS']
        date_obs_dt = datetime.strptime(date_obs, '%Y-%m-%dT%H:%M:%S')
        formatted_date = date_obs_dt.strftime('%d %B %Y')

        # exp_start = header['EXPSTART']
        exp_start = header['DATE-OBS']
        exp_start_dt = datetime.strptime(exp_start, '%Y-%m-%dT%H:%M:%S')
        # exp_stop = header['EXPSTOP']
        exp_stop = header['DATE-END']
        exp_stop_dt = datetime.strptime(exp_stop, '%Y-%m-%dT%H:%M:%S')
        esp_time = exp_stop_dt - exp_start_dt

        ra_obj = header['RA_OBJ']
        dec_obj = header['DEC_OBJ']

        obs_id = header['OBS_ID']

        coord_str = f'RA: {ra_obj:.4f}, DEC: {dec_obj:.4f}'
        print()
        exp_str = f'Exposure: {esp_time.seconds:.2e}'
        date_str = f'DATE-OBS: {formatted_date}'

        return coord_str, exp_str, date_str, date_obs_dt, obs_id


InstrumentType = Literal["PN", "M1", "M2"]

def analyze_source(
    source: Source,
    output_dir: Path,
    instrument: InstrumentType = "PN"
) -> pd.DataFrame:
    """Analyze all observations for a single source."""
    logger = logging.getLogger(__name__)
    logger.info(
        f"\nStarting analysis of source {source.source_id} "
        f"using {instrument} instrument"
    )
    
    # Set instrument on source
    source.instrument = instrument

    logger.info(f"Found {len(source.observations)} observations")

    fit_results = []

    # Create plots directory with absolute path
    plots_dir = output_dir.resolve() / 'plots' / source.source_id
    plots_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Plot directory created: {plots_dir}")

    for i, spectrum_path in enumerate(source.observations, 1):
        logger.info(f"\nProcessing observation {i}/{len(source.observations)}")
        logger.info(f"Spectrum path: {spectrum_path}")

        try:
            coord_str, exp_str, date_str, date_obs, obs_id = extract_title(
                spectrum_path
            )
            logger.debug(f"Observation details: {date_str} | {exp_str}")
            logger.debug(f"Coordinates: {coord_str}")
            title = f'{coord_str} | {exp_str} | {date_str}'

            # Extract obs_id and src_num from directory structure
            src_path = spectrum_path.parent.parent.parent
            logger.info(f"src_path: {src_path}")
            # For individual spectra, use obsid_srcnum
            if 'SRSPEC' in spectrum_path.name:
                obs_path = spectrum_path.parent.parent.parent.parent
                plot_name = (
                    f"source_{src_path.name}_obs_{obs_path.name}_fit.png"
                )
            else:
                # For clustered spectra, use cluster date
                cluster_date = spectrum_path.parent.name  # Gets YYYY_MM
                plot_name = (
                    f"source_{src_path.name}_cluster_{cluster_date}_fit.png"
                )

            plot_path = plots_dir / plot_name
            # plot_name = f"{src_path.name}.png"
            # plot_path = plots_dir / plot_name
            logger.info(f"Plot will be saved as: {plot_name} at {plot_path}")

            with ChangeDir(spectrum_path.parent):
                fit_result = mo2_fit_xmm(
                    specname=spectrum_path.name,
                    rshift=source.redshift,
                    en_lower=0.3,
                    en_upper=11.0,
                    title=title,
                    plot_path=plot_path,
                    date_obs=date_obs,
                    obs_id=obs_id,
                    model_str='ph*zph*zpo'
                )
                if fit_result is not None:
                    fit_results.append(fit_result)
                    logger.info("Fit successful")
                else:
                    logger.warning("Fit failed")

        except Exception as e:
            logger.error(
                f"Error processing observation:\n{traceback.format_exc()}: {e}"
            )
            return None

    n_success = len(fit_results)
    logger.info(f"\nCompleted analysis of source {source.source_id}")
    logger.info(
        f"Successfully processed {n_success}/{len(source.observations)} "
        "observations"
    )

    return pd.DataFrame(fit_results) if fit_results else pd.DataFrame()
