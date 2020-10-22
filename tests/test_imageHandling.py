import os
import tempfile

from nibabel.nicom import dicomreaders
import numpy as np
import pytest

from rtCommon.dataInterface import DataInterface
from rtCommon.errors import ValidationError
from tests.common import test_dicomPath, test_dicomTruncPath, test_inputDirPath
import rtCommon.imageHandling as imgHandler


def test_readDicom():
    dicomImg1 = imgHandler.readDicomFromFile(test_dicomPath)
    vol1 = imgHandler.parseDicomVolume(dicomImg1, 64)
    assert vol1 is not None

    with open(test_dicomPath, 'rb') as fp:
        data = fp.read()
    dicomImg2 = imgHandler.readDicomFromBuffer(data)
    vol2 = imgHandler.parseDicomVolume(dicomImg2, 64)
    assert vol2 is not None
    assert (vol1 == vol2).all()

    # if dataInterface is not initialized with allowedDirs or allowedFileTypes,
    # it should fail
    dataInterface = DataInterface()
    with pytest.raises(ValidationError):
        dataInterface.initWatch(test_inputDirPath, '*.dcm', 0)

    # Now allow all dirs and file types
    dataInterface = DataInterface(allowedDirs=['*'], allowedFileTypes=['*'])
    dataInterface.initWatch(test_inputDirPath, '*.dcm', 0)
    dicomImg3 = imgHandler.readRetryDicomFromDataInterface(dataInterface,
                                                           test_dicomPath)
    vol3 = imgHandler.parseDicomVolume(dicomImg3, 64)
    assert vol3 is not None
    assert (vol1 == vol3).all()

    # read in a truncated file, should fail and return None.
    dicomImg4 = imgHandler.readRetryDicomFromDataInterface(dataInterface,
                                                           test_dicomTruncPath)
    assert dicomImg4 is None

    # Test convert to nifti
    niftiObject = dicomreaders.mosaic_to_nii(dicomImg3)
    assert niftiObject is not None

    dataInterface.fileWatcher.__del__()
    dataInterface.fileWatcher = None

    # Test anonymization of sensitive patient fields
    def countUnanonymizedSensitiveAttrs(dicomImg):
        sensitiveAttrs = 0
        for attr in imgHandler.attributesToAnonymize:
            if hasattr(dicomImg, attr) and getattr(dicomImg, attr) != "":
                sensitiveAttrs += 1
        return sensitiveAttrs

    dicomImg5 = imgHandler.readDicomFromFile(test_dicomPath)
    assert countUnanonymizedSensitiveAttrs(dicomImg5) >= 1

    imgHandler.anonymizeDicom(dicomImg5)
    assert countUnanonymizedSensitiveAttrs(dicomImg5) == 0


def test_nifti():
    with tempfile.TemporaryDirectory() as tmpDir:
        niftiFilename = os.path.join(tmpDir, 'nifti1.nii')
        imgHandler.convertDicomFileToNifti(test_dicomPath, niftiFilename)
        niftiImg1 = imgHandler.readNifti(niftiFilename)

        dcmImg = imgHandler.readDicomFromFile(test_dicomPath)
        niftiImgFromDcm = imgHandler.convertDicomImgToNifti(dcmImg)
        assert niftiImg1.header == niftiImgFromDcm.header
        assert np.array_equal(np.array(niftiImg1.dataobj),
                              np.array(niftiImgFromDcm.dataobj))
