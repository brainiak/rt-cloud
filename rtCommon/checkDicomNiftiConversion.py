"""-----------------------------------------------------------------------------

checkDicomNiftiConversion.py (Last Updated: 05/26/2020)

The purpose of this script is to check that the nifti file conversion done during
real-time in the cloud matches the nifti conversion done during your offline
analyses, assuming you used heudiconv or you directly called 'dcm2nix()'.
This script addresses the warning you get when you import pydicom.

To run this script, uncomment the lines in 'def main()' below. Complete the
sections that need to be filled in, denoted by "[FILL IN]"'". Save this file
and then run the script "python checkDicomNiftiConversion.py" in the terminal.

-----------------------------------------------------------------------------"""

import os
import glob
import nibabel as nib
import numpy as np
from rtCommon.imageHandling import saveAsNiftiImage, getAxesForTransform, \
    getTransform, readDicomFromFile


def checkingDicomNiftiConversion(cfg):
    """
    Purpose: check the nibabel nifti/dicom conversion method BEFORE using it in
    real-time.
    Here we're assuming you have raw dicoms and the corresponding converted nifti that you
    used in pilot data collection.

    STEPS:
        0. set up config
        1. get number of TRs from dicom path and nifti path
        2. go through each TR in dicom, convert them each to niftis and save
        3. load in each nifti into new data matrix
        4. compare this to loaded offline nifti file
    """
    complete_path = os.path.join(cfg.dicomDir,cfg.dicomNamePattern).format('*')
    all_dicoms = glob.glob(complete_path)
    sorted_dicom_list = sorted(all_dicoms, key=lambda x: int("".join([i for i in x if i.isdigit()])))
    target_orientation, dicom_orientation = getAxesForTransform(sorted_dicom_list[0],cfg)
    cfg.axesTransform = getTransform(target_orientation, dicom_orientation)
    nTRs_dicom = len(sorted_dicom_list)
    nifti_image = nib.load(cfg.niftiFile)
    nifti_data = nifti_image.get_fdata()
    nTRs_nifti = np.shape(nifti_data)[-1]
    image_shape = np.shape(nifti_data)
    # check that the number of TRs are the same
    print('Step 1: Verifying dicom and nifti data match # TRs')
    if nTRs_dicom != nTRs_nifti:
        print('WARNING: number of dicoms don''t match! Check your files again!')
    else:
        nTR = nTRs_dicom
        print('TR numbers match!')
    # now read in each dicom
    print('Step 2: Saving dicoms as nifti files')
    full_nifti_name = [None]*nTR
    for trIndex in np.arange(nTR):
        print(trIndex)
        dicomData = readDicomFromFile(sorted_dicom_list[trIndex])
        expected_dicom_name = sorted_dicom_list[trIndex].split('/')[-1]
        full_nifti_name[trIndex] = saveAsNiftiImage(dicomData, expected_dicom_name, cfg, cfg.ref_BOLD)
    # now load in each nifti and create new matrix
    print('Step 3: Reading in the saved dicoms')
    dicom_data = np.zeros(image_shape)
    for trIndex in np.arange(nTR):
        dicom_object = nib.load(full_nifti_name[trIndex])
        dicom_data[:,:,:,trIndex] = dicom_object.get_fdata()
    # now check if there's any value that's different
    print('Step 4: Verifying the saved dicoms match the offline Nifti created')
    different_values = np.argwhere(dicom_data != nifti_data)
    if len(different_values) == 0:
        PASSED = 1
    elif len(different_values) > 0:
        PASSED = 0
    return PASSED


def main():
    pass
    # cfg = StructDict() # initialize empty dictionary
    # cfg.dataDir = os.getcwd() # or change to any directory where you want the tmp/convertedNiftis to go
    # cfg.ref_BOLD = [FILL IN] # reference image saved as a nifti file after undergoing fMRIprep
    # cfg.dicomDir = [FILL IN] # directory where the dicoms get save (on the stimulus computer)
    # cfg.dicomNamePattern = [FILL IN] # the naming pattern for the dicom files,
    # # which should include the specific series/scan number of the scanner '9-{}-1.dcm'
    # cfg.niftiFile =  [FILL IN] # the full path from the nifti file for that run (assuming you
    # # already did heudiconv)
    # PASSFAIL = checkingDicomNiftiConversion(cfg)
    # print('Checking Conversion Outcome:', PASSFAIL)


if __name__ == "__main__":
    # execute only if run as a script
    main()
