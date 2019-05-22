import pytest
import os
import rtCommon.readDicom as rd


def test_readDicom():
    dicomFile = os.path.join(os.path.dirname(__file__), 'test_input/001_000001_000001.dcm')
    dicomImg1 = rd.readDicomFromFile(dicomFile)
    vol1 = rd.parseDicomVolume(dicomImg1, 64)
    assert vol1 is not None

    with open(dicomFile, 'rb') as fp:
        data = fp.read()
    dicomImg2 = rd.readDicomFromBuffer(data)
    vol2 = rd.parseDicomVolume(dicomImg2, 64)
    assert vol2 is not None
    assert (vol1 == vol2).all()
