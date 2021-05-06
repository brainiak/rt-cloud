from operator import eq as opeq
from pathlib import Path
import json
import logging
import os
import re

from bids.exceptions import (
    NoMatchError,
)
from bids.layout.writing import build_path as bids_build_path
import nibabel as nib
import numpy as np
import pandas as pd
import pytest

from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsCommon import (
    BIDS_FILE_PATH_PATTERN,
    BIDS_EVENT_COL_TO_DTYPE,
    BidsFileExtension,
    DEFAULT_DATASET_DESC,
    DEFAULT_EVENTS_HEADERS,
    DEFAULT_README,
    adjustTimeUnits,
    correctEventsFileDatatypes,
    filterEntities,
    getNiftiData,
    loadBidsEntities,
    metadataAppendCompatible,
    niftiImagesAppendCompatible,
    symmetricDictDifference,
    writeDataFrameToEvents,
)
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.bidsRun import BidsRun
from tests.common import isValidBidsArchive

from rtCommon.errors import (
    MetadataMismatchError,
    MissingMetadataError,
    QueryError,
    StateError,
)

logger = logging.getLogger(__name__)

""" -----BEGIN HELPERS----- """


# Helper for checking data after append
def appendDataMatches(archive: BidsArchive, reference: BidsIncremental,
                      startIndex: int = 0, endIndex: int = -1):
    entities = filterEntities(reference.getImageMetadata())
    images = archive.getImages(**entities)
    assert len(images) == 1
    imageFromArchive = images[0].get_image()

    fullImageData = getNiftiData(imageFromArchive)
    if endIndex == -1:
        endIndex = len(fullImageData)
    appendedData = fullImageData[..., startIndex:endIndex]

    appendedImage = nib.Nifti1Image(appendedData,
                                    imageFromArchive.affine,
                                    imageFromArchive.header)

    newIncremental = BidsIncremental(appendedImage,
                                     reference.getImageMetadata())
    return newIncremental == reference


def archiveHasMetadata(archive: BidsArchive, metadata: dict) -> bool:
    """
    Test if archive's metadata matches provided metadata dict
    """

    # Compare metadata reported by PyBids to metadata we expect has been written
    bidsLayout = archive.data
    archiveMetadata = {}
    for f in bidsLayout.get(return_type='filename'):
        _, ext = os.path.splitext(f)
        if not ext == ".nii":
            continue
        archiveMetadata.update(
            bidsLayout.get_metadata(f, include_entities=True))
    for key, value in archiveMetadata.items():
        niftiValue = metadata.get(key, None)
        if niftiValue is None or niftiValue == value:
            continue
        # special case BIDS interpretation of int as int vs. dict has string
        elif type(value) is int and int(niftiValue) == value:
            continue
        # special case when metadata has been converted to BIDS values (seconds)
        # by BIDS-I construction
        elif int(niftiValue) / 1000 == value:
            continue
        else:
            logger.debug(f"{niftiValue}, type {type(niftiValue)} != {value}, "
                         f"type {type(value)}")
            return False

    return True


def incrementAcquisitionValues(incremental: BidsIncremental) -> None:
    """
    Increment the acquisition values in an image metadata dictionary to prepare
    for append an incremental to an archive built with the same source image.
    """
    trTime = incremental.getMetadataField("RepetitionTime")
    trTime = 1.0 if trTime is None else float(trTime)

    fieldToIncrement = {'AcquisitionTime': trTime, 'AcquisitionNumber': 1.0}

    for field, increment in fieldToIncrement.items():
        previousValue = incremental.getMetadataField(field)
        if previousValue is None:
            continue
        else:
            previousValue = float(previousValue)
            incremental.setMetadataField(field, previousValue + increment)


""" ----- END HELPERS ----- """


""" ----- BEGIN TEST ARCHIVE QUERYING ----- """


# Test using attributes forwarded to the BIDSLayout
def testAttributeForward(bidsArchive4D):
    assert bidsArchive4D.getSubject() == bidsArchive4D.getSubjects() == ['01']
    assert bidsArchive4D.getRun() == bidsArchive4D.getRuns() == [1]
    assert bidsArchive4D.getSession() == bidsArchive4D.getSessions() == ['01']
    assert bidsArchive4D.getCeagent() == bidsArchive4D.getCeagents() == []
    assert bidsArchive4D.getDirection() == bidsArchive4D.getDirections() == []
    assert bidsArchive4D.getDatasetDescription() == \
        bidsArchive4D.data.get_dataset_description()


