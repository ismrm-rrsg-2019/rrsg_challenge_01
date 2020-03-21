#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Apr 1 2019

@author: omaier

Copyright 2019 Oliver Maier

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""


import numpy as np
import os
import h5py
import argparse
from rrsg_cgreco._helper_fun import goldcomp as goldcomp
from rrsg_cgreco._helper_fun.est_coils import estimate_coil_sensitivities
import rrsg_cgreco.linop as linop
import rrsg_cgreco.solver as solver

DTYPE = np.complex64
DTYPE_real = np.float32


def _get_args(
      config='default',
      inscale=True,
      denscor=True,
      data='rawdata_brain_radial_96proj_12ch.h5',
      acc=1,
      ogf='1.706'
      ):
    """
    Parse command line arguments.

    Args
    ----
        config (string):
            Name of config file to use (default).
            The file is assumed to be in the same folder where the script is
            run. If not specified, use default parameters.

        inscale (bool):
            Wether to perform intensity scaling. Defaults to True.

        denscor (bool):
            Switch to choose between reconstruction with (True) or
            without (False) density compensation. Defaults to True.

        data (string):
            Full qualified path to the h5 data file.

        acc (int):
            Desired acceleration compared to the number of
            spokes provided in data.
            E.g. 1 uses all available spokes 2 every 2nd.

        ogf (string):
            Ratio between Cartesian cropped grid and full
            regridded k-space grid.

    Returns
    -------
        The parsed arguments as argparse object
    """
    parser = argparse.ArgumentParser(description='CG Sense Reconstruction')
    parser.add_argument(
        '--config', default=config, dest='config',
        help='Name of config file to use (assumed to be in the same folder). '
        'If not specified, use default parameters.'
        )
    parser.add_argument(
        '--inscale', default=inscale, type=int, dest='inscale',
        help='Perform Intensity Scaling.'
        )
    parser.add_argument(
        '--denscor', default=denscor, type=int, dest='denscor',
        help='Perform density correction.'
        )
    parser.add_argument(
        '--data', default=data, dest='data',
        help='Path to the h5 data file.'
        )
    parser.add_argument(
        '--acc', default=acc, type=int, dest='acc',
        help='Desired acceleration factor.'
        )
    parser.add_argument(
        '--ogf', default=ogf, type=str, dest='ogf',
        help='Overgridfactor. 1.706 for Brain, 1+1/3 for heart data.'
        )
    args = parser.parse_args()
    return args


def run(
      config='default',
      inscale=True,
      denscor=True,
      data='rawdata_brain_radial_96proj_12ch.h5',
      acc=1,
      ogf='1.706'
      ):
    """
    Run the CG reco of radial data.

    Args
    ----
        config (string):
            Name of config file to use (default).
            The file is assumed to be in the same folder where the script
            is run. If not specified, use default parameters.

        inscale (bool):
            Wether to perform intensity scaling. Defaults to True.

        denscor (bool):
            Switch to choose between reconstruction with (True) or
            without (False) density compensation. Defaults to True.

        data (string):
            Full qualified path to the h5 data file.

        acc (int):
             Desired acceleration compared to the number of
             spokes provided in data.
             E.g. 1 uses all available spokes 2 every 2nd.

        ogf (string):
            Ratio between Cartesian cropped grid and full regridded
            k-space grid.
    """
    args = _get_args(
        config,
        inscale,
        denscor,
        data,
        acc,
        ogf
        )
    _run_reco(args)


def read_data(
      path,
      acc,
      data_rawdata_key='rawdata',
      data_trajectory_key='trajectory',
      noise_key='noise'
      ):
    """
    Handle data and possible undersampling.

    Reading in h5 data from the path variable.
    Apply undersampling if specified.
    It is assumed that the data is saved as complex
    valued entry named "rawdata".
    The corresponding measurement trajectory is also saved as complex valued
    entry named "trajectory"

    Args
    ----
        path (string):
            Full qualified path to the .h5 data file.
        acc (int):
            Desired acceleration compared to the number of
            spokes provided in data.
            E.g. 1 uses all available spokes 2 every 2nd.
        par (dict):
            Dictionary for storing data and parameters.
    Retruns
    -------
        rawdata (np.complex64):
            The rawdata array
        trajectory (np.complex64):
            The k-space trajectory
    Raises
    ------
         ValueError:
             If no data file is specified
    """
    if not os.path.isfile(path):
        raise ValueError("Given path is not an existing file.")

    name = os.path.normpath(path)
    with h5py.File(name, 'r') as h5_dataset:
        if "heart" in name:
            if acc == 2:
                trajectory = h5_dataset[data_trajectory_key][:, :, :33]
                rawdata = h5_dataset[data_rawdata_key][:, :, :33, :]
            elif acc == 3:
                trajectory = h5_dataset[data_trajectory_key][:, :, :22]
                rawdata = h5_dataset[data_rawdata_key][:, :, :22, :]
            elif acc == 4:
                trajectory = h5_dataset[data_trajectory_key][:, :, :11]
                rawdata = h5_dataset[data_rawdata_key][:, :, :11, :]
            else:
                trajectory = h5_dataset[data_trajectory_key][...]
                rawdata = h5_dataset[data_rawdata_key][...]
        else:
            trajectory = h5_dataset[data_trajectory_key][:, :, ::acc]
            rawdata = h5_dataset[data_rawdata_key][:, :, ::acc, :]
        if noise_key in h5_dataset.keys():
            noise_scan = h5_dataset[noise_key][()]
        else:
            noise_scan = None

    # Squeeze dummy dimension and transpose to C-style ordering.
    rawdata = np.squeeze(rawdata.T)

    # Normalize trajectory to the range of (-1/2)/(1/2)
    norm_trajectory = 2 * np.max(trajectory[0])

    trajectory = (
      np.require(
        (
            trajectory[0] / norm_trajectory
            + 1j *
            trajectory[1] / norm_trajectory
            )
        .T,
        requirements='C'
        )
      )

    # TODO Shouldnt we use a standard amount of dimensions right from the start?
    # e.g. [num_scans, num_coils, num_slc, grid_size, grid_size]
    # And something similar for trajectories?
    # Or at least exlain why we are adding a third dimension here.
    if trajectory.ndim < 3:
        trajectory = trajectory[None, ...]

    return rawdata, trajectory, noise_scan


