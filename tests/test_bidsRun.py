import logging

import nibabel as nib
import numpy as np
import pytest

from rtCommon.bidsCommon import getNiftiData, DEFAULT_EVENTS_HEADERS
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.bidsRun import BidsRun
from rtCommon.errors import MetadataMismatchError

logger = logging.getLogger(__name__)


# Test equality check is correct
def testEq(oneImageBidsI):
    run1 = BidsRun()
    run2 = BidsRun()

    run1.appendIncremental(oneImageBidsI)
    assert run1 != run2

    run2.appendIncremental(oneImageBidsI)
    assert run1 == run2

    run2._entities['subject'] = "new_subect"
    assert run1 != run2


# Test numIncrementals output is correct
def testNumIncrementals(oneImageBidsI):
    run = BidsRun()
    assert run.numIncrementals() == 0

    NUM_APPENDS = 20
    for i in range(NUM_APPENDS):
        run.appendIncremental(oneImageBidsI)
        assert run.numIncrementals() == i + 1


# Test out of bounds values for get incremental
def testGetOutOfBounds(oneImageBidsI):
    run = BidsRun()

    NUM_APPENDS = 10
    for i in range(NUM_APPENDS):
        run.appendIncremental(oneImageBidsI)

    # This is inbounds due to how negative indexing works
    assert run.getIncremental(0) == run.getIncremental(-1 * NUM_APPENDS)

    with pytest.raises(IndexError):
        run.getIncremental(NUM_APPENDS)
    with pytest.raises(IndexError):
        run.getIncremental(NUM_APPENDS + 1)
    with pytest.raises(IndexError):
        run.getIncremental(-1 * NUM_APPENDS - 1)


# Test get and append
def testGetAppendIncremental(oneImageBidsI):
    run = BidsRun()

    run.appendIncremental(oneImageBidsI)
    assert run.getIncremental(0) == oneImageBidsI

    NUM_APPENDS = 20
    for i in range(1, NUM_APPENDS):
        run.appendIncremental(oneImageBidsI)
        assert run.getIncremental(i) == oneImageBidsI


# Test construction
def testConstruction(oneImageBidsI, sampleBidsEntities):
    runWithoutEntities = BidsRun()
    assert runWithoutEntities is not None
    assert len(runWithoutEntities.getRunEntities()) == 0

    runWithEntities = BidsRun(**sampleBidsEntities)
    assert runWithEntities is not None
    assert runWithEntities.getRunEntities() == sampleBidsEntities


# Test append correctly sets entities
def testAppendSetEntities(oneImageBidsI, sampleBidsEntities):
    run = BidsRun()
    run.appendIncremental(oneImageBidsI)
    assert run.getRunEntities() == sampleBidsEntities


# Test append works correctly if entities are set but incremental list is empty
def testAppendEmptyIncrementals(oneImageBidsI, sampleBidsEntities):
    run = BidsRun(**sampleBidsEntities)
    run.appendIncremental(oneImageBidsI)
    assert run.numIncrementals() == 1


# Test append doesn't work with mismatched entities
def testAppendConflictingEntities(oneImageBidsI):
    differentBidsInc = BidsIncremental(oneImageBidsI.image,
                                       oneImageBidsI.getImageMetadata())
    differentBidsInc.setMetadataField("subject", "new-subject")

    run = BidsRun()
    run.appendIncremental(oneImageBidsI)
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(differentBidsInc)


# Test append doesn't work if NIfTI headers don't match
def testAppendConflictingNiftiHeaders(oneImageBidsI, imageMetadata):
    # Change the pixel dimensions (zooms) to make the image append-incompatible
    image2 = nib.Nifti1Image(oneImageBidsI.image.dataobj,
                             oneImageBidsI.image.affine,
                             oneImageBidsI.image.header)
    new_data_shape = tuple(i * 2 for i in image2.header.get_zooms())
    image2.header.set_zooms(new_data_shape)
    bidsInc2 = BidsIncremental(image2, imageMetadata)

    run = BidsRun()
    run.appendIncremental(oneImageBidsI)
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(bidsInc2)

    # Append should work now with validateAppend turned off
    numIncrementalsBefore = run.numIncrementals()
    run.appendIncremental(bidsInc2, validateAppend=False)
    assert run.numIncrementals() == (numIncrementalsBefore + 1)


