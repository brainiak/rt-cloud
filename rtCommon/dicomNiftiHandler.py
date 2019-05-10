# PURPOSE: anonmyize dicom data

import os
import glob
from shutil import copyfile
import pandas as pd
import json
import numpy as np
from subprocess import call
from rtCommon.utils import loadConfigFile
from rtCommon.structDict import StructDict
import time
import nilearn
from nilearn.masking import apply_mask
from nilearn.image import new_img_like
from scipy import stats
import scipy.io as sio
import pickle
#from greenEyes.greenEyes_main import initializeGreenEyes
from rtCommon.readDicom import *
import numpy as np  # type: ignore
from rtCommon.errors import StateError
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore
from nibabel.nicom import dicomreaders
from nilearn import image
import nibabel as nib
import matplotlib.pyplot as plt



def anonymizeDicom(dicomFilePath):
    """Read dicom + header, anonymize header"""
    dicomImg = readDicomFromFile(dicomFilePath)
    del dicomImg.PatientID
    del dicomImg.PatientAge
    del dicomImg.PatientBirthDate
    del dicomImg.PatientName
    del dicomImg.PatientSex
    del dicomImg.PatientSize
    del dicomImg.PatientWeight
    del dicomImg.PatientPosition
    return dicomImg

def saveAsNiftiImage(dicomDataObject,expected_dicom_name,cfg):
    #A = time.time()
    nameToSaveNifti = expected_dicom_name.split('.')[0] + '.nii.gz'
    tempNiftiDir = os.path.join(cfg.dataDir, 'tmp/convertedNiftis/')
    if not os.path.exists(tempNiftiDir):
        command = 'mkdir -pv {0}'.format(tempNiftiDir)
        call(command,shell=True)
    fullNiftiFilename = os.path.join(tempNiftiDir,nameToSaveNifti)
    niftiObject = dicomreaders.mosaic_to_nii(dicomDataObject)
    temp_data = niftiObject.get_data()
    #rounded_temp_data = np.round(temp_data)
    output_image_correct = nib.orientations.apply_orientation(temp_data,cfg.axesTransform)
    correct_object = new_img_like(cfg.ref_BOLD,output_image_correct,copy_header=True)
    correct_object.to_filename(fullNiftiFilename)
    #B = time.time()
    #print(B-A)
    return fullNiftiFilename


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





if __name__ == "__main__":
    # execute only if run as a script
    main()