# Test archive's string output is correct
def testStringOutput(bidsArchive4D):
    outPattern = r"^Root: \S+ \| Subjects: \d+ \| Sessions: \d+ " \
                 r"\| Runs: \d+$"
    assert re.fullmatch(outPattern, str(bidsArchive4D)) is not None


# Test creating bidsArchive object in an empty directory
def testEmptyArchiveCreation(tmpdir):
    datasetRoot = Path(tmpdir, "bids-archive")
    assert BidsArchive(datasetRoot) is not None


# Test empty check
def testIsEmpty(tmpdir, bidsArchive4D):
    datasetRoot = Path(tmpdir, "bids-archive")
    archive = BidsArchive(datasetRoot)
    assert archive is not None
    assert archive.isEmpty()

    assert not bidsArchive4D.isEmpty()


# Test finding an image in an archive
def testGetImages(bidsArchive4D, sample4DNifti1, bidsArchiveMultipleRuns,
                  imageMetadata):
    entities = ['subject', 'task', 'session']
    dataDict = {key: imageMetadata[key] for key in entities}

    archiveImages = bidsArchive4D.getImages(**dataDict, matchExact=False)
    assert len(archiveImages) == 1

    archiveImage = archiveImages[0].get_image()
    assert archiveImage.header == sample4DNifti1.header
    assert np.array_equal(getNiftiData(archiveImage),
                          getNiftiData(sample4DNifti1))

    # Exact match requires set of provided entities and set of entities in a
    # filename to be exactly the same (1-1 mapping); since 'run' isn't provided,
    # an exact match will fail for the multiple runs archive, which has files
    # with the 'run' entity, but will succeed for a non-exact matching, as the
    # provided entities match a subset of the file entities
    archiveImages = bidsArchiveMultipleRuns.getImages(**dataDict,
                                                      matchExact=True)
    assert archiveImages == []

    matchingDict = dataDict.copy()
    matchingDict.update({'datatype': 'func', 'suffix': 'bold', 'run': 1})
    archiveImages = bidsArchiveMultipleRuns.getImages(**matchingDict,
                                                      matchExact=True)
    assert archiveImages != []

    archiveImages = bidsArchiveMultipleRuns.getImages(**dataDict,
                                                      matchExact=False)
    assert archiveImages != []
    assert len(archiveImages) == 2


# Test failing to find an image in an archive
def testFailFindImage(bidsArchive4D, sample4DNifti1, imageMetadata, caplog):
    caplog.set_level(logging.DEBUG)

    dataDict = {'subject': 'nonValidSubject'}
    assert bidsArchive4D.getImages(**dataDict) == []
    assert f'Found no images with all entities: {dataDict}' in caplog.text

    dataDict['subject'] = imageMetadata['subject']
    dataDict['task'] = 'invalidTask'
    assert bidsArchive4D.getImages(**dataDict) == []
    assert f'Found no images with all entities: {dataDict}' in caplog.text


# Test failing when dataset is empty
def testFailEmpty(tmpdir):
    datasetRoot = Path(tmpdir, "bids-archive")
    emptyArchive = BidsArchive(datasetRoot)

    with pytest.raises(StateError):
        emptyArchive.dirExistsInArchive("will fail anyway")
    with pytest.raises(StateError):
        emptyArchive.getReadme()
    with pytest.raises(StateError):
        emptyArchive.getImages("will fail anyway")
    with pytest.raises(StateError):
        emptyArchive.getSidecarMetadata("will fall anyway")
    with pytest.raises(StateError):
        emptyArchive._getIncremental(subject="will fall anyway",
                                     session="will fall anyway",
                                     task="will fall anyway",
                                     suffix="will fall anyway",
                                     datatype="will fall anyway")


