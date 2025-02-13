import os
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import traceback
from xspec import Xset, Fit, AllData, AllModels, Model, Plot
from typing import Callable, Tuple
import logging
from pathlib import Path


def extract_xspec_values(
    series: pd.Series, model: Model, prefix: str
) -> pd.Series:
    """
    Extract best-fit parameter values and errors from an XSPEC model.

    Args:
        series (pd.Series): Series to add parameter values and errors.
        model (xspec.Model): XSPEC model to extract values and errors.
        prefix (str): String to prepend to parameter names.

    Returns:
        pd.Series: Input Series, updated with parameter values and errors.

    Note:
        Function adds three entries for each parameter in the XSPEC model:
        the best-fit value, the negative error, and the positive error. Keys
        for these entries are constructed by concatenating the prefix, the
        component name, the parameter name, and a suffix indicating the type
        of value ('', '_nerr', or '_perr').
    """
    # extract the best-fit parameter values and errors
    for comp_name in model.componentNames:
        for param in getattr(model, comp_name).parameterNames:
            value_and_error = getattr(getattr(model, comp_name), param)

            value = value_and_error.values[0]
            value_nerr = value - value_and_error.error[0]
            value_perr = value_and_error.error[1] - value

            series[f'{prefix}_{comp_name}_{param}'] = value
            series[f'{prefix}_{comp_name}_{param}_nerr'] = value_nerr
            series[f'{prefix}_{comp_name}_{param}_perr'] = value_perr

            series[f'{prefix}_par_{comp_name}_{param}_xspec'] = \
                value_and_error.values
            series[f'{prefix}_par_{comp_name}_{param}'] = \
                [value, value_nerr, value_perr]

    return series


def ellipse_minmax(
        x: np.array, y: np.array, z: np.array,
        levels: int | np.ndarray, ax: plt.Axes
) -> Tuple[Tuple, Tuple]:
    """
    Extracts parameter errors from 2d steppar contours directly.
    https://heasarc.gsfc.nasa.gov/xanadu/xspec/manual/node86.html
    https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.contour.html

    Args:
        x (np.array): An array of x values
        y (np.array): An array of y values
        z (np.array): The height values over which the contour is drawn
        levels (int | np.ndarray): The levels of the contour
        ax (plt.Axes): The axes to plot the contour

    Returns:
        Tuple[Tuple, Tuple]: The x and y min and max values of the contour
    """

    # Plot the contour
    CS = ax.contour(
        x, y, z, levels, colors=['red']
    )

    contour_lines = CS.allsegs[0]

    # A contour might be present with several distinct lines
    # (e. g.) srcid 4200
    if len(contour_lines) > 1:
        all_contour_dots = np.empty((0, 2))
        for contour_line in contour_lines:
            all_contour_dots = np.vstack(
                [all_contour_dots, contour_line]
            )
        x_ellipse, y_ellipse = (
            all_contour_dots[:, 0], all_contour_dots[:, 1]
        )
    else:
        all_contour_dots = CS.allsegs[0][0]
        x_ellipse, y_ellipse = (
            all_contour_dots[:, 0], all_contour_dots[:, 1]
        )
    x_min_max = (min(x_ellipse), max(x_ellipse))
    y_min_max = (min(y_ellipse), max(y_ellipse))

    return x_min_max, y_min_max