def setup_parameter_dict(
      rawdata,
      traj,
      ogf,
      traj_type='radial'
      ):
    """
    Parameter dict generation.

    Args
    ----
        rawdata (np.complex64):
            The raw k-space data
        ogf (string):
            Over-gridding factor. Ratio between Cartesian cropped grid and full
            regridded k-space grid.

    Returns
    -------
        par (dict):
            A dictionary storing reconstruction related parameters like
            number of coils and image dimension in 2D.
    """
    # Create empty dict
    par = {}
    [n_ch, n_spokes, num_reads] = rawdata.shape

    par["ogf"] = float(eval(ogf))
    dimX, dimY = [int(num_reads/par["ogf"]), int(num_reads/par["ogf"])]

    # Calculate density compensation for radial data.
    #############
    # This needs to be adjusted for spirals!!!!!
    #############
    par["dens_cor"] = (
        np.sqrt(
            np.array(
                goldcomp.get_golden_angle_dcf(traj),
                dtype=DTYPE_real
                )
            )
        .astype(DTYPE_real)
        )
    par["dens_cor"] = (
        np.require(
            np.abs(par["dens_cor"]),
            DTYPE_real,
            requirements='C'
            )
        )

    par["num_coils"] = n_ch
    par["dimY"] = dimY
    par["dimX"] = dimX
    par["num_reads"] = num_reads
    par["num_proj"] = n_spokes
    par["num_scans"] = 1
    par["num_slc"] = 1

    return par


def save_to_file(
      result,
      args
      ):
    """
    Save the reconstruction result to a h5 file.

    Args
    ----
      result (np.complex64):
        The reconstructed complex images to save.
      args (ArgumentParser):
         Console arguments passed to the script.
    """
    outdir = ""
    if "heart" in args.data:
        outdir += "/heart"
    elif "brain" in args.data:
        outdir += "/brain"
    if not os.path.exists('./output'):
        os.makedirs('output')
    if not os.path.exists('./output' + outdir):
        os.makedirs("./output" + outdir)
    cwd = os.getcwd()
    os.chdir("./output" + outdir)
    f = h5py.File(
        "CG_reco_inscale_" + str(args.inscale) + "_denscor_"
        + str(args.denscor) + "_reduction_" + str(args.acc)
        + "_acc_" + str(args.acc) + ".h5",
        "w"
        )
    f.create_dataset(
        "CG_reco",
        result.shape,
        dtype=DTYPE,
        data=result
        )
    f.flush()
    f.close()
    os.chdir(cwd)


def _decor_noise(data, noise, par):
    if noise is None:
        return data
    else:
        cov = np.cov(noise)
        L = np.linalg.cholesky(cov)
        invL = np.linalg.inv(L)
        data = np.reshape(data, (par["num_coils"], -1))
        data = invL@data
        data = np.reshape(data,
                          (par["num_coils"],
                           par["num_proj"],
                           par["num_reads"]))
        return data


def _run_reco(args):
    # Read input data
    rawdata, trajectory, noise = read_data(args.data, args.acc)
    # Setup parameters
    par = setup_parameter_dict(rawdata, trajectory, args.ogf)
    # Decorrelate Coil channels if noise scan is present
    rawdata = _decor_noise(rawdata, noise, par)
    # Get coil sensitivities in the parameter dict
    estimate_coil_sensitivities(rawdata, trajectory, par)
    # Get operator
    MRImagingOperator = linop.MRIImagingModel(par, trajectory)
    cgs = solver.CGReco(par)
    cgs.set_operator(MRImagingOperator)
    # Start reconstruction
    # Data needs to be multiplied with the sqrt of dense_cor to assure that
    # forward and adjoint application of the NUFFT is adjoint with each other.
    # dens_cor itself is save din the par dict as the sqrt.
    recon_result = cgs.optimize(data=rawdata * par["dens_cor"])
    # Store results
    save_to_file(recon_result, args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CG Sense Reconstruction')
    parser.add_argument(
        '--config', default='default', dest='config',
        help='Name of config file to use (assumed to be in the same folder). '
             'If not specified, use default parameters.'
             )
    parser.add_argument(
        '--inscale', default=1, type=int, dest='inscale',
        help='Perform Intensity Scaling.'
        )
    parser.add_argument(
        '--denscor', default=1, type=int, dest='denscor',
        help='Perform density correction.'
        )
    parser.add_argument(
        '--data', default='rawdata_brain_radial_96proj_12ch.h5', dest='data',
        help='Path to the h5 data file.'
        )
    parser.add_argument(
        '--acc', default=1, type=int, dest='acc',
        help='Desired acceleration factor.'
        )
    parser.add_argument(
        '--ogf', default='1.706', type=str, dest='ogf',
        help='Overgridfactor. 1.706 for Brain, 1+1/3 for heart data.'
        )
    args = parser.parse_args()
    _run_reco(args)