# Test getting metadata from the archive
def testGetSidecarMetadata(bidsArchive4D, imageMetadata):
    # all entities in imageMetadata should be returned
    EXTENSION = '.nii'
    returnedMeta = bidsArchive4D.getSidecarMetadata(
        bids_build_path(imageMetadata, BIDS_FILE_PATH_PATTERN) + EXTENSION,
        includeEntities=True)

    # 'TaskName' is parsed from 'task' by BIDS-I when being created, before an
    # append, so it's not in the default imageMetadata test fixture
    imageMetadata['TaskName'] = imageMetadata['task']
    adjustTimeUnits(imageMetadata)

    diff = symmetricDictDifference(returnedMeta, imageMetadata, opeq)

    # Remove the file-name entities from comparison, as we're only concerned
    # about the sidecar metadata
    bidsEntities = loadBidsEntities()
    diff = {key: diff[key] for key in diff.keys() if key not in bidsEntities}

    assert diff == {}

    invalidValues = [5, ["path1", "path2"]]
    for v in invalidValues:
        with pytest.raises(TypeError):
            bidsArchive4D.getSidecarMetadata(v)


# Test getting an event file from the archive
def testGetEvents(validBidsI, imageMetadata, tmpdir):
    archive = BidsArchive(tmpdir)
    archive._appendIncremental(validBidsI)

    # Get the events from the archive as a pandas data frame
    events = archive.getEvents()[0].get_df()
    events = correctEventsFileDatatypes(events)
    assert events is not None

    # Check the required columns are present in the events file data frame
    for column in DEFAULT_EVENTS_HEADERS:
        assert column in events.columns

    # Check the columns are of the proper types
    for column, dtype in BIDS_EVENT_COL_TO_DTYPE.items():
        if column in events.columns:
            assert events[column].dtype == dtype


""" ----- BEGIN TEST APPENDING ----- """


# Test NIfTI headers are correctly compared for append compatibility
def testNiftiHeaderValidation(sample4DNifti1, sample3DNifti1, sample2DNifti1,
                              caplog):
    # Prepare test infrastructure
    original3DHeader = sample3DNifti1.header.copy()
    original4DHeader = sample4DNifti1.header.copy()

    other3D = nib.Nifti1Image(sample3DNifti1.dataobj,
                              sample3DNifti1.affine,
                              sample3DNifti1.header)
    assert other3D.header == original3DHeader

    other4D = nib.Nifti1Image(sample4DNifti1.dataobj,
                              sample4DNifti1.affine,
                              sample4DNifti1.header)
    assert other4D.header == original4DHeader

    """ Test field values """
    # Test equal headers
    assert niftiImagesAppendCompatible(sample4DNifti1, other4D)

    # Test unequal headers on variety of fields that must match
    fieldsToModify = ["intent_code", "dim_info", "scl_slope", "sform_code"]

    for field in fieldsToModify:
        fieldArray = other4D.header[field]
        oldValue = fieldArray.copy()

        if np.sum(np.isnan(fieldArray)) > 0:
            fieldArray = np.zeros(1)
        else:
            fieldArray = fieldArray + 1
        other4D.header[field] = fieldArray

        compatible, error = \
            niftiImagesAppendCompatible(sample4DNifti1, other4D)
        assert not compatible
        assert "NIfTI headers don't match on field: " + field in error

        other4D.header[field] = oldValue

    """ Test special cases for dimensions and pixel dimensions being non-equal
    but still append compatible """
    # First three dimensions and pixel dimensions equal
    assert niftiImagesAppendCompatible(sample3DNifti1, sample4DNifti1)

    # Dimension 4 of the 3D image should not matter
    for i in range(0, 100):
        sample3DNifti1.header["dim"][4] = i
        compatible, errorMsg = niftiImagesAppendCompatible(sample3DNifti1,
                                                           sample4DNifti1)
        assert compatible

    sample3DNifti1.header["dim"] = np.copy(original3DHeader["dim"])
    assert sample3DNifti1.header == original3DHeader

    """ Test special cases for dimensions and pixel dimensions being non-equal
    and not append compatible """
    # Ensure all headers are in their original states
    assert sample4DNifti1.header == original4DHeader
    assert other4D.header == original4DHeader
    assert sample3DNifti1.header == original3DHeader
    assert other3D.header == original3DHeader

    # 4D with non-matching first 3 dimensions should fail
    other4D.header["dim"][1:4] = other4D.header["dim"][1:4] * 2
    compatible, errorMsg = niftiImagesAppendCompatible(sample4DNifti1, other4D)
    assert not compatible
    assert "NIfTI headers not append compatible due to mismatch in dimensions "\
        "and pixdim fields." in errorMsg
    # Reset
    other4D.header["dim"][1:4] = original4DHeader["dim"][1:4]
    assert other4D.header == original4DHeader

    # 3D and 4D in which first 3 dimensions don't match
    other3D.header["dim"][1:3] = other3D.header["dim"][1:3] * 2
    compatible, errorMsg = niftiImagesAppendCompatible(sample4DNifti1, other3D)
    assert not compatible

    # Reset
    other3D.header["dim"][1:3] = original3DHeader["dim"][1:3]
    assert other3D.header == original3DHeader

    # 2D and 4D are one too many dimensions apart
    other4D.header['dim'][0] = 2
    compatible, errorMsg = niftiImagesAppendCompatible(other4D, sample4DNifti1)
    assert not compatible


