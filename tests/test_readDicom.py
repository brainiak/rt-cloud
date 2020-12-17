import pytest
import os
import rtCommon.imageHandling as rd
from nibabel.nicom import dicomreaders
from rtCommon.fileInterface import FileInterface

test_dicomFile = '001_000013_000005.dcm'
test_dicomTruncFile = 'trunc_001_000013_000005.dcm'


def test_readDicom():
    dicomDir = os.path.join(os.path.dirname(__file__), 'test_input')
    dicomFile = os.path.join(dicomDir, test_dicomFile)
    dicomImg1 = rd.readDicomFromFile(dicomFile)
    vol1 = rd.parseDicomVolume(dicomImg1, 64)
    assert vol1 is not None

    with open(dicomFile, 'rb') as fp:
        data = fp.read()
    dicomImg2 = rd.readDicomFromBuffer(data)
    vol2 = rd.parseDicomVolume(dicomImg2, 64)
    assert vol2 is not None
    assert (vol1 == vol2).all()

    fileInterface = FileInterface()
    fileInterface.initWatch(dicomDir, '*.dcm', 0)
    dicomImg3 = rd.readRetryDicomFromFileInterface(fileInterface, dicomFile)
    vol3 = rd.parseDicomVolume(dicomImg3, 64)
    assert vol3 is not None
    assert (vol1 == vol3).all()

    # read in a truncated file, should fail and return None.
    trucatedDicomFile = os.path.join(dicomDir, test_dicomTruncFile)
    dicomImg4 = rd.readRetryDicomFromFileInterface(fileInterface, trucatedDicomFile)
    assert dicomImg4 is None

    # Test convert to nifti
    niftiObject = dicomreaders.mosaic_to_nii(dicomImg3)
    assert niftiObject is not None

    fileInterface.fileWatcher.__del__()
    fileInterface.fileWatcher = None

    # Test anonymization of sensitive patient fields
    def countUnanonymizedSensitiveAttrs(dicomImg):
        sensitiveAttrs = 0
        for attr in rd.attributesToAnonymize:
            if hasattr(dicomImg, attr) and getattr(dicomImg, attr) != "":
                sensitiveAttrs += 1
        return sensitiveAttrs

    dicomImg5 = rd.readDicomFromFile(dicomFile)
    assert countUnanonymizedSensitiveAttrs(dicomImg5) >= 1

    rd.anonymizeDicom(dicomImg5)
    assert countUnanonymizedSensitiveAttrs(dicomImg5) == 0
