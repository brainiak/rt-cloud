# purpose: resample images in quick function

import numpy as numpy
import nibabel
import nilearn
from nilearn.image import resample_to_img
import matplotlib.pyplot as pyplot
from nilearn import plotting
from nilearn.plotting import show
from nilearn.plotting import plot_roi
from nilearn import image
from nilearn.image import load_img
import sys

# purpose of functions - take in image to resize, reference image
# resave as resampled image

image_to_resample=sys.argv[1]
image_reference=sys.argv[2]

# first resample - change interpolation strategy if you would like
resampled_image = resample_to_img(image_to_resample,image_reference,interpolation='nearest')
# save as resampled
if 'gz' in image_to_resample:
    # go back that many characters
    base_name = image_to_resample[0:-7]
    save_name = base_name + '_resampled' + '.nii.gz'
else: # gzipped nifti
    base_name = image_to_resample[0:-4]
    save_name = base_name + '_resampled' + '.nii'
# now save
resampled_image.to_filename(save_name)