# Test metdata fields are correctly compared for append compatibility
def testMetadataValidation(imageMetadata, caplog):
    metadataCopy = imageMetadata.copy()

    # Test failure on sample of fields that must be the same
    matchFields = ["Modality", "MagneticFieldStrength", "ImagingFrequency",
                   "Manufacturer", "ManufacturersModelName", "InstitutionName",
                   "InstitutionAddress", "DeviceSerialNumber", "StationName",
                   "BodyPartExamined", "PatientPosition", "EchoTime",
                   "ProcedureStepDescription", "SoftwareVersions",
                   "MRAcquisitionType", "SeriesDescription", "ProtocolName",
                   "ScanningSequence", "SequenceVariant", "ScanOptions",
                   "SequenceName", "SpacingBetweenSlices", "SliceThickness",
                   "ImageType", "RepetitionTime", "PhaseEncodingDirection",
                   "FlipAngle", "InPlanePhaseEncodingDirectionDICOM",
                   "ImageOrientationPatientDICOM", "PartialFourier"]

    for field in matchFields:
        oldValue = metadataCopy.get(field, None)

        # If field not present, append should work
        if oldValue is None:
            assert metadataAppendCompatible(imageMetadata, metadataCopy)
        # If field is present, modify and ensure failure
        else:
            metadataCopy[field] = "not a valid value by any stretch of the word"
            assert metadataCopy[field] != oldValue

            compatible, errorMsg = metadataAppendCompatible(imageMetadata,
                                                            metadataCopy)
            assert not compatible
            assert f"Metadata doesn't match on field: {field}" in errorMsg

            metadataCopy[field] = oldValue

    # Test append-compatible when only one side has a particular metadata value
    for field in matchFields:
        for metadataDict in [imageMetadata, metadataCopy]:
            oldValue = metadataDict.pop(field, None)
            if oldValue is None:
                continue

            compatible, errorMsg = metadataAppendCompatible(imageMetadata,
                                                            metadataCopy)
            assert compatible

            metadataDict[field] = oldValue


# Test images are correctly appended to an empty archive
def testEmptyArchiveAppend(validBidsI, imageMetadata, tmpdir):
    # Create in root with no BIDS-I, then append to make non-empty archive
    datasetRoot = Path(tmpdir, testEmptyArchiveAppend.__name__)
    archive = BidsArchive(datasetRoot)
    archive._appendIncremental(validBidsI)

    assert not archive.isEmpty()
    assert archiveHasMetadata(archive, imageMetadata)
    assert appendDataMatches(archive, validBidsI)
    assert isValidBidsArchive(datasetRoot)


