# NOTE: Could modularize this further by creating a fixtures dir and importing
# See: https://gist.github.com/peterhurford/09f7dcda0ab04b95c026c60fa49c2a68
from pathlib import Path
from random import randint
import json
import logging
import os

from bids.layout.writing import build_path as bids_build_path
import nibabel as nib
import pandas as pd
import pydicom
import pytest

from tests.common import (
    test_3DNifti1Path,
    test_3DNifti2Path,
    test_4DNifti1Path,
    test_4DNifti2Path,
    test_dicomPath,
)
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsCommon import (
    BIDS_DIR_PATH_PATTERN,
    BIDS_FILE_PATTERN,
    DEFAULT_DATASET_DESC,
    DEFAULT_README,
    DEFAULT_EVENTS_HEADERS,
    adjustTimeUnits,
    correctEventsFileDatatypes,
    getDicomMetadata,
    getNiftiData,
    writeDataFrameToEvents,
)
from rtCommon.bidsIncremental import BidsIncremental
from tests.createTestNiftis import (
    createNiftiTestFiles,
    deleteNiftiTestFiles,
    haveAllNiftiTestFiles,
)
from rtCommon.imageHandling import (
    readDicomFromFile,
    readNifti
)

logger = logging.getLogger(__name__)

RECREATE_TEST_NIFTIS_KEY = "recreateTestNiftis"


def pytest_addoption(parser):
    # Enable forced re-creation of NIfTI test files
    parser.addoption("--recreate-test-niftis", action="store_true",
                     dest=RECREATE_TEST_NIFTIS_KEY, default=False)


def pytest_configure(config) -> None:
    # Recreate test files if requested or if any are missing
    recreateTestNiftis = config.getoption(RECREATE_TEST_NIFTIS_KEY, False)
    if recreateTestNiftis or not haveAllNiftiTestFiles():
        deleteNiftiTestFiles()
        createNiftiTestFiles()


""" BEGIN DICOM RELATED FIXTURES """


# Dictionary of some fields of the read-in DICOM image
@pytest.fixture
def dicomMetadataSample() -> dict:
    sample = {}
    sample["ContentDate"] = "20190219"
    sample["ContentTime"] = "124758.653000"
    sample["RepetitionTime"] = 1500
    sample["StudyDescription"] = "Norman_Mennen^5516_greenEyes"
    sample["StudyInstanceUID"] = \
        "1.3.12.2.1107.5.2.19.45031.30000019021215313940500000046"
    sample["ProtocolName"] = "func_ses-01_task-faces_run-01"

    return sample


# PyDicom image read in from test DICOM file
@pytest.fixture
def dicomImage(dicomMetadataSample) -> pydicom.dataset.Dataset:
    dicom = readDicomFromFile(os.path.join(os.path.dirname(__file__),
                                           test_dicomPath))
    assert dicom is not None

    # Test a sampling of fields to ensure proper read
    for field, value in dicomMetadataSample.items():
        assert getattr(dicom, field) == value

    return dicom


# Public metadata for test DICOM file
@pytest.fixture
def dicomImageMetadata(dicomImage):
    return getDicomMetadata(dicomImage, kind='public')


""" END DICOM RELATED FIXTURES """


""" BEGIN BIDS RELATED FIXTURES """


# 2-D NIfTI 1 image corrupted from the test DICOM image
@pytest.fixture
def sample2DNifti1():
    nifti = readNifti(test_3DNifti1Path)
    newData = getNiftiData(nifti)
    # max positive value of 2 byte, signed short used in Nifti header for
    # storing dimension information
    newData = (newData.flatten()[:10000]).reshape((100, 100))
    return nib.Nifti1Image(newData, nifti.affine)


# A NIfTI image that is technically 4-D, but actually is only 2-D (i.e., it's
# header has 4 dimensions, but the last two are 1's)
@pytest.fixture
def samplePseudo2DNifti1(sample2DNifti1):
    data = getNiftiData(sample2DNifti1)
    data = data.reshape((data.shape[0], data.shape[1], 1, 1))
    return nib.Nifti1Image(data, sample2DNifti1.affine)


# 3-D NIfTI 1 image derived from the test DICOM image
@pytest.fixture(scope='function')
def sample3DNifti1():
    return readNifti(test_3DNifti1Path)


# 3-D NIfTI 2 image derived from the test DICOM image
@pytest.fixture(scope='function')
def sample3DNifti2():
    return readNifti(test_3DNifti2Path)


# 4-D NIfTI 1 image derived from concatting the test DICOM image with itself
@pytest.fixture(scope='function')
def sample4DNifti1():
    return readNifti(test_4DNifti1Path)


# 4-D NIfTI 2 image derived from concatting the test DICOM image with itself
@pytest.fixture(scope='function')
def sampleNifti2():
    return readNifti(test_4DNifti2Path)


