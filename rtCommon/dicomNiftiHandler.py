# PURPOSE: anonmyize dicom data

import os
import glob
from subprocess import call
from nilearn.image import new_img_like
from nibabel.nicom import dicomreaders
import nibabel as nib
import numpy as np
from rtCommon.readDicom import readDicomFromBuffer, readRetryDicomFromFileInterface
from rtCommon.fileClient import FileInterface
import rtCommon.projectUtils as projUtils
from rtCommon.structDict import StructDict

def saveAsNiftiImage(dicomDataObject, fullNiftiFilename, cfg, reference):
    niftiObject = dicomreaders.mosaic_to_nii(dicomDataObject)
    temp_data = niftiObject.get_fdata()
    output_image_correct = nib.orientations.apply_orientation(temp_data, cfg.axesTransform)
    correct_object = new_img_like(reference, output_image_correct, copy_header=True)
    correct_object.to_filename(fullNiftiFilename)
    return fullNiftiFilename

def getAxesForTransform(startingDicomFile,cfg):
    """ Load one example file """
    nifti_object = nib.load(cfg.ref_BOLD)
    target_orientation = nib.aff2axcodes(nifti_object.affine)
    dicom_object = getLocalDicomData(cfg,startingDicomFile)
    dicom_object = dicomreaders.mosaic_to_nii(dicom_object)
    dicom_orientation = nib.aff2axcodes(dicom_object.affine)
    return target_orientation,dicom_orientation # from here you can save and load it so getTransform is hard coded --you only need to run this once

def getTransform(target_orientation,dicom_orientation):
    target_orientation_code = nib.orientations.axcodes2ornt(target_orientation)
    dicom_orientation_code = nib.orientations.axcodes2ornt(dicom_orientation)
    transform = nib.orientations.ornt_transform(dicom_orientation_code,target_orientation_code)
    return transform

def getLocalDicomData(cfg,fullpath):
    projComm = projUtils.initProjectComm(None,False)
    fileInterface = FileInterface(filesremote=False,commPipes=projComm)
    fileInterface.initWatch(cfg.dicomDir,cfg.dicomNamePattern,300000)
    dicomData = readRetryDicomFromFileInterface(fileInterface,fullpath)
    return dicomData

def checkDicomNiftiConversion(cfg):
    """Purpose: check the nibabel nifti/dicom conversion method BEFORE using it in real-time.
    Here we're assuming you have raw dicoms and the corresponding converted nifti that you 
    used in pilot data collection."""

    # STEPS:
    # 0. set up config
    # 1. get number of TRs from dicom path and nifti path
    # 2. go through each TR in dicom, convert them each to niftis and save
    # 3. load in each nifti into new data matrix
    # 4. compare this to loaded offline nifti file
    complete_path = os.path.join(cfg.dicomDir,cfg.dicomNamePattern).format('*')
    all_dicoms = glob.glob(complete_path)
    sorted_dicom_list = sorted(all_dicoms, key=lambda x: int("".join([i for i in x if i.isdigit()])))
    target_orientation,dicom_orientation = getAxesForTransform(sorted_dicom_list[0],cfg)
    cfg.axesTransform = getTransform(target_orientation,dicom_orientation)
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
        dicomData = getLocalDicomData(cfg,sorted_dicom_list[trIndex])
        expected_dicom_name = sorted_dicom_list[trIndex].split('/')[-1]
        full_nifti_name[trIndex] = saveAsNiftiImage(dicomData,expected_dicom_name,cfg)
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
    # example below how to use this code
    # you have to make sure you have certain files in the config file**

    # configFile = 'greenEyes.toml'
    # cfg = initializeGreenEyes(configFile)
    # scanNum = 9
    # TRnum = 11
    # expected_dicom_name = cfg.dicomNamePattern.format(scanNum,TRnum)
    # full_dicom_name = '{0}{1}'.format(cfg.subjectDcmDir,expected_dicom_name)

    # dicomImg = anonymizeDicom(full_dicom_name)
    # saveAsNiftiImage(dicomImg,expected_dicom_name,cfg)

    # # TEST EXACTLY THE SAME
    # f1 = '/jukebox/norman/amennen/github/brainiak/rtAttenPenn/greenEyes/tmp/convertedNiftis/9-11-1.nii.gz'
    # f2 = '/jukebox/norman/amennen/github/brainiak/rtAttenPenn/greenEyes/data/sub-102/ses-02/converted_niftis/9-11-1.nii.gz'

    # obj_1 = nib.load(f1)
    # obj_2 = nib.load(f2)
    # d_1 = obj_1.get_fdata()
    # d_2 = obj_2.get_fdata()

    # np.argwhere(d_1!=d_2)

    cfg = StructDict()
    # cfg.dataDir = os.getcwd() # or change to any directory where you want the tmp/convertedNiftis to go
    # cfg.ref_BOLD = # YOUR REFERNECE IMAGE
    # cfg.dicomDir = # YOUR DICOM DIRECTORY
    # cfg.dicomNamePattern = # DICOM PATTERN FOR THE SPECIFIC SERIES/RUN OF THE SCANNER (e.g, 9) THAT YOU'RE TESTING '9-{}-1.dcm' 
    # cfg.niftiFile =  # FULL NIFTI PATH AND FILENAME FOR THE CORRESPONDING NIFTI FILE CREATED FROM THE SAME RUN
    #PASSFAIL = checkDicomNiftiConversion(cfg)


if __name__ == "__main__":
    # execute only if run as a script
    main()
