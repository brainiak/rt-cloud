"""
This script includes all of the functions that are needed (1) to transfer dicom
files back and forth from the cloud and (2) to convert the dicom files to
nifti files, which is a file format that is better for data analyses.
"""

import os
import time
import copy
import uuid
import logging
import subprocess
import warnings
import numpy as np  # type: ignore
import nibabel as nib
import pydicom
from datetime import datetime
from rtCommon.utils import getTimeToNextTR
from rtCommon.errors import StateError, ValidationError
from rtCommon.errors import InvocationError, RequestError
from nilearn.image import new_img_like
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning)
    from nibabel.nicom import dicomreaders
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore

# binary path of the conda environment
binPath = None

###########
# The following functions are used to transfer dicom files back and forth from the
# cloud. We note whether a function is used externally (e.g., not exclusively by
# other functions found in rtCommon) or internally.
###########

def getDicomFileName(cfg, scanNum, fileNum):
    """
    This function takes in different variables (which are both specific to the specific
    scan and the general setup for the entire experiment) to produce the full filename
    for the dicom file of interest.

    Used externally.
    """
    if scanNum < 0:
        raise ValidationError("ScanNumber not supplied or invalid {}".format(scanNum))

    # the naming pattern is provided in the toml file
    if cfg.dicomNamePattern is None:
        raise InvocationError("Missing config settings dicomNamePattern")

    if '{TR' in cfg.dicomNamePattern:
        fileName = cfg.dicomNamePattern.format(SCAN=scanNum, TR=fileNum)
    else:
        scanNumStr = str(scanNum).zfill(2)
        fileNumStr = str(fileNum).zfill(3)
        fileName = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    fullFileName = os.path.join(cfg.dicomDir, fileName)

    return fullFileName

# Note: don't anonymize AcquisitionTime, needed to sync with TR
attributesToAnonymize = [
        'PatientID', 'PatientAge', 'PatientBirthDate', 'PatientName',
        'PatientSex', 'PatientSize', 'PatientWeight', 'PatientPosition',
        'StudyDate', 'StudyTime', 'SeriesDate', 'SeriesTime',
        'AcquisitionDate', 'ContentDate', 'ContentTime',
        'InstanceCreationDate', 'InstanceCreationTime',
        'PerformedProcedureStepStartDate', 'PerformedProcedureStepStartTime'
]

def anonymizeDicom(dicomImg):
    """
    This function takes in the dicom image that you read in and deletes
    lots of different attributes. The purpose of this is to anonymize the
    dicom data before transferring it to the cloud.

    Used externally.
    """
    for toAnonymize in attributesToAnonymize:
        if hasattr(dicomImg, toAnonymize):
            setattr(dicomImg, toAnonymize, "")

    return dicomImg

def readDicomFromFile(filename):
    """
    This function takes the path/name of the dicom file of interest and reads it.

    Used internally.
    """
    dicomImg = dicom.read_file(filename)
    return dicomImg


def writeDicomFile(dicomImg, filename):
    """
    This function takes a dicomImg and the path/name of the file to write to.

    Used internally.
    """
    dicomImg.save_as(filename)
    return


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


def readDicomFromBuffer(data) -> pydicom.dataset.FileDataset:
    """
    This function reads data that is in binary mode and then converts it into a
    structure that can be read as a dicom file. This is necessary because files are
    transferred to the cloud in the following manner:
    dicom from scanner --> binary file  --> transfer to cloud --> dicom file

    Use internally.
    """
    dataBytesIO = dicom.filebase.DicomBytesIO(data)
    try:
        dicomImg = dicom.dcmread(dataBytesIO)
        # Test if the dicom image is complete
        dicomImgTest = copy.deepcopy(dicomImg)
        dicomImgTest.convert_pixel_data()
    except Exception as err:
        raise ValidationError(f"readDicomFromBuffer: Dicom may be corrupted or truncated {err}")
    return dicomImg


def readRetryDicomFromDataInterface(dataInterface, filename, timeout=5):
    """
    This function is waiting and watching for a dicom file to be sent to the cloud
    from the scanner. It dodes this by calling the 'watchFile()' function in the
    'dataInterface.py'

    Used externally (and internally).
    Args:
        dataInterface: A dataInterface to make calls on
        filename: Dicom filename to watch for and read when available
        timeout: Max number of seconds to wait for file to be available
    Returns:
        The dicom image
    """
    if timeout <= 0:
        # Don't allow infinite timeout
        raise RequestError("readRetryDicomFromDataInterface: "
                           "timeout parameter must be > 0 secs")

    loop_timeout = 5  # 5 seconds per loop
    time_remaining = timeout
    while time_remaining > 0:
        if time_remaining < loop_timeout:
            loop_timeout = time_remaining
        try:
            data = dataInterface.watchFile(filename, loop_timeout)
            dicomImg = readDicomFromBuffer(data)
            # check that pixel array is complete
            dicomImg.convert_pixel_data()
            # successful
            return dicomImg
        except TimeoutError as err:
            logging.info(f"Waiting for {filename} ...")
        except Exception as err:
            logging.error(f"ReadRetryDicom Error, filename {filename} err: {err}")
            return None
        time_remaining -= loop_timeout
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


