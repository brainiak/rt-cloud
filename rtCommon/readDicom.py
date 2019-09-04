import time
import logging
import numpy as np  # type: ignore
from rtCommon.errors import StateError
try:
    import pydicom as dicom  # type: ignore
except ModuleNotFoundError:
    import dicom  # type: ignore


def parseDicomVolume(dicomImg, sliceDim):
    '''The raw dicom file will be a 2D picture with multiple slices tiled together.
       We need to separate the slices and form a volume from them.
    '''
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
    dataBytesIO = dicom.filebase.DicomBytesIO(data)
    dicomImg = dicom.dcmread(dataBytesIO)
    return dicomImg


def readDicomFromFile(filename):
    dicomImg = dicom.read_file(filename)
    return dicomImg


def readRetryDicomFromFileInterface(fileInterface, filename, timeout=5):
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
    # maskedVolume = np.zeros(volume.shape, dtype=float)
    # maskedVolume.flat[roiInds] = volume.flat[roiInds]
    maskedVolume = volume.flat[roiInds]
    return maskedVolume


def anonymizeDicom(dicomImg):
    """Anonymize header"""
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
    dataBytesIO = dicom.filebase.DicomBytesIO()
    dicom.filewriter.write_file(dataBytesIO, dicomImg)
    dataBytesIO.seek(0)
    data = dataBytesIO.read()
    return data
