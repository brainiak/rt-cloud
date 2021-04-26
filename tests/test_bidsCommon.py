import logging
import os

import numpy as np
import pytest

from rtCommon.bidsCommon import (
    adjustTimeUnits,
    getDicomMetadata,
    getNiftiData,
    gunzipFile,
    loadBidsEntities,
    metadataFromProtocolName,
)

logger = logging.getLogger(__name__)


# Test time units are adjusted correctly from DICOM (msec) to BIDS (sec)
def testTimeUnitAdjustment():
    rtKey = 'RepetitionTime'
    etKey = 'EchoTime'
    metadata = {}

    # Test values that are correct numbers, but strings and need to be converted
    rtValidButString = '50'
    etValidButString = '.5'
    metadata[rtKey] = rtValidButString
    metadata[etKey] = etValidButString

    adjustTimeUnits(metadata)
    assert metadata[rtKey] == float(rtValidButString)
    assert metadata[etKey] == float(etValidButString)

    # Test values above max, but convertible
    rtConvertible = 1000
    etConvertible = 10
    metadata[rtKey] = rtConvertible
    metadata[etKey] = etConvertible

    adjustTimeUnits(metadata)
    assert metadata[rtKey] == rtConvertible / 1000.0
    assert metadata[etKey] == etConvertible / 1000.0

    # Test values above max, but convertible
    rtAboveMax = 1000 * 100 + 1
    etAboveMax = 1000 * 1 + 1
    metadata[rtKey] = rtAboveMax
    metadata[etKey] = etAboveMax

    with pytest.raises(ValueError):
        adjustTimeUnits(metadata)

    # Test values within max
    rtWithinMax = 50
    etWithinMax = .5
    metadata[rtKey] = rtWithinMax
    metadata[etKey] = etWithinMax

    adjustTimeUnits(metadata)
    assert metadata[rtKey] == rtWithinMax
    assert metadata[etKey] == etWithinMax

    # Test missing values
    metadata[rtKey] = None
    metadata[etKey] = None

    adjustTimeUnits(metadata)
    assert metadata[rtKey] is None
    assert metadata[etKey] is None


# Test metadata is correctly extracted from a DICOM to public and private
# dictionaries by ensuring a sample of public keys have the right value
def testMetadataExtraction(dicomImage, dicomMetadataSample):
    with pytest.raises(TypeError):
        getDicomMetadata("this isn't a pydicom dataset")

    # Test a sampling of field names and values extracted by hand
    metadata = getDicomMetadata(dicomImage, kind='all')
    for field, value in dicomMetadataSample.items():
        assert metadata.get(field) == str(value)


# Ensure entitity dictionary is loaded and parsed properly
# Expected dictionary format:
#   key: Full entity name, all lowercase
def testEntitiesDictGeneration():
    entities = loadBidsEntities()

    # Ensure entity count correct
    # Manually summed from bids.json and derivatives.json, which are on Github
    # at bids-standard/pybids/bids/layout/config/
    NUM_ENTITIES = 28
    assert len(entities) == NUM_ENTITIES

    # Ensure case correct
    for key in entities.keys():
        assert key.islower()

    # Check a sample of important keys are present
    importantKeySample = ["subject", "task", "session", "datatype"]
    for key in importantKeySample:
        assert key in entities.keys()


# Test BIDS fields in a DICOM ProtocolName header field are properly parsed
def testParseProtocolName():
    # ensure nothing spurious is found in strings without BIDS fields
    assert metadataFromProtocolName("") == {}
    assert metadataFromProtocolName("this ain't bids") == {}
    assert metadataFromProtocolName("nor_is_this") == {}
    assert metadataFromProtocolName("still-aint_it") == {}

    protocolName = "func_ses-01_task-story_run-01"
    expectedValues = {'session': '01', 'task': 'story', 'run': '1'}

    parsedValues = metadataFromProtocolName(protocolName)

    for key, expectedValue in expectedValues.items():
        assert parsedValues[key] == expectedValue


# Test correct Nifti data is extracted
def testGetNiftiData(sample4DNifti1):
    extracted = getNiftiData(sample4DNifti1)
    fromRawDataobj = np.asanyarray(sample4DNifti1.dataobj,
                                   dtype=sample4DNifti1.dataobj.dtype)

    assert np.array_equal(extracted, fromRawDataobj)


# Test correct unzipping of a file
def testGunzipFile(gzippedFile):
    # Test bad source path
    with pytest.raises(FileNotFoundError):
        gunzipFile(source='/we/really/hope/this/file/doesnt/exist',
                   destination='/tmp/file.out')

    # Test bad destination path
    with pytest.raises(FileNotFoundError):
        gunzipFile(source='/tmp/file.out',
                   destination='/we/really/hope/this/file/doesnt/exist')

    destination, _ = os.path.splitext(gzippedFile)

    # Test don't delete original
    gunzipFile(gzippedFile, destination, deleteOriginal=False)
    assert os.path.exists(gzippedFile)
    assert os.path.exists(destination)

    # Test delete original
    gunzipFile(gzippedFile, destination, deleteOriginal=True)
    assert not os.path.exists(gzippedFile)
    assert os.path.exists(destination)