def extract_errors_from_2d_contour(
        series: pd.Series, ellipse_minmax: Callable,
        plot_savepath: str = ''
) -> pd.Series:
    """
    Extracts parameter errors from 2d steppar contours directly and adds them
    into `series`.

    Args:
        series (pd.Series): A series with the contour coordinates
        ellipse_minmax (Callable): A function that extracts minimum and
            maximum values from the contour

    Returns:
        pd.Series: An updeted `series` with best fit values and parameter
            errors extracted directly from 2d steppar contours.
    """

    step2d_x = series['step2d_x']
    step2d_y = series['step2d_y']
    step2d_z = series['step2d_z']
    levelvals = series['levelvals']

    fig, ax = plt.subplots(figsize=(8, 4))

    ax.contourf(
        step2d_x, step2d_y, step2d_z,
        np.append(levelvals - 2.71, levelvals),
        colors='red', alpha=.1
    )

    _ = ax.contour(
        step2d_x, step2d_y, step2d_z, levelvals, colors=['red'],
    )

    # Find the index of the minimum value (best fit)
    argmin_id = np.unravel_index(step2d_z.argmin(), step2d_z.shape)
    nh_2d_bf = step2d_x[argmin_id[1]]
    phoind_2d_bf = step2d_y[argmin_id[0]]

    nh_min_max, phoind_min_max = ellipse_minmax(
        step2d_x, step2d_y, step2d_z, levelvals, ax
    )

    nh_conf_lower, nh_conf_upper = nh_min_max
    phoind_conf_lower, phoind_conf_upper = phoind_min_max

    ax.set_xlim(.001, 10)
    ax.set_xscale('log')
    ax.set_ylim(-1, 2)

    nh_conf_lower, nh_conf_upper = nh_min_max
    phoind_conf_lower, phoind_conf_upper = phoind_min_max

    series['mo2_PhoIndex_step_2d'] = phoind_2d_bf
    series['mo2_PhoIndex_step_2d_lower'] = phoind_conf_lower
    series['mo2_PhoIndex_step_2d_upper'] = phoind_conf_upper
    series['mo2_PhoIndex_step_2d_perr'] = phoind_conf_upper - phoind_2d_bf
    series['mo2_PhoIndex_step_2d_nerr'] = phoind_2d_bf - phoind_conf_lower

    series['mo2_nH_step_2d'] = nh_2d_bf
    series['mo2_nH_step_2d_lower'] = nh_conf_lower
    series['mo2_nH_step_2d_upper'] = nh_conf_upper
    series['mo2_nH_step_2d_perr'] = nh_conf_upper - nh_2d_bf
    series['mo2_nH_step_2d_nerr'] = nh_2d_bf - nh_conf_lower

    for hline in [phoind_conf_lower, phoind_conf_upper]:
        ax.axhline(hline, color='k')

    for vline in [nh_conf_lower, nh_conf_upper]:
        ax.axvline(vline, color='k')

    ax.axhline(
        phoind_2d_bf, color='gray', ls='--'
    )

    ax.axvline(
        nh_2d_bf, color='gray', ls='--'
    )

    # plt.xscale('log')
    ax.set_xlabel(r'$N_{\rm H}\ (10^{22})$')
    ax.set_ylabel('Г')

    if plot_savepath:
        os.makedirs(os.path.dirname(plot_savepath), exist_ok=True)
        fig.savefig(plot_savepath, dpi=300, bbox_inches='tight')

    return series