# Test append doesn't work if metadata doesn't match
def testAppendConflictingMetadata(oneImageBidsI):
    bidsInc2 = BidsIncremental(oneImageBidsI.image,
                               oneImageBidsI.getImageMetadata())
    bidsInc2.setMetadataField('subject', 'definitely_invalid_name')

    run = BidsRun()
    run.appendIncremental(oneImageBidsI)
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(bidsInc2)

    # Append should work now with validateAppend turned off
    numIncrementalsBefore = run.numIncrementals()
    run.appendIncremental(bidsInc2, validateAppend=False)
    assert run.numIncrementals() == (numIncrementalsBefore + 1)


# Test append conflicting readme
def testAppendConflictingReadme(oneImageBidsI, sampleBidsEntities):
    run = BidsRun()
    run.appendIncremental(oneImageBidsI)

    oneImageBidsI.readme += "totally new data"
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(oneImageBidsI)

    assert oneImageBidsI != run.getIncremental(0)


# Test append conflicting dataset description
def testAppendConflictingDatasetDescription(oneImageBidsI, sampleBidsEntities):
    run = BidsRun()
    run.appendIncremental(oneImageBidsI)

    oneImageBidsI.datasetDescription["newKey"] = "totally new data"
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(oneImageBidsI)

    assert oneImageBidsI != run.getIncremental(0)


# Test append conflicting event files
def testAppendConflictingEvents(oneImageBidsI, sampleBidsEntities):
    run = BidsRun()
    run.appendIncremental(oneImageBidsI)

    # This should work, as the previous events file is empty so any new data
    # shouldn't have a conflict
    newEventsData = [{key: data for key in DEFAULT_EVENTS_HEADERS} for data in
                     range(1)]
    oneImageBidsI.events = oneImageBidsI.events.append(newEventsData,
                                                       ignore_index=True)
    run.appendIncremental(oneImageBidsI)

    # This should also work, as they share the same starting row, and the new
    # DataFrame just has 5 additional rows
    newRowCount = 5
    newEventsData = [{key: data for key in DEFAULT_EVENTS_HEADERS} for data in
                     range(1, newRowCount + 1)]
    oneImageBidsI.events = oneImageBidsI.events.append(newEventsData,
                                                       ignore_index=True)
    run.appendIncremental(oneImageBidsI)

    # This should fail, as rows for same onset times have different values now
    with pytest.raises(MetadataMismatchError):
        oneImageBidsI.events.iloc[int(newRowCount / 2):] += 1
        run.appendIncremental(oneImageBidsI)

    assert oneImageBidsI != run.getIncremental(0)


# Test consolidation into single incremental works as expected
def testAsSingleIncremental(oneImageBidsI):
    run = BidsRun()
    assert run.asSingleIncremental() is None

    NUM_APPENDS = 5
    for i in range(NUM_APPENDS):
        run.appendIncremental(oneImageBidsI)

    oldImage = oneImageBidsI.image
    imageData = getNiftiData(oldImage)
    newDataShape = imageData.shape[:3] + (NUM_APPENDS,)
    newData = np.zeros(newDataShape, dtype=imageData.dtype)
    for i in range(NUM_APPENDS):
        newData[..., i] = imageData[..., 0]

    newImage = oldImage.__class__(newData, oldImage.affine, oldImage.header)
    consolidatedBidsI = BidsIncremental(newImage,
                                        oneImageBidsI.getImageMetadata())

    assert run.asSingleIncremental() == consolidatedBidsI


# Test that updating entities works as expected
def testUpdateEntities(validBidsI):
    # Ensure an append updates the run's entities to the full set
    entities = {key: validBidsI.getEntities()[key] for key in ['subject',
                                                               'task']}
    run = BidsRun(**entities)

    assert run._entities != validBidsI.getEntities()
    run.appendIncremental(validBidsI)
    assert run._entities == validBidsI.getEntities()

    # Ensure minimally supplied entities are still sufficient to block a
    # non-matching run and doesn't update the run's entities
    entities = {key: validBidsI.getEntities()[key] for key in ['subject',
                                                               'task']}
    run = BidsRun(**entities)

    preAppendEntities = run._entities
    assert preAppendEntities != validBidsI.getEntities()
    validBidsI.setMetadataField('subject', 'nonValidSubject')
    with pytest.raises(MetadataMismatchError):
        run.appendIncremental(validBidsI)
    assert run._entities == preAppendEntities