def getDicomAcquisitionTime(dicomImg) -> datetime.time:
    """
    Returns the acquisition time as a datetime.time
    Note: day, month and year are not specified
    """
    acqTm = dicomImg.get('AcquisitionTime', None)
    if acqTm is None:
        return None
    dtm = datetime.strptime(acqTm, '%H%M%S.%f')
    return dtm.time()

def getDicomRepetitionTime(dicomImg) -> float:
    """Returns the TR repetition time in seconds"""
    repTm = dicomImg.get('RepetitionTime', None)
    if repTm is None:
        return None
    tr_sec = float(repTm) / 1000
    return tr_sec

def dicomTimeToNextTr(dicomImg, clockSkew, now=None):
    """Based on Dicom header. Returns seconds to next TR start"""
    acquisitionTime = getDicomAcquisitionTime(dicomImg)
    repetitionTime = getDicomRepetitionTime(dicomImg)
    if now is None:  # now variable may be passed in for testing purposes
        now = datetime.now().time()
    secToNextTr = getTimeToNextTR(acquisitionTime, repetitionTime, now, clockSkew)
    return secToNextTr

def bidsIncrementalTimeToNextTr(bidsIncremental, clockSkew, now=None):
    """Based on BidsIncremental header. Returns seconds to next TR start"""
    acqTimestamp = bidsIncremental.getMetadataField('AcquisitionTime')
    acquisitionTime = None
    if acqTimestamp is not None:
        dtm = datetime.strptime(acqTimestamp, '%H%M%S.%f')
        acquisitionTime = dtm.time()
    repetitionTime = bidsIncremental.getMetadataField('RepetitionTime')
    if now is None:  # now variable may be passed in for testing purposes
        now = datetime.now().time()
    secToNextTr = getTimeToNextTR(acquisitionTime, repetitionTime, now, clockSkew)
    return secToNextTr

###########
# The following functions are used to convert dicom files into nifti files, which
# can then be easily used in fMRI analyses. Again, we denote whether functions are
# used externally or internally.
###########

## ANNE - is this the correct order in which these functions would be used?

def getAxesForTransform(startingDicomFile, cfg):
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
    dicom_object = readDicomFromFile(startingDicomFile)
    dicom_object = dicomreaders.mosaic_to_nii(dicom_object)
    dicom_orientation = nib.aff2axcodes(dicom_object.affine)
    return target_orientation,dicom_orientation


def getTransform(target_orientation, dicom_orientation):
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
    This function takes in a dicom data object written in bytes, what you expect
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


def convertDicomFileToNifti(dicomFilename, niftiFilename):
    global binPath
    if binPath is None:
        # Used to use 'which python' to find the conda env path
        result = subprocess.run(['which', 'dcm2niix'], stdout=subprocess.PIPE)
        binPath = result.stdout.decode('utf-8')
        binPath = os.path.dirname(binPath)
    dcm2niiCmd = os.path.join(binPath, 'dcm2niix')
    outPath, outName = os.path.split(niftiFilename)
    if outName.endswith('.nii'):
        outName = os.path.splitext(outName)[0]  # remove extention
    cmd = [dcm2niiCmd, '-s', 'y', '-b', 'n', '-o', outPath, '-f', outName,
           dicomFilename]
    proc = subprocess.run(cmd, shell=False, stdout=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise StateError("Failed to convert Dicom to Nifti. Dicom may be corrupted")



def niftiToMem(niftiImg):
    '''
    Fully load Nifti image into memory and remove any file-backing.
    NiftiImage by default contains a pointer to the image file for the data.
    '''
    niftiBytes = niftiImg.to_bytes()
    niftiMemImg = niftiImg.__class__.from_bytes(niftiBytes)
    return niftiMemImg


def readNifti(niftiFilename, memCached=True):
    niftiImg = nib.load(niftiFilename)
    # When memCached is True we want to load the image all in memory so, for example,
    #   it can be sent remotely.
    if memCached is True:
        niftiImg = niftiToMem(niftiImg)
    return niftiImg


def convertDicomImgToNifti(dicomImg, dicomFilename=None):
    '''
    Given an in-memory dicomImg, convert it to an in-memory niftiImg. 
    Note: due to how nibabel niftiImage works, it is just a pointer to a file
    on disk, so we can't delete the niftiFile while niftiImage is in use.
    '''
    if dicomFilename is None:
        dicomFilename = os.path.join('/tmp', 'tmp_nifti_' + uuid.uuid4().hex + '.dcm')
    writeDicomFile(dicomImg, dicomFilename)
    # swap .dcm extension with .nii extension
    base, ext = os.path.splitext(dicomFilename)
    assert ext == '.dcm'
    niftiFilename = base + '.nii'
    # concvert dicom file to nifti file
    convertDicomFileToNifti(dicomFilename, niftiFilename)
    niftiImg = readNifti(niftiFilename)
    # cleanup the tmp files created
    os.remove(dicomFilename)
    os.remove(niftiFilename)
    return niftiImg
