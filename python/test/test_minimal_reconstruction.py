"""
Here we show a very minimal effort way to reconstruct an image using this module...
"""

import os
import matplotlib.pyplot as plt
import scipy.io
import rrsg_cgreco.recon as recon

# First.. define data paths
data_path = '/media/bugger/UBUNTU 20_0/data/v9_24012021_1241182_7_2_transradialfastV4_data.mat'
om_path = '/media/bugger/UBUNTU 20_0/data/v9_24012021_1241182_7_2_transradialfastV4_trajectory.mat'
image_path = '/media/bugger/UBUNTU 20_0/data/v9_24012021_1241182_7_2_transradialfastV4_25_image.mat'
default_config_path = os.path.expanduser('~/PycharmProjects/rrsg_challenge_01/python/default.txt')

#   And load the data...
A_img = scipy.io.loadmat(image_path)['one_slice']
A = scipy.io.loadmat(data_path)['data_array'][:, :, 0, 0, 0, 0]
A_traj = scipy.io.loadmat(om_path)['trajectory_array'][:, :, 0, :2]

# Secondly.. get a default config
derp = recon.setup_parameter_dict(default_config_path, rawdata=A_img, trajectory=A_traj)

# Thirdly.. reconstruct the image





