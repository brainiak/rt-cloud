from copy import deepcopy
import logging
import os
import pickle

from bids.layout import BIDSImageFile
from bids.layout.writing import build_path as bids_build_path
import nibabel as nib
import numpy as np
import pandas as pd
import pytest

from rtCommon.bidsCommon import (
    BIDS_DIR_PATH_PATTERN,
    BIDS_FILE_PATTERN,
    PYBIDS_PSEUDO_ENTITIES,
    BidsFileExtension,
    getNiftiData,
    metadataFromProtocolName,
)
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.bidsArchive import BidsArchive
from rtCommon.errors import MissingMetadataError
from tests.common import isValidBidsArchive

logger = logging.getLogger(__name__)


# Test that construction fails for image metadata missing required fields
def testInvalidConstruction(sample2DNifti1, samplePseudo2DNifti1,
                            sample4DNifti1, imageMetadata):
    # Test empty image
    with pytest.raises(TypeError):
        BidsIncremental(image=None,
                        imageMetadata=imageMetadata)

    # Test 2-D image
    with pytest.raises(ValueError) as err:
        BidsIncremental(image=sample2DNifti1,
                        imageMetadata=imageMetadata)
        assert "Image must have at least 3 dimensions" in str(err.value)

    # Test 2-D image masquerading as 4-D image
    with pytest.raises(ValueError) as err:
        BidsIncremental(image=samplePseudo2DNifti1,
                        imageMetadata=imageMetadata)
        assert ("Image's 3rd (and any higher) dimensions are <= 1, which means "
                "it is a 2D image; images must have at least 3 dimensions" in
                str(err.value))

    # Test incomplete metadata
    protocolName = imageMetadata.pop("ProtocolName")
    for key in BidsIncremental.REQUIRED_IMAGE_METADATA:
        value = imageMetadata.pop(key)

        assert not BidsIncremental.isCompleteImageMetadata(imageMetadata)
        with pytest.raises(MissingMetadataError):
            BidsIncremental(image=sample4DNifti1,
                            imageMetadata=imageMetadata)

        imageMetadata[key] = value
    imageMetadata["ProtocolName"] = protocolName

    # Test too-large repetition and echo times
    for key in ["RepetitionTime", "EchoTime"]:
        original = imageMetadata[key]
        imageMetadata[key] = 10**6

        with pytest.raises(ValueError):
            BidsIncremental(image=sample4DNifti1,
                            imageMetadata=imageMetadata)

        imageMetadata[key] = original

    # Test non-image object
    with pytest.raises(TypeError) as err:
        notImage = "definitely not an image"
        BidsIncremental(image=notImage,
                        imageMetadata=imageMetadata)
        assert ("Image must be one of [nib.Nifti1Image, nib.Nifti2Image, "
               f"BIDSImageFile (got {type(notImage)})" in str(err.value))

    # Test non-functional data
    with pytest.raises(NotImplementedError) as err:
        original = imageMetadata['datatype']
        invalidType = 'anat'
        imageMetadata['datatype'] = invalidType
        BidsIncremental(image=sample4DNifti1,
                        imageMetadata=imageMetadata)
        imageMetadata['datatype'] = original

        assert ("BIDS Incremental for BIDS datatypes other than 'func' is not "
                f"yet implemented (got '{invalidType}')") in str(err.value)


# Test that valid arguments produce a BIDS incremental
def testValidConstruction(sample3DNifti1, sample3DNifti2,
                          sample4DNifti1, sampleNifti2, bidsArchive4D,
                          imageMetadata):
    # 3-D should be promoted to 4-D
    assert BidsIncremental(sample3DNifti1, imageMetadata) is not None
    assert BidsIncremental(sample3DNifti2, imageMetadata) is not None

    # Both Nifti1 and Nifti2 images should work
    assert BidsIncremental(sample4DNifti1, imageMetadata) is not None
    assert BidsIncremental(sampleNifti2, imageMetadata) is not None

    # If the metadata provides a RepetitionTime or EchoTime that works without
    # adjustment, the construction should still work
    repetitionTimeKey = "RepetitionTime"
    original = imageMetadata[repetitionTimeKey]
    imageMetadata[repetitionTimeKey] = 1.5
    assert BidsIncremental(sample4DNifti1, imageMetadata) is not None
    imageMetadata[repetitionTimeKey] = original

    # Passing a BIDSImageFile is also valid
    image = bidsArchive4D.getImages()[0]
    assert type(image) is BIDSImageFile
    assert BidsIncremental(image, imageMetadata) is not None


