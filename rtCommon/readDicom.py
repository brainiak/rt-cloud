import os
import time
import logging
import numpy as np  # type: ignore
from rtCommon.errors import StateError
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore
# import glob
# from subprocess import call
# from nilearn.image import new_img_like
# from nibabel.nicom import dicomreaders
# import nibabel as nib
# import numpy as np
# from rtCommon.readDicom import readDicomFromBuffer, readRetryDicomFromFileInterface
# from rtCommon.fileClient import FileInterface
# import rtCommon.projectUtils as projUtils
# from rtCommon.structDict import StructDict


"""-----------------------------------------------------------------------------

The following functions can be used to read the dicom files that are coming in
from the scanner. 

-----------------------------------------------------------------------------"""

def parseDicomVolume(dicomImg, sliceDim):
    """
    The raw dicom file coming from the scanner will be a 2-dimensional picture
    made of up multiple image slices that are tiled together. This function 
    separates the image slices to form a single volume.
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


def readDicomFromBuffer(data):
    """
    ANNE - what does this do?
    """
    dataBytesIO = dicom.filebase.DicomBytesIO(data)
    dicomImg = dicom.dcmread(dataBytesIO)
    return dicomImg


def readDicomFromFile(filename):
    """
    This function takes the path/name of the dicom file of interest and reads it.
    """
    dicomImg = dicom.read_file(filename)
    return dicomImg


def readRetryDicomFromFileInterface(fileInterface, filename, timeout=5):
    """
    This function is waiting and watching for a dicom file to be sent to the cloud 
    from the scanner. It dodes this by calling the 'watchFile()' function in the
    'fileInterface.py' 
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


def applyMask(volume, roiInds):
    """
    ANNE - what does this do?
    """
    # maskedVolume = np.zeros(volume.shape, dtype=float)
    # maskedVolume.flat[roiInds] = volume.flat[roiInds]
    maskedVolume = volume.flat[roiInds]
    return maskedVolume


def anonymizeDicom(dicomImg):
    """
    This function takes in the dicom image that you read in and deletes
    lots of different variables. The purpose of this is to anonymize the
    dicom data before transferring it to the cloud.
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

def writeDicomToBuffer(dicomImg):
    """
    ANNE - what does this do?
    """
    dataBytesIO = dicom.filebase.DicomBytesIO()
    dicom.filewriter.write_file(dataBytesIO, dicomImg)
    dataBytesIO.seek(0)
    data = dataBytesIO.read()
    return data

def getDicomFileName(cfg, scanNum, fileNum):
    """
    This function takes in different variables (which are both specific to the specific
    scan and the general setup for the entire experiment) to produce the full filename
    for the dicom file of interest.
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

"""-----------------------------------------------------------------------------

The following functions can be used to read the dicom files that are coming in
from the scanner. 

-----------------------------------------------------------------------------"""