def mo2_fit_xmm(
        specname: str, rshift: float, en_lower: float, en_upper: float,
        model_str: str, title: str, plot_path: Path, date_obs, obs_id,
        phoind_fixed=False
) -> pd.Series:
    """
    Performs a fit for a single spectrum using a specified model.

    Args:
        srcid (str): source id
        rshift (float): redshift
        en_lower (float): lower energy limit
        en_upper (float): upper energy limit
        phoind_upper (float): upper limit for the photon index estimated in mo1
            (for visualization purposes only)
        cts (int): counts
        cts_err (float): counts error
        nn_spec_class (str): a class of the spectrum
            taken from the LH catalog
        nn_spec_class_origin (str): a class of the spectrum
            taken from the LH catalog
        nn_spec_z (float): a redshift of the spectrum
            taken from the LH catalog
        nn_srgz_zph (float): a redshift of the spectrum
            taken from the LH catalog
        model_str (str): a model to fit (in Xspec notation)
        data_path (str): a path to the data
        plot_path (str): a path to the plots
        phoind_fixed (bool, optional): a flag to fix the photon index.
            Defaults to False.

    Returns:
        pd.Series: a pandas Series containing fit parameters and plotting data
    """
    logging.info(f"\nFitting spectrum: {specname}")
    logging.info(f"Model: {model_str}, redshift: {rshift}")
    logging.info(f"Energy range: {en_lower}-{en_upper} keV")

    en_lower = float(en_lower)
    en_upper = float(en_upper)

    # Set Xspec parameters
    Xset.parallel.error = 10
    Xset.parallel.steppar = 10
    Fit.query = "yes"
    Fit.statMethod = "cstat"  # IMPORTANT
    # Fit.method = "migrad"

    # Load data and ignore bad energy ranges
    AllData.clear()
    AllModels.clear()

    try:
        AllData(specname)
        logging.info("Spectrum loaded successfully")
    except Exception as e:
        logging.error(f"Failed to load spectrum: {e}")
        return None

    AllData.ignore("bad")
    AllData.ignore(f'**-{en_lower} {en_upper}-**')
    print(f'{specname} is riden')
    print()

    # Set model parameters
    zphabs_zpo_model = Model(model_str)
    zphabs_zpo_model.phabs.nH.values = 7e-3
    zphabs_zpo_model.phabs.nH.frozen = True
    zphabs_zpo_model.zphabs.Redshift.values = rshift
    zphabs_zpo_model.zpowerlw.Redshift.values = rshift

    zphabs_zpo_model.zphabs.nH.values = 0
    zphabs_zpo_model.zphabs.nH.frozen = True
    Fit.perform()
    zphabs_zpo_model.zphabs.nH.frozen = False
    # zphabs_zpo_model.zphabs.nH.values = [0.01, 0.01, 1e-2, 1e-2, 1e3, 1e3]
    Fit.perform()
    print()
    print('Fit.perform() after nH was freezed and then thawed')
    print()

    # Perform a 2D parameter scan and extract the fit results
    try:
        logging.info("Starting 2D parameter scan")
        Fit.steppar('log 2 1e-1 10 100 nolog 4 -1 3 100')
        logging.info("Steppar completed successfully")

        # Perform a contour plot of the 2D parameter scan
        # Do it now, because 1d steppars are follows
        Plot.addCommand("image off")
        Plot("contour,,1,2.71")
        Plot.delCommand(1)
        step2d_labels = Plot.labels()
        step2d_x = np.array(Plot.x())
        step2d_y = np.array(Plot.y())
        step2d_z = np.array(Plot.z())
        statval = Fit.statistic
        levelvals = np.array(Plot.contourLevels())

        # 2.71 is 90% confidence for 1 parameter, 1-3 is the range
        # of parameters to fit
        err_commdns = f"2.71 1-{zphabs_zpo_model.nParameters}"

        Fit.perform()
        Fit.error(err_commdns)

        AllModels.calcFlux("0.5 2.0 err 500")
        flux_tuple = AllData(1).flux
        logging.info(
            f"Flux calculated: {flux_tuple[0]:.2e} "
            f"(+{flux_tuple[2]:.2e}/-{flux_tuple[1]:.2e})"
        )

        suffix = model_str.replace("*", "_") + '_3stepp_kev'
        xspec_datamodel_file = f'xspec_{suffix}_{specname.split(".")[0]}.xcm'
        # phoind_value_errors, phoind_step_coords = make_steppar('4 -5 9 500')

        # (phoind_bf, phoind_low_lim, phoind_up_lim) = phoind_value_errors
        # phoind_perr = phoind_up_lim - phoind_bf
        # phoind_nerr = phoind_bf - phoind_low_lim

        fit_result = pd.Series({
            'filename': specname,
            'date_obs': date_obs,
            'obs_id': obs_id,
            'mo2_model': model_str,
            'mo2_cstat': Fit.statistic,
            'mo2_dof': Fit.dof,
            'mo2_cstat_r': Fit.statistic / Fit.dof,
            'flux': flux_tuple[0],
            'flux_nerr': flux_tuple[1],
            'flux_perr': flux_tuple[2]}
        )

        if os.path.exists(xspec_datamodel_file):
            os.remove(xspec_datamodel_file)
        Xset.save(xspec_datamodel_file)

        # fit_result = pd.Series()

        # Extract the best-fit parameter values and errors
        fit_result = extract_xspec_values(
            fit_result, zphabs_zpo_model, prefix='mo2'
        )

        # Add the fit results and contour plot data to the output DataFrame
        fit_result['step2d_labels'] = np.array(step2d_labels)
        fit_result['step2d_x'] = np.array(step2d_x)
        fit_result['step2d_y'] = np.array(step2d_y)
        fit_result['step2d_z'] = np.array(step2d_z)
        fit_result['statval'] = np.array(statval)
        fit_result['levelvals'] = levelvals

        try:
            fit_result = extract_errors_from_2d_contour(
                fit_result, ellipse_minmax, plot_savepath=''
            )
        except Exception as e:
            logging.error(f"Failed to extract 2d contours for {specname}: {e}")
            return None

        # fig = plt.figure(figsize=(6, 8))
        fig, ax3 = plt.subplots(figsize=(6, 6))

        colors = 'red'
        ls = '-'

        marker = 'o'
        s = 2

        # Filled contour
        ax3.contourf(
            step2d_x, step2d_y, step2d_z,
            np.append(levelvals - 2.71, levelvals),
            colors=colors, alpha=.05
        )
        # Empty contour

        ax3.contour(
            step2d_x, step2d_y, step2d_z,
            np.append(levelvals - 2.71, levelvals),
            colors=colors, linewidths=0.5, linestyles=ls
        )

        ax3.scatter(
            fit_result['mo2_nH_step_2d'],
            fit_result['mo2_PhoIndex_step_2d'], s=s, color='k',
            zorder=10, marker=marker
        )

        ax3.set_xlabel(r'$N_{\rm H}\ (10^{22})$')
        ax3.set_ylabel('Г')
        ax3.set_xscale('log')
        ax3.set_xlim(0.1, 10)
        ax3.set_ylim(0.3, 2.5)

        fig.suptitle(title, fontsize=12, y=.95)

        # Plot saving section
        if plot_path:
            try:
                # Ensure parent directory exists
                plot_path.parent.mkdir(parents=True, exist_ok=True)

                # Save plot directly to the provided path
                fig.savefig(plot_path, bbox_inches='tight', dpi=200)
                logging.info(f"Saving plot to: {plot_path}")
            except Exception as e:
                logging.error(f"Failed to save plot: {e}")

        return fit_result

    except Exception as e:
        logging.error(f"Error in fitting process: {e}")
        logging.error("Fit.steppar() failed")
        logging.error(traceback.format_exc())
        return None