"""
NOTE: Appending to a 3-D archive is not logical, as we currently only append to
functional runs, and all functional runs must be 4-D (according to BIDS
standard)

TODO(spolcyn): Support 3-D anatomical case

# Test images are correctly appended to an archive with just a 3-D image in it
def test3DAppend(bidsArchive3D, validBidsI, imageMetadata):
    incrementAcquisitionValues(validBidsI)
    bidsArchive3D._appendIncremental(validBidsI)
    assert archiveHasMetadata(bidsArchive3D, imageMetadata)
    assert appendDataMatches(bidsArchive3D, validBidsI, startIndex=1)

    # Verify header is correctly updated
    images = bidsArchive3D.getImages(**filterEntities(imageMetadata))
    assert len(images) == 1
    image = images[0].get_image()

    # Dimensions should have increased by size of BIDS-I
    dimensions = image.header['dim']
    assert dimensions[0] == 4  # 4-D NIfTI now
    # First 3 dimensions should remain same as before, only time (4th) dimension
    # should change
    assert np.array_equal(dimensions[1:3], validBidsI.imageHeader['dim'][1:3])
    # Number of time dimensions should now be 1 (from previous image) + however
    # many images the BIDS-I volume has
    assert dimensions[4] == 1 + validBidsI.getImageDimensions()[3]

    # Time dimension (4th) should now contain the TR length
    assert image.header['pixdim'][4] == imageMetadata['RepetitionTime']

    # Units should now have time, so millimeters and seconds for current setup
    assert image.header['xyzt_units'] == 10

"""


# Test appending changes nothing if no already existing image to append to and
# specified not to create path
def testAppendNoMakePath(bidsArchive4D, validBidsI, tmpdir):
    # Append to empty archive specifying not to make any files or directories
    datasetRoot = Path(tmpdir, testEmptyArchiveAppend.__name__)
    assert not BidsArchive(datasetRoot)._appendIncremental(validBidsI,
                                                           makePath=False)

    # Append to populated archive in a way that would require new directories
    # and files without allowing it
    validBidsI.setMetadataField('subject', 'invalidSubject')
    validBidsI.setMetadataField('run', 42)

    assert not bidsArchive4D._appendIncremental(validBidsI, makePath=False)


# Test appending raises error when NIfTI headers incompatible with existing
def testConflictingNiftiHeaderAppend(bidsArchive4D, sample4DNifti1,
                                     imageMetadata):
    # Modify NIfTI header in critical way (change the datatype)
    sample4DNifti1.header['datatype'] = 32  # 32=complex, should be uint16=512
    with pytest.raises(MetadataMismatchError):
        bidsArchive4D._appendIncremental(BidsIncremental(sample4DNifti1,
                                                         imageMetadata))


# Test appending raises error when image metadata incompatible with existing
def testConflictingMetadataAppend(bidsArchive4D, sample4DNifti1, imageMetadata):
    # Modify metadata in critical way (change the subject)
    imageMetadata['ProtocolName'] = 'not the same'
    with pytest.raises(MetadataMismatchError):
        bidsArchive4D._appendIncremental(BidsIncremental(sample4DNifti1,
                                                         imageMetadata))


# Test images are correctly appended to an archive with a single 4-D image in it
def test4DAppend(bidsArchive4D, validBidsI, imageMetadata):
    incrementAcquisitionValues(validBidsI)
    bidsArchive4D._appendIncremental(validBidsI)

    assert archiveHasMetadata(bidsArchive4D, imageMetadata)
    assert appendDataMatches(bidsArchive4D, validBidsI, startIndex=2)
    assert isValidBidsArchive(bidsArchive4D.rootPath)


# Test images are correctly appended to an archive with a 4-D sequence in it
def testSequenceAppend(bidsArchive4D, validBidsI, imageMetadata):
    NUM_APPENDS = 2
    BIDSI_LENGTH = 2

    for i in range(NUM_APPENDS):
        incrementAcquisitionValues(validBidsI)
        bidsArchive4D._appendIncremental(validBidsI)

    image = bidsArchive4D.getImages(
        matchExact=False, **filterEntities(imageMetadata))[0].get_image()

    shape = image.header.get_data_shape()
    assert len(shape) == 4 and shape[3] == (BIDSI_LENGTH * (1 + NUM_APPENDS))

    assert archiveHasMetadata(bidsArchive4D, imageMetadata)
    assert appendDataMatches(bidsArchive4D, validBidsI,
                             startIndex=2, endIndex=4)
    assert isValidBidsArchive(bidsArchive4D.rootPath)


