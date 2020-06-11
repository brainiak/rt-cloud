"""-----------------------------------------------------------------------------

imageHandling.py (Last Updated: 05/27/2020)

This script includes all of the functions that are needed (1) to transfer dicom
files back and forth from the cloud and (2) to convert the dicom files to
nifti files, which is a file format that is better for data analyses.

-----------------------------------------------------------------------------"""

import os
import time
import logging
import numpy as np  # type: ignore
import nibabel as nib
import rtCommon.projectUtils as projUtils
from rtCommon.structDict import StructDict
from rtCommon.errors import StateError
from subprocess import call
from nilearn.image import new_img_like
from nibabel.nicom import dicomreaders
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore

"""-----------------------------------------------------------------------------

The following functions are used to transfer dicom files back and forth from the
cloud. We note whether a function is used externally (e.g., not exclusively by
other functions found in rtCommon) or internally.

-----------------------------------------------------------------------------"""

def getDicomFileName(cfg, scanNum, fileNum):
    """
    This function takes in different variables (which are both specific to the specific
    scan and the general setup for the entire experiment) to produce the full filename
    for the dicom file of interest.

    Used externally.
    """
    if scanNum < 0:
        raise ValidationError("ScanNumber not supplied of invalid {}".format(scanNum))

    # converting important info to strings
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(fileNum).zfill(3)

    # the naming pattern is provided in the toml file
    if cfg.dicomNamePattern is None:
        raise InvocationError("Missing config settings dicomNamePattern")
    fileName = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    fullFileName = os.path.join(cfg.dicomDir, fileName)

    return fullFileName

def anonymizeDicom(dicomImg):
    """
    This function takes in the dicom image that you read in and deletes
    lots of different variables. The purpose of this is to anonymize the
    dicom data before transferring it to the cloud.

    Used externally.
    """
    del dicomImg.PatientID
    del dicomImg.PatientAge
    del dicomImg.PatientBirthDate
    del dicomImg.PatientName
    del dicomImg.PatientSex
    del dicomImg.PatientSize
    del dicomImg.PatientWeight
    del dicomImg.PatientPosition
    del dicomImg.StudyDate
    del dicomImg.StudyTime
    del dicomImg.SeriesDate
    del dicomImg.SeriesTime
    del dicomImg.AcquisitionDate
    del dicomImg.AcquisitionTime
    del dicomImg.ContentDate
    del dicomImg.ContentTime
    del dicomImg.InstanceCreationDate
    del dicomImg.InstanceCreationTime
    del dicomImg.PerformedProcedureStepStartDate
    del dicomImg.PerformedProcedureStepStartTime
    return dicomImg

def readDicomFromFile(filename):
    """
    This function takes the path/name of the dicom file of interest and reads it.

    Used internally.
    """
    dicomImg = dicom.read_file(filename)
    return dicomImg

def writeDicomToBuffer(dicomImg):
    """
    This function write dicom data to binary mode so that it can be transferred
    to the cloud, where it again becomes a dicom. This is needed because files are
    transferred to the cloud in the following manner:
        dicom from scanner --> binary file  --> transfer to cloud --> dicom file

    Used internally.
    """
    dataBytesIO = dicom.filebase.DicomBytesIO()
    dicom.filewriter.write_file(dataBytesIO, dicomImg)
    dataBytesIO.seek(0)
    data = dataBytesIO.read()
    return data

def readDicomFromBuffer(data):
    """
    This function reads data that is in binary mode and then converts it into a
    structure that can be read as a dicom file. This is necessary because files are
    transferred to the cloud in the following manner:
        dicom from scanner --> binary file  --> transfer to cloud --> dicom file

    Use internally.
    """
    dataBytesIO = dicom.filebase.DicomBytesIO(data)
    dicomImg = dicom.dcmread(dataBytesIO)
    return dicomImg