# Set of BIDS entities needed for BIDS-I creation
@pytest.fixture(scope='function')
def sampleBidsEntities():
    return {'subject': '01', 'task': 'faces', 'suffix': 'bold', 'datatype':
            'func', 'session': '01', 'run': 1}


@pytest.fixture(scope='function')
def imageMetadata(dicomImageMetadata, sampleBidsEntities):
    """
    Dictionary with all required metadata to construct a BIDS-Incremental, as
    well as extra metadata extracted from the test DICOM image.
    """
    meta = sampleBidsEntities.copy()
    meta.update(dicomImageMetadata)
    return meta


@pytest.fixture(scope='function')
def validBidsI(sample4DNifti1, imageMetadata):
    """
    Constructs and returns a known-valid BIDS-Incremental using known metadata.
    """
    return BidsIncremental(image=sample4DNifti1,
                           imageMetadata=imageMetadata)


@pytest.fixture(scope='function')
def oneImageBidsI(sample4DNifti1, imageMetadata):
    """
    Constructs and returns a known-valid BIDS-Incremental using known metadata.
    """
    newData = getNiftiData(sample4DNifti1)[..., 0]
    newImage = sample4DNifti1.__class__(newData, sample4DNifti1.affine,
                                        sample4DNifti1.header)

    return BidsIncremental(image=newImage,
                           imageMetadata=imageMetadata)


def archiveWithImage(image, metadata: dict, tmpdir):
    """
    Create an archive on disk by hand with the provided image and metadata
    """
    # Create ensured empty directory
    while True:
        id = str(randint(0, 1e6))
        rootPath = Path(tmpdir, f"dataset-{id}/")
        if not Path.exists(rootPath):
            rootPath.mkdir()
            break

    # Create the archive by hand, with default readme and dataset description
    Path(rootPath, 'README').write_text(DEFAULT_README)
    Path(rootPath, 'dataset_description.json') \
        .write_text(json.dumps(DEFAULT_DATASET_DESC))

    # Write the nifti image & metadata
    dataPath = Path(rootPath, bids_build_path(metadata, BIDS_DIR_PATH_PATTERN))
    dataPath.mkdir(parents=True)

    filenamePrefix = bids_build_path(metadata, BIDS_FILE_PATTERN)
    imagePath = Path(dataPath, filenamePrefix + '.nii')
    metadataPath = Path(dataPath, filenamePrefix + '.json')

    nib.save(image, str(imagePath))

    # BIDS Incremental takes care of this automatically, but must be done
    # manually here
    metadata['TaskName'] = metadata['task']
    metadataPath.write_text(json.dumps(metadata))
    del metadata['TaskName']

    # BIDS-I's takes care of event file creation automatically, but must be done
    # manually here
    metadata['suffix'] = 'events'
    metadata['extension'] = '.tsv'

    eventsPath = Path(dataPath, bids_build_path(metadata, BIDS_FILE_PATTERN))
    df = pd.DataFrame(columns=DEFAULT_EVENTS_HEADERS)
    df = correctEventsFileDatatypes(df)
    writeDataFrameToEvents(df, str(eventsPath))

    # Create an archive from the directory and return it
    return BidsArchive(rootPath)


"""
TODO(spolcyn): Support anatomical data in BIDS-I and get anatomical input DICOM
# BIDS Archive with a single 3-D image (anatomical, as functional BOLD data must
# be in 4-D images
@pytest.fixture(scope='function')
def bidsArchive3D(tmpdir, sample3DNifti1, imageMetadata):
    metadata = imageMetadata.copy()

    adjustTimeUnits(metadata)
    metadata['datatype'] = 'anat'
    metadata['suffix'] = None

    return archiveWithImage(sample3DNifti1, metadata, tmpdir)
"""


# BIDS Archive with a 4-D image
@pytest.fixture(scope='function')
def bidsArchive4D(tmpdir, sample4DNifti1, imageMetadata):
    metadata = imageMetadata.copy()
    adjustTimeUnits(metadata)
    return archiveWithImage(sample4DNifti1, metadata, tmpdir)


# BIDS Archive with multiple runs for a single subject
@pytest.fixture(scope='function')
def bidsArchiveMultipleRuns(tmpdir, sample4DNifti1, imageMetadata):
    metadata = imageMetadata.copy()
    adjustTimeUnits(metadata)
    archive = archiveWithImage(sample4DNifti1, metadata, tmpdir)

    metadata = imageMetadata.copy()
    adjustTimeUnits(metadata)
    metadata['run'] = int(metadata['run']) + 1

    incremental = BidsIncremental(sample4DNifti1, metadata)
    archive._appendIncremental(incremental)

    return archive


""" END BIDS RELATED FIXTURES """
