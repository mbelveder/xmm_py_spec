from .models import mo2_fit_xmm
from .source import Source
from pathlib import Path
from astropy.io import fits
from datetime import datetime
import pandas as pd
import os
import logging


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


def analyze_source(source: Source, output_dir: Path) -> pd.DataFrame:
    """Analyze all observations for a single source"""
    logging.info(f"\nAnalyzing source {source.source_id}")
    logging.info(f"Found {len(source.observations)} observations")
    fit_results = []

    for i, spectrum_path in enumerate(source.observations, 1):
        logging.info(f"\nProcessing observation {i}/{len(source.observations)}")
        logging.info(f"Spectrum path: {spectrum_path}")
        
        try:
            coord_str, exp_str, date_str, date_obs, obs_id = extract_title(spectrum_path)
            logging.info(f"Observation details: {date_str} | {exp_str}")
            title = f'{coord_str} | {exp_str} | {date_str}'

            plot_dir = output_dir / 'plots' / source.source_id
            plot_dir.mkdir(parents=True, exist_ok=True)
            
            fit_result = mo2_fit_xmm(
                specname=str(spectrum_path),
                rshift=source.redshift,
                en_lower=0.3,
                en_upper=11.0,
                title=title,
                plot_path=plot_dir,
                date_obs=date_obs,
                obs_id=obs_id,
                model_str='ph*zph*zpo'
            )
            
            if fit_result is not None:
                fit_results.append(fit_result)
                logging.info("Fit successful, results stored")
            else:
                logging.warning("Fit failed, skipping observation")
                
        except Exception as e:
            logging.error(f"Error processing observation: {e}")
            continue

    logging.info(f"\nCompleted analysis of source {source.source_id}")
    logging.info(f"Successfully processed {len(fit_results)}/{len(source.observations)} observations")
    
    return pd.DataFrame(fit_results)

# with ChangeDir(data_path):

#     file_path = 'grouped_spectra_list.txt'
#     # Open the file in read mode
#     with open(file_path, 'r') as file:
#         # Read the contents of the file
#         contents = file.read()

#     spectra_names = [name for name in contents.split('\n') if name]
#     print(spectra_names)
#     print(len(spectra_names))

#     fit_results = []
#     for spectrum_name in spectra_names:
#         if spectrum_name == 'grouped_min_src_1430_020_SourceSpec_00001.fits.gz':
#             en_upper = 9.0
#             coord_str, exp_str, date_str, date_obs, obs_id = '', '', '', '', ''
#         else:
#             en_upper = 11.0
#             coord_str, exp_str, date_str, date_obs, obs_id = extract_title(spectrum_name)
#         title = f'{coord_str} | {exp_str} | {date_str}'
#         fit_result = mo2_fit_xmm(
#             specname=spectrum_name, rshift=0.78,
#             en_lower=0.3, en_upper=en_upper,
#             title='', plot_path=data_path / 'plots',
#             date_obs=date_obs, obs_id=obs_id,
#             model_str='ph*zph*zpo'
#             )
#         fit_results.append(fit_result)

#     print(len(fit_results))
#     fit_results = [result for result in fit_results if result is not None]
#     print(len(fit_results))

#     pd.DataFrame(fit_results).to_pickle(
#         '/Users/mike/Yandex.Disk.localized/Работа/ИКИ/Y.repos/lh_obscurus/data/xmm_spectra/srcid_1430/mo2_fit_individual_only_2d_steppar_PN_flux_etc_eRASS_2.pkl'
#         )
#     print('DataFrame is saved')