def readRetryDicomFromFileInterface(fileInterface, filename, timeout=5):
    """
    This function is waiting and watching for a dicom file to be sent to the cloud
    from the scanner. It dodes this by calling the 'watchFile()' function in the
    'fileInterface.py'

    Used externally (and internally).
    """
    retries = 0
    while retries < 5:
        retries += 1
        try:
            data = fileInterface.watchFile(filename, timeout)
            # TODO - Inject error here and see if commpipe remains open
            dicomImg = readDicomFromBuffer(data)
            # check that pixel array is complete
            dicomImg.convert_pixel_data()
            # successful
            return dicomImg
        except Exception as err:
            logging.warning("LoadImage error, retry in 100 ms: {} ".format(err))
            time.sleep(0.1)
    return None

def parseDicomVolume(dicomImg, sliceDim):
    """
    The raw dicom file coming from the scanner will be a 2-dimensional picture
    made of up multiple image slices that are tiled together. This function
    separates the image slices to form a single volume.

    Used externally.
    """
    sliceWidth = sliceDim
    sliceHeight = sliceDim

    image = dicomImg.pixel_array

    dicomHeight, dicomWidth = image.shape
    numSlicesPerRow = dicomWidth // sliceWidth
    numSlicesPerCol = dicomHeight // sliceHeight

    max_slices = numSlicesPerRow * numSlicesPerCol
    volume = np.full((sliceWidth, sliceHeight, max_slices), np.nan)

    sliceNum = 0
    for row in range(numSlicesPerCol):
        for col in range(numSlicesPerRow):
            if sliceNum >= max_slices:
                raise StateError('parseDicomVolume: sliceNum {} exceeds max_slices {}'
                                 .format(sliceNum, max_slices))
            rpos = row * sliceHeight
            cpos = col * sliceWidth
            slice = image[rpos: rpos+sliceHeight, cpos: cpos+sliceWidth]
            volume[:, :, sliceNum] = slice
            sliceNum += 1
    return volume


"""-----------------------------------------------------------------------------

The following functions are used to convert dicom files into nifti files, which
can then be easily used in fMRI analyses. Again, we denote whether functions are
used externally or internally.

-----------------------------------------------------------------------------"""

## ANNE - is this the correct order in which these functions would be used?

def getAxesForTransform(startingDicomFile,cfg):
    """
    This function takes a single dicom file (which can be the first file) and
    the config file to obtain the target_orientation (in nifti space) and the
    dicom_orientation (in the original space).

    NOTE: You only need to run this function once to obtain the target and
    dicom orientations. You can save and load these variables so that
    'getTransform()' is hard coded.

    Used externally.
    """
    #Load one example file
    nifti_object = nib.load(cfg.ref_BOLD)
    target_orientation = nib.aff2axcodes(nifti_object.affine)
    dicom_object = getLocalDicomData(cfg,startingDicomFile)
    dicom_object = dicomreaders.mosaic_to_nii(dicom_object)
    dicom_orientation = nib.aff2axcodes(dicom_object.affine)
    return target_orientation,dicom_orientation

def getTransform(target_orientation,dicom_orientation):
    """
    This function calculates the right transformation needed to go from the original
    axis space (dicom_orientation) to the target axis space in nifti space
    (target_orientation).

    Used externally.
    """
    target_orientation_code = nib.orientations.axcodes2ornt(target_orientation)
    dicom_orientation_code = nib.orientations.axcodes2ornt(dicom_orientation)
    transform = nib.orientations.ornt_transform(dicom_orientation_code, target_orientation_code)
    return transform

def saveAsNiftiImage(dicomDataObject, fullNiftiFilename, cfg, reference):
    """
    This function takes in a dicom data object written in bytess, what you expect
    the dicom file to be called (we will use the same name format for the nifti
    file), and the config file while will have (1) the axes transformation for the
    dicom file and (2) the header information from a reference scan.

    Used externally.
    """
    niftiObject = dicomreaders.mosaic_to_nii(dicomDataObject)
    temp_data = niftiObject.get_fdata()
    output_image_correct = nib.orientations.apply_orientation(temp_data, cfg.axesTransform)
    correct_object = new_img_like(reference, output_image_correct, copy_header=True)
    correct_object.to_filename(fullNiftiFilename)
    return fullNiftiFilename