# Test appending a new subject (and thus creating a new directory) to a
# non-empty BIDS Archive
def testAppendNewSubject(bidsArchive4D, validBidsI):
    preSubjects = bidsArchive4D.getSubjects()

    validBidsI.setMetadataField("subject", "02")
    bidsArchive4D._appendIncremental(validBidsI)

    assert len(bidsArchive4D.getSubjects()) == len(preSubjects) + 1

    assert appendDataMatches(bidsArchive4D, validBidsI)
    assert isValidBidsArchive(bidsArchive4D.rootPath)


# Test appending to an archive does not overwrite existing dataset metadata
def testAppendNoOverwriteDatasetMetadata(tmpdir, validBidsI):
    rootPath = Path(tmpdir, "new-dataset")
    archive = BidsArchive(rootPath)

    EXPECTED_README = "The readme we expect"
    validBidsI.readme = EXPECTED_README
    archive._appendIncremental(validBidsI)

    NEW_README = "The readme we don't expect"
    validBidsI.readme = NEW_README
    validBidsI.setMetadataField('subject', 'newSubject')
    archive._appendIncremental(validBidsI)

    with open(os.path.join(rootPath, 'README')) as readme:
        readmeText = readme.readlines()
        assert len(readmeText) == 1
        assert readmeText[0] == EXPECTED_README


""" ----- BEGIN TEST IMAGE GETTING ----- """


# Test stripping an image off a BIDS archive works as expected
def testGetIncremental(bidsArchive4D, sample3DNifti1, sample4DNifti1,
                       imageMetadata):
    """
    TODO(spolcyn): Support anatomical archives
    # 3D Case
    reference = BidsIncremental(sample3DNifti1, imageMetadata)
    incremental = bidsArchive3D._getIncremental(
        subject=imageMetadata["subject"],
        task=imageMetadata["task"],
        suffix=imageMetadata["suffix"],
        datatype="anat",
        session=imageMetadata["session"])

    # 3D image still results in 4D incremental
    assert len(incremental.getImageDimensions()) == 4
    assert incremental.getImageDimensions()[3] == 1

    assert incremental == reference
    """

    # 4D Case
    # Both the first and second image in the 4D archive should be identical
    reference = BidsIncremental(sample3DNifti1, imageMetadata)
    for index in range(0, 2):
        incremental = bidsArchive4D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            imageIndex=index,
            session=imageMetadata["session"])

        assert len(incremental.getImageDimensions()) == 4
        assert incremental.getImageDimensions()[3] == 1

        assert incremental == reference


# Test getting incremental from BIDS archive fails when no matching images are
# present in the archive (either 0 or too many)
def testGetIncrementalNoMatchingImage(bidsArchive4D, bidsArchiveMultipleRuns,
                                      imageMetadata):
    with pytest.raises(NoMatchError):
        incremental = bidsArchive4D._getIncremental(
            subject='notPresent',
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            session=imageMetadata["session"])

        assert incremental is None

    with pytest.raises(QueryError):
        incremental = bidsArchiveMultipleRuns._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func")

        assert incremental is None


# Test getting incremental from BIDS archive raises warning when no matching
# metadata is present in the archive
def testGetIncrementalNoMatchingMetadata(bidsArchive4D, imageMetadata, caplog,
                                         tmpdir):
    # Create path to sidecar metadata file
    relPath = bids_build_path(imageMetadata, BIDS_FILE_PATH_PATTERN) + \
        BidsFileExtension.METADATA.value

    absPath = None
    files = os.listdir(tmpdir)
    for fname in files:
        if "dataset" in fname:
            absPath = Path(tmpdir, fname, relPath)
            break

    # Remove the sidecar metadata file
    os.remove(absPath)
    bidsArchive4D._updateLayout()

    # Without the sidecar metadata, not enough information for an incremental
    errorText = r"Archive lacks required metadata for BIDS Incremental " \
                r"creation: .*"
    with pytest.raises(MissingMetadataError, match=errorText):
        bidsArchive4D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            session=imageMetadata["session"])