# Test that metadata values are of the correct types, if required by BIDS
def testMetadataTypes(validBidsI):
    typeDict = {"RepetitionTime": float, "EchoTime": float}

    for field, typ in typeDict.items():
        assert type(validBidsI.getMetadataField(field)) is typ


# Test that the provided image metadata dictionary takes precedence over the
# metadata parsed from the protocol name, if any
def testConstructionMetadataPrecedence(sample4DNifti1, imageMetadata):
    assert imageMetadata.get('ProtocolName', None) is not None
    metadata = metadataFromProtocolName(imageMetadata['ProtocolName'])
    assert len(metadata) > 0

    assert metadata.get('run', None) is not None
    newRunNumber = int(metadata['run']) + 1
    imageMetadata['run'] = newRunNumber
    assert metadata['run'] != imageMetadata['run']

    incremental = BidsIncremental(sample4DNifti1, imageMetadata)
    assert incremental.getMetadataField('run') == newRunNumber


# Test that the string output of the BIDS-I is as expected
def testStringOutput(validBidsI):
    imageShape = str(validBidsI.getImageDimensions())
    keyCount = len(validBidsI._imgMetadata.keys())
    version = validBidsI.version
    assert str(validBidsI) == f"Image shape: {imageShape}; " \
                              f"Metadata Key Count: {keyCount}; " \
                              f"BIDS-I Version: {version}"


# Test that equality comparison is as expected
def testEquals(sample4DNifti1, sample3DNifti1, imageMetadata):
    # Test images with different headers
    assert BidsIncremental(sample4DNifti1, imageMetadata) != \
           BidsIncremental(sample3DNifti1, imageMetadata)

    # Test images with the same header, but different data
    newData = 2 * getNiftiData(sample4DNifti1)
    reversedNifti1 = nib.Nifti1Image(newData, sample4DNifti1.affine,
                                     header=sample4DNifti1.header)
    assert BidsIncremental(sample4DNifti1, imageMetadata) != \
        BidsIncremental(reversedNifti1, imageMetadata)

    # Test different image metadata
    modifiedImageMetadata = deepcopy(imageMetadata)
    modifiedImageMetadata["subject"] = "newSubject"
    assert BidsIncremental(sample4DNifti1, imageMetadata) != \
           BidsIncremental(sample4DNifti1, modifiedImageMetadata)

    # Test different dataset metadata
    datasetMeta1 = {"Name": "Dataset_1", "BIDSVersion": "1.0"}
    datasetMeta2 = {"Name": "Dataset_2", "BIDSVersion": "2.0"}
    assert BidsIncremental(sample4DNifti1, imageMetadata, datasetMeta1) != \
           BidsIncremental(sample4DNifti1, imageMetadata, datasetMeta2)

    # Test different readme
    incremental1 = BidsIncremental(sample4DNifti1, imageMetadata)
    incremental2 = BidsIncremental(sample4DNifti1, imageMetadata)
    readme1 = "README 1"
    readme2 = "README 2"

    incremental1.readme = readme1
    incremental2.readme = readme2
    assert incremental1 != incremental2

    # Test different events file
    incremental1 = BidsIncremental(sample4DNifti1, imageMetadata)
    incremental2 = BidsIncremental(sample4DNifti1, imageMetadata)

    events1 = {'onset': [1, 25, 50], 'duration': [10, 10, 10], 'response_time':
               [15, 36, 70]}
    events2 = {key: [v + 5 for v in events1[key]] for key in events1.keys()}

    incremental1.events = pd.DataFrame(data=events1)
    incremental2.events = pd.DataFrame(data=events2)
    assert incremental1 != incremental2


