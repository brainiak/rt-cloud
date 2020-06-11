import pytest
import os
import rtCommon.imageHandling as rd
from nibabel.nicom import dicomreaders
from rtCommon.fileClient import FileInterface

test_dicomFile = '001_000005_000100.dcm'
test_dicomTruncFile = 'trunc_001_000005_000100.dcm'


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