# Test get incremental with an out-of-bounds image index for the matching image
# (could be either non-0 for 3D or beyond bounds for a 4D)
def testGetIncrementalImageIndexOutOfBounds(bidsArchive4D, imageMetadata,
                                            caplog):
    # Negative case
    outOfBoundsIndex = -1
    errorMsg = fr"Image index must be >= 0 \(got {outOfBoundsIndex}\)"
    with pytest.raises(IndexError, match=errorMsg):
        incremental = bidsArchive4D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            imageIndex=outOfBoundsIndex,
            session=imageMetadata["session"])

        assert incremental is None

    """
    TODO(spolcyn): Support 3-D anatomical case
    # 3D case
    outOfBoundsIndex = 1
    errorMsg = (f"Matching image was a 3-D NIfTI; {outOfBoundsIndex} too high "
                r"for a 3-D NIfTI \(must be 0\)") # noqa
    with pytest.raises(IndexError, match=errorMsg):
        incremental = bidsArchive3D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            imageIndex=outOfBoundsIndex,
            session=imageMetadata["session"])

        assert incremental is None
    """

    # 4D case
    outOfBoundsIndex = 4
    archiveLength = 2
    errorMsg = (f"Image index {outOfBoundsIndex} too large for NIfTI volume of "
                f"length {archiveLength}")
    with pytest.raises(IndexError, match=errorMsg):
        incremental = bidsArchive4D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            imageIndex=outOfBoundsIndex,
            session=imageMetadata["session"])

        assert incremental is None


# Test get incremental when files are found, but none match provided parameters
# exactly
def testGetIncrementalNoParameterMatch(bidsArchive4D, imageMetadata, caplog):
    # Test entity values that don't exist in the archive
    errorText = r"Unable to find any data in archive that matches" \
                r" all provided entities: \{.*?\}"
    with pytest.raises(NoMatchError, match=errorText):
        incremental = bidsArchive4D._getIncremental(
            subject=imageMetadata["subject"],
            task=imageMetadata["task"],
            suffix=imageMetadata["suffix"],
            datatype="func",
            session=imageMetadata['session'],
            run=2)

        assert incremental is None

    # Test non-existent task, subject, session, and suffix in turn
    modificationPairs = {'subject': 'nonExistentSubject',
                         'session': 'nonExistentSession',
                         'task': 'nonExistentSession',
                         'suffix': 'notBoldCBvOrPhase'}

    for argName, argValue in modificationPairs.items():
        oldValue = imageMetadata[argName]
        imageMetadata[argName] = argValue

        with pytest.raises(NoMatchError, match=errorText):
            incremental = bidsArchive4D._getIncremental(
                subject=imageMetadata["subject"],
                task=imageMetadata["task"],
                suffix=imageMetadata["suffix"],
                datatype="func",
                session=imageMetadata['session'])

            assert incremental is None

        imageMetadata[argName] = oldValue