# Test that image metadata dictionaries can be properly created by the class
def testImageMetadataDictCreation(imageMetadata):
    createdDict = BidsIncremental.createImageMetadataDict(
        subject=imageMetadata["subject"],
        task=imageMetadata["task"],
        suffix=imageMetadata["suffix"],
        repetitionTime=imageMetadata["RepetitionTime"],
        datatype='func')

    for key in createdDict.keys():
        assert createdDict.get(key) == imageMetadata.get(key)

    # Ensure that the method is in sync with the required metadata
    # Get all required fields as lowerCamelCase for passing as kwargs
    requiredFieldsCamel = [(key[0].lower() + key[1:]) for key in
                           BidsIncremental.REQUIRED_IMAGE_METADATA]
    dummyValue = 'n/a'
    metadataDict = {key: dummyValue for key in requiredFieldsCamel}
    createdDict = BidsIncremental.createImageMetadataDict(**metadataDict)

    for field in BidsIncremental.REQUIRED_IMAGE_METADATA:
        assert createdDict[field] == dummyValue


# Test that internal metadata dictionary is independent from the argument dict
def testMetadataDictionaryIndependence(sample4DNifti1, imageMetadata):
    incremental = BidsIncremental(sample4DNifti1, imageMetadata)

    key = 'subject'
    assert incremental.getMetadataField(key) == imageMetadata[key]
    old = incremental.getMetadataField(key)

    imageMetadata[key] = 'a brand-new subject'
    assert incremental.getMetadataField(key) == old
    assert incremental.getMetadataField(key) != imageMetadata[key]


# Test that invalid dataset.json fields are rejected and valid ones are accepted
def testDatasetMetadata(sample4DNifti1, imageMetadata):
    # Test invalid dataset metadata
    with pytest.raises(MissingMetadataError):
        BidsIncremental(image=sample4DNifti1,
                        imageMetadata=imageMetadata,
                        datasetDescription={"random_field": "doesnt work"})

    # Test valid dataset metadata
    dataset_name = "Test dataset"
    bidsInc = BidsIncremental(image=sample4DNifti1,
                              imageMetadata=imageMetadata,
                              datasetDescription={"Name": dataset_name,
                                                  "BIDSVersion": "1.0"})
    assert bidsInc.getDatasetName() == dataset_name


# Test that extracting metadata from the BIDS-I using its provided API returns
# the correct values
def testMetadataOutput(validBidsI, imageMetadata):
    with pytest.raises(ValueError):
        validBidsI.getMetadataField("InvalidEntityName", strict=True)
    with pytest.raises(KeyError):
        validBidsI.getMetadataField("InvalidEntityName")

    # Data type - always 'func' currently
    assert validBidsI.getDatatype() == "func"
    # Entities
    for entity in ['subject', 'task']:
        assert validBidsI.getMetadataField(entity) == imageMetadata[entity]
    # Suffix
    assert validBidsI.getSuffix() == imageMetadata["suffix"]


# Test setting BIDS-I metadata API works as expected
def testSetMetadata(validBidsI):
    # Test non-official BIDS entity fails with strict
    with pytest.raises(ValueError):
        validBidsI.setMetadataField("nonentity", "value", strict=True)

    # Non-official BIDS entity succeeds without strict
    validBidsI.setMetadataField("nonentity", "value", strict=False)
    assert validBidsI.getMetadataField("nonentity", strict=False) == "value"
    validBidsI.removeMetadataField("nonentity", strict=False)

    # None field is invalid
    with pytest.raises(ValueError):
        validBidsI.setMetadataField(None, "test")

    entityName = "subject"
    newValue = "newValue"
    originalValue = validBidsI.getMetadataField(entityName)

    validBidsI.setMetadataField(entityName, newValue)
    assert validBidsI.getMetadataField(entityName) == newValue

    validBidsI.setMetadataField(entityName, originalValue)
    assert validBidsI.getMetadataField(entityName) == originalValue


# Test removing BIDS-I metadata API works as expected
def testRemoveMetadata(validBidsI):
    # Fail for entities that don't exist
    with pytest.raises(ValueError):
        validBidsI.removeMetadataField("nonentity", strict=True)

    # Fail for entities that are required to be in the dictionary
    with pytest.raises(RuntimeError):
        validBidsI.removeMetadataField("subject")

    entityName = "ProtocolName"
    originalValue = validBidsI.getMetadataField(entityName)

    validBidsI.removeMetadataField(entityName)
    with pytest.raises(KeyError):
        validBidsI.getMetadataField(entityName) is None

    validBidsI.setMetadataField(entityName, originalValue)
    assert validBidsI.getMetadataField(entityName) == originalValue


# Test that the BIDS-I interface methods for extracting internal NIfTI data
# return the correct values
def testQueryNifti(validBidsI):
    # Image data
    queriedData = validBidsI.getImageData()
    exactData = getNiftiData(validBidsI.image)
    assert np.array_equal(queriedData, exactData), "{} elements not equal" \
        .format(np.sum(np.where(queriedData != exactData)))

    # Header Data
    queriedHeader = validBidsI.getImageHeader()
    exactHeader = validBidsI.image.header

    # Compare full image header
    assert queriedHeader.keys() == exactHeader.keys()
    for (field, queryValue) in queriedHeader.items():
        exactValue = exactHeader.get(field)
        if queryValue.dtype.char == 'S':
            assert queryValue == exactValue
        else:
            assert np.allclose(queryValue, exactValue, atol=0.0, equal_nan=True)

    # Compare Header field: Dimensions
    FIELD = "dim"
    assert np.array_equal(queriedHeader.get(FIELD), exactHeader.get(FIELD))


# Test that constructing BIDS-compatible filenames from internal metadata
# returns the correct filenames
def testFilenameConstruction(validBidsI, imageMetadata):
    """
    General format:
    sub-<label>[_ses-<label>]_task-<label>[_acq-<label>] [_ce-<label>]
        [_dir-<label>][_rec-<label>][_run-<index>]
        [_echo-<index>]_<contrast_label >.ext
    """
    baseFilename = bids_build_path(imageMetadata, BIDS_FILE_PATTERN)

    assert baseFilename + ".nii" == \
        validBidsI.makeBidsFileName(BidsFileExtension.IMAGE)
    assert baseFilename + ".json" == \
        validBidsI.makeBidsFileName(BidsFileExtension.METADATA)


# Test that the hypothetical path for the BIDS-I if it were in an archive is
# correct based on the metadata within it
def testArchivePathConstruction(validBidsI, imageMetadata):
    assert validBidsI.getDataDirPath() == \
        bids_build_path(imageMetadata, BIDS_DIR_PATH_PATTERN)


# Test that writing the BIDS-I to disk returns a properly formatted BIDS archive
# in the correct location with all the data in the BIDS-I
def testDiskOutput(validBidsI, tmpdir):
    # Write the archive
    datasetRoot = os.path.join(tmpdir, "bids-pytest-dataset")
    validBidsI.writeToDisk(datasetRoot)

    # Validate the output can be opened by BidsArchive and verified against the
    # source BIDS-Incremental
    archive = BidsArchive(datasetRoot)
    archiveImage = archive.getImages()[0]

    # Remove pseudo entities to avoid conflict with the validBidsI
    metadata = archive.getSidecarMetadata(archiveImage, includeEntities=True)
    for entity in PYBIDS_PSEUDO_ENTITIES:
        metadata.pop(entity)

    incrementalFromArchive = BidsIncremental(archiveImage, metadata)
    assert incrementalFromArchive == validBidsI

    assert isValidBidsArchive(archive.rootPath)

    # Try only writing data
    datasetRoot = os.path.join(tmpdir, "bids-pytest-dataset-2")
    validBidsI.writeToDisk(datasetRoot, onlyData=True)
    assert not os.path.exists(os.path.join(datasetRoot, "README"))
    assert not os.path.exists(os.path.join(datasetRoot,
                                           "dataset_description.json"))


# Test serialization results in equivalent BIDS-I object
def testSerialization(validBidsI, sample4DNifti1, imageMetadata, tmpdir):
    # Copy the NIfTI source image to a different location
    sourceFileName = 'test.nii'
    sourceFilePath = os.path.join(tmpdir, sourceFileName)
    nib.save(sample4DNifti1, sourceFilePath)

    sourceNifti = nib.load(sourceFilePath)
    incremental = BidsIncremental(sourceNifti, imageMetadata)

    # validBidsI is derived from a file elsewhere on disk, so we can use it as a
    # reference once the file 'incremental' is derived from is removed
    # Transitive property gives us:
    # IF incremental == validBidsI AND validBidsI == deserialized
    # THEN incremental == deserialized
    assert incremental == validBidsI

    # Serialize the object
    serialized = pickle.dumps(incremental)
    del incremental

    # Now remove image file so the deserialized object can't access it
    os.remove(sourceFilePath)

    # Deserialize the object
    deserialized = pickle.loads(serialized)

    # Compare equality
    assert validBidsI == deserialized

    # Check there's no file mapping
    assert deserialized.image.file_map['image'].filename is None