# Test getBidsRun returns all images in a given run
def testGetBidsRun(bidsArchiveMultipleRuns, sampleBidsEntities, sample4DNifti1,
                   bidsArchive4D, validBidsI):
    # Entities that aren't present in the archive won't match
    with pytest.raises(NoMatchError) as err:
        bidsArchive4D.getBidsRun(subject='notARealSubject')
    assert "Found no runs matching entities" in str(err.value)

    # Just one entity is not specific enough
    with pytest.raises(QueryError) as err:
        bidsArchiveMultipleRuns.getBidsRun(
            subject=sampleBidsEntities['subject'])
    assert "Provided entities were not unique to one run" in str(err.value)

    run = bidsArchive4D.getBidsRun(**sampleBidsEntities)
    runData = getNiftiData(run.getIncremental(0).image).flatten()
    incrementalData = getNiftiData(validBidsI.image)[..., 0].flatten()
    assert runData.shape == incrementalData.shape
    assert np.array_equal(runData, incrementalData)

    # Ensure that the run has the expected readme, events, and dataset
    # description in it
    assert run._readme == DEFAULT_README
    assert run._datasetDescription == DEFAULT_DATASET_DESC
    for column in DEFAULT_EVENTS_HEADERS:
        assert column in run._events.columns

    # Now change the archive and ensure the values for a new run are correct
    # Change readme
    readmeFile = Path(bidsArchive4D.getReadme().path)
    newReadmeText = 'new pytest readme'
    readmeFile.write_text(newReadmeText)

    # Change dataset description
    datasetDescriptionFile = Path(bidsArchive4D.rootPath,
                                  'dataset_description.json')
    with open(datasetDescriptionFile, 'w') as f:
        newDatasetDescription = DEFAULT_DATASET_DESC.copy()
        newDatasetDescription['newField'] = 'this is some new data'
        json.dump(newDatasetDescription, f)

    # Change events
    eventsFile = bidsArchive4D.getEvents(**sampleBidsEntities)[0]
    eventsDF = correctEventsFileDatatypes(eventsFile.get_df())
    newEventsRow = [1, 2]
    eventsDF.loc[len(eventsDF)] = newEventsRow
    writeDataFrameToEvents(eventsDF, eventsFile.path)

    # Get new run and test it
    newRun = bidsArchive4D.getBidsRun(**sampleBidsEntities)
    assert newRun._readme == newReadmeText
    assert newRun._datasetDescription == newDatasetDescription
    pd.util.testing.assert_frame_equal(eventsDF, newRun._events)

    # With multiple runs, not specifying run isn't good enough
    entities = sampleBidsEntities.copy()
    del entities['run']
    with pytest.raises(QueryError) as err:
        bidsArchiveMultipleRuns.getBidsRun(**entities)
    assert "Provided entities were not unique to one run" in str(err.value)

    run = bidsArchiveMultipleRuns.getBidsRun(**sampleBidsEntities)
    assert run is not None
    assert run.numIncrementals() == sample4DNifti1.header.get_data_shape()[3]


# Test getBidsRun gets inherited events data
def testGetBidsRunInheritedEvents(tmpdir, validBidsI, sampleBidsEntities):
    # Add an events file on the top level with data
    rootPath = os.path.join(tmpdir, 'dataset')
    incrementalDFDict = {col: [4] for col in DEFAULT_EVENTS_HEADERS}
    incrementalDF = pd.DataFrame.from_dict(incrementalDFDict)
    validBidsI.events = correctEventsFileDatatypes(incrementalDF)

    validBidsI.writeToDisk(rootPath)
    archive = BidsArchive(rootPath)

    newDFDict = {col: [1, 2, 3] for col in DEFAULT_EVENTS_HEADERS}
    newDF = pd.DataFrame.from_dict(newDFDict)
    newDF = correctEventsFileDatatypes(newDF)
    writeDataFrameToEvents(newDF, '{dirPath}/task-{taskName}_events.tsv'.format(
        dirPath=rootPath, taskName=sampleBidsEntities['task']))
    archive._updateLayout()

    # Get the BIDS run
    run = archive.getBidsRun(**sampleBidsEntities)

    # Ensure that the BIDS run has all of the data added at the top level
    combinedDF = newDF.append(incrementalDF)
    combinedDF.sort_values(by='onset', inplace=True, ignore_index=True)
    assert combinedDF.equals(run._events)


# Test appendBidsRun works with compatible images
def testAppendBidsRun(tmpdir, bidsArchive4D, bidsArchiveMultipleRuns,
                      sampleBidsEntities):
    archivePath = Path(tmpdir, "appendBidsRunArchive")
    archive = BidsArchive(archivePath)
    emptyRun = BidsRun()
    archive.appendBidsRun(emptyRun)

    run = bidsArchive4D.getBidsRun(**sampleBidsEntities)
    archive.appendBidsRun(run)

    assert archive.getBidsRun(**sampleBidsEntities) == run


# Test dataset description can be retrieved
def testGetDatasetDescription(bidsArchive4D):
    path = os.path.join(bidsArchive4D.rootPath, 'dataset_description.json')
    with open(path) as f:
        datasetDescription = json.load(f)
        assert datasetDescription == bidsArchive4D.getDatasetDescription()


# Test readme can be retrieved
def testGetReadme(bidsArchive4D):
    path = os.path.join(bidsArchive4D.rootPath, 'README')
    readmeFile = bidsArchive4D.getReadme()
    with open(path) as archiveReadme, open(readmeFile.path) as returnedReadme:
        assert archiveReadme.read() == returnedReadme.read()
