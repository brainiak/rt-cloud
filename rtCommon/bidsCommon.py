"""-----------------------------------------------------------------------------

bidsCommon.py

Shared constants and functions used by modules working with BIDS data.

-----------------------------------------------------------------------------"""
from enum import Enum
from operator import eq as opeq
from typing import Any, Callable, Tuple
import functools
import logging
import re

from bids.layout.models import Config as BidsConfig
import nibabel as nib
import numpy as np
import pandas as pd
import pydicom

logger = logging.getLogger(__name__)

# Version of the standard to be compatible with
BIDS_VERSION = "1.4.1"

# Required fields in the dataset_description.json file
DATASET_DESC_REQ_FIELDS = ["Name", "BIDSVersion"]
DEFAULT_DATASET_DESC = {"Name": "bidsi_dataset",
                        "BIDSVersion": str(BIDS_VERSION),
                        "Authors": ["The RT-Cloud Authors",
                                    "The Dataset Author"]}

# Deafult readme text for RT-Cloud
DEFAULT_README = "Generated BIDS-Incremental Dataset from RT-Cloud"

# Required columns for the BIDS events files
DEFAULT_EVENTS_HEADERS = ['onset', 'duration']

# Pattern for creating BIDS filenames from all compatible fMRI entities
BIDS_FILE_PATTERN = "sub-{subject}[_ses-{session}]_task-{task}" \
                     "[_acq-{acquisition}][_ce-{ceagent}][_dir-{direction}]" \
                     "[_rec-{reconstruction}][_run-{run}][_echo-{echo}]" \
                     "[_recording-{recording}][_part-{part}]" \
                     "_{suffix<bold|cbv|sbref|events>}" \
                     "[{extension<.nii|.json|.tsv>}]"

# Pattern for creating BIDS archive directory path
BIDS_DIR_PATH_PATTERN = "sub-{subject}[/ses-{session}]/{datatype<func>|func}"

# Pattern for creating full path of BIDS file relative to archive root
BIDS_FILE_PATH_PATTERN = BIDS_DIR_PATH_PATTERN + '/' + BIDS_FILE_PATTERN

# 'Entities' reported by PyBids for files and used for searching, but that don't
# actually exist in the BIDS Standard and that shouldn't be output in an archive
PYBIDS_PSEUDO_ENTITIES = ['extension']

# https://bids-specification.readthedocs.io/en/stable/04-modality-specific-files/05-task-events.html
BIDS_EVENT_COL_TO_DTYPE = {'onset': 'float64',
                           'duration': 'float64',
                           'sample': 'float64',
                           'trial_type': 'object',
                           'response_time': 'float64',
                           'value': 'object',  # can be str or num
                           'HED': 'object'}


# Valid extensions for various file types in the BIDS format
class BidsFileExtension(Enum):
    IMAGE = '.nii'
    IMAGE_COMPRESSED = '.nii.gz'
    METADATA = '.json'
    EVENTS = '.tsv'


# BIDS Entitiy information dict
class BidsEntityKeys(Enum):
    ENTITY = "entity"
    FORMAT = "format"
    DESCRIPTION = "description"


# See test file for more specifics about expected format
@functools.lru_cache(maxsize=1)
def loadBidsEntities() -> dict:
    """
    Loads all accepted BIDS entities from PyBids into a dictionary.

    Returns:
        A dictionary mapping the entity names to the PyBids Entity object
            containing information about that entity.
    """
    # PyBids uses its own, internal bids.json to configure what entities it
    # accepts and what form they take. A custom config could be specified with a
    # full path name, but using just 'bids' will direct the PyBids Config class
    # to get the bids.json from its own internal package.
    BIDS_DEFAULT_CONFIG_NAME = 'bids'
    BIDS_DERIVATIES_CONFIG_NAME = 'derivatives'

    entities = {}
    for configName in [BIDS_DEFAULT_CONFIG_NAME, BIDS_DERIVATIES_CONFIG_NAME]:
        entities.update(BidsConfig.load(configName).entities)

    return entities


def filterEntities(metadata: dict) -> dict:
    """
    Returns a new dictionary containing all the elements of the argument that
    are valid BIDS entities.
    """
    entities = loadBidsEntities()
    return {key: metadata[key] for key in metadata if key in entities}


def getNiftiData(image: nib.Nifti1Image) -> np.ndarray:
    """
    Nibabel exposes a get_fdata() method, but this converts all the data to
    float64. Since our Nifti files are often converted from DICOM's, which store
    data in signed or unsigned ints, treating the data as float can cause issues
    when comparing images or re-writing a Nifti read in from disk.
    """
    return np.asanyarray(image.dataobj, dtype=image.dataobj.dtype)


def makeDicomFieldBidsCompatible(dicomField: str) -> str:
    """
    Remove non-alphanumeric characters to make a DICOM field name
    BIDS-compatible (CamelCase alphanumeric) metadata field.  Note: Multi-word
    keys like 'Frame of Reference UID' become 'FrameofReferenceUID', which might
    be different than the expected behavior

    Args:
        dicomField: Name of the DICOM field to convert to BIDS format

    Returns:
        DICOM field name in BIDS-compatible format.

    Examples:
        >>> field = "Repetition Time"
        >>> makeDicomFieldBidsCompatible(field)
        'RepetitionTime'
    """
    return re.compile('[^a-zA-z]').sub("", dicomField)


# From official nifti1.h
UNIT_TO_CODE = {'unknown': 0, 'meter': 1, 'mm': 2, 'micron': 3, 'sec': 8,
                'msec': 16, 'usec': 24, 'hz': 32, 'ppm': 40, 'rads': 48}
CODE_TO_UNIT = {UNIT_TO_CODE[key]: key for key in UNIT_TO_CODE.keys()}


def correct3DHeaderTo4D(image: nib.Nifti1Image, repetitionTime: int,
                        timeUnitCode: int = 8) -> None:
    """
    Makes necessary changes to the NIfTI header to reflect the increase in its
    corresponding image's data shape from 3D to 4D.

    Args:
        image: NIfTI image to modify header for
        repetitionTime: Repetition time for the scan that produced the image
        timeUnitCode: The temporal dimension NIfTI unit code (e.g., millimeters
            is 2, seconds is 8). Defaults to seconds.
    """
    oldShape = image.header.get_data_shape()
    dimensions = len(oldShape)
    if dimensions < 3 or dimensions > 4:
        raise ValueError(f'Image must be 3-D or 4-D (got {dimensions}-D)')

    # dim - only update if currently 3D (possible given 4D image whose data has
    # been changed, and dim is correct but pixdim/xyzt_units need correcting)
    if dimensions == 3:
        newShape = (*oldShape, 1)
        logger.debug(f"Shape old: {oldShape} | Shape new: {newShape}")
        image.header.set_data_shape(newShape)

    # pixdim
    oldZooms = image.header.get_zooms()
    if len(oldZooms) == 3:
        newZooms = (*oldZooms, repetitionTime)
    elif len(oldZooms) == 4:
        newZooms = (*oldZooms[0:3], repetitionTime)
    logger.debug(f"Zooms old: {oldZooms} | Zooms new: {newZooms}")
    image.header.set_zooms(newZooms)

    # xyzt_units
    oldUnits = image.header.get_xyzt_units()
    newUnits = (oldUnits[0], timeUnitCode)
    image.header.set_xyzt_units(xyz=newUnits[0], t=newUnits[1])
    logger.debug(f"Units old: {oldUnits} | Units new: {newUnits}")


def adjustTimeUnits(imageMetadata: dict) -> None:
    """
    Validates and converts in-place the units of various time-based metadata,
    which is stored in seconds in BIDS, but often provided using milliseconds in
    DICOM.
    """
    fieldToMaxValue = {"RepetitionTime": 100, "EchoTime": 1}
    for field, maxValue in fieldToMaxValue.items():
        value = imageMetadata.get(field, None)
        if value is None:
            continue
        else:
            value = float(value)

        if value <= maxValue:
            imageMetadata[field] = value
        elif value / 1000.0 <= maxValue:
            logger.info(f"{field} has value {value} > {maxValue}. Assuming "
                        f"value is in milliseconds, converting to seconds.")
            imageMetadata[field] = value / 1000.0
        else:
            raise ValueError(f"{field}'s max value is {maxValue}; {value} > "
                             f"{maxValue} even if interpreted as milliseconds.")


def metadataFromProtocolName(protocolName: str) -> dict:
    """
    Extracts BIDS label-value combinations from a DICOM protocol name, if
    any are present.

    Returns:
        A dictionary containing any valid label-value combinations found.
    """
    if not protocolName:
        return {}

    foundEntities = {}
    for entity in loadBidsEntities().values():
        result = re.search(entity.pattern, protocolName)

        if result is not None and len(result.groups()) == 1:
            foundEntities[entity.name] = result.group(1)

    return foundEntities


def getDicomMetadata(dicomImg: pydicom.dataset.Dataset, kind='all') -> dict:
    """
    Returns the public (even-numbered tags) and private (odd-numbered tags)
    metadata from the provided DICOM image.

    Args:
        dicomImg: A Pydicom object to read metadata from.
        kind: Metadata category to get. 'public' for public DICOM tags,
            'private' for private DICOM tags, 'all' for all DICOM tags.

    Returns:
        Dictionary containing requested metadata from the DICOM image.

    Raises:
        TypeError: If the image provided is not a pydicom.dataset.Dataset object
            (e.g., if the image were the raw DICOM data).
    """
    if not isinstance(dicomImg, pydicom.dataset.Dataset):
        raise TypeError("Expected pydicom.dataset.Dataset as argument")

    metadata = {}
    STORE_PRIVATE = (kind == 'all' or kind == 'private')
    STORE_PUBLIC = (kind == 'all' or kind == 'public')

    ignoredTags = ['Pixel Data']  # the image's raw data is not metadata

    for elem in dicomImg:
        if elem.name in ignoredTags:
            continue

        cleanedKey = makeDicomFieldBidsCompatible(elem.name)
        # in DICOM, public tags have even group numbers and private tags are odd
        # http://dicom.nema.org/dicom/2013/output/chtml/part05/chapter_7.html
        value = str(elem.value)

        if elem.tag.is_private:
            if STORE_PRIVATE:
                metadata[cleanedKey] = value
        elif STORE_PUBLIC:
            metadata[cleanedKey] = value

    return metadata


def symmetricDictDifference(d1: dict, d2: dict,
                            equal: Callable[[Any, Any], bool] = opeq) -> dict:
    """
    Returns the symmetric difference of the provided dictionaries. This
    consists of 3 parts:
    1) Key-value pairs for which both dictionaries have the key, but have
    different values for that key.
    2) All key-value pairs that only the first dictionary has.
    3) All key-value pairs that only the second dictionary has.

    Arguments:
        d1: First dictionary
        d2: Second dictionary
        equal: Function that returns True if two keys are equal, False otherwise

    Returns:
        A dictionary with all key-value pair differences between the two
        dictionaries. 'None' is used as the value for a key-value pair if that
        dictionary lacks a key that the other one has.

    Examples:
        >>> d1 = {'a': 1, 'b': 2, 'c': 3}
        >>> d2 = {'c': 4, 'd': 5}
        >>> print(symmetricDictDifference(d1, d2))
        {'a': [1, None], 'b': [2, None], 'c': [3, 4], 'd': [None, 5]}
        >>> d2 = {'a': 1, 'b': 2, 'c': 4}
        >>> print(symmetricDictDifference(d1, d2))
        {'c': [3, 4]}
    """

    sharedKeys = d1.keys() & d2.keys()
    difference = {key: [d1[key], d2[key]]
                  for key in sharedKeys
                  if not equal(d1[key], d2[key])}

    d1OnlyKeys = d1.keys() - d2.keys()
    difference.update({key: [d1[key], None] for key in d1OnlyKeys})

    d2OnlyKeys = d2.keys() - d1.keys()
    difference.update({key: [None, d2[key]] for key in d2OnlyKeys})

    return difference


def niftiHeadersAppendCompatible(header1: dict, header2: dict):
    """
    Verifies that two Nifti image headers match in along a defined set of
    NIfTI header fields which should not change during a continuous fMRI
    scanning session.

    This is primarily intended as a safety check, and does not conclusively
    determine that two images are valid to append to together or are part of
    the same scanning session.

    Args:
        header1: First Nifti header to compare (dict of numpy arrays)
        header2: Second Nifti header to compare (dict of numpy arrays)

    Returns:
        True if the headers match along the required dimensions, False
        otherwise.

    """
    fieldsToMatch = ["intent_p1", "intent_p2", "intent_p3", "intent_code",
                     "dim_info", "datatype", "bitpix",
                     "slice_duration", "toffset", "scl_slope", "scl_inter",
                     "qform_code", "quatern_b", "quatern_c", "quatern_d",
                     "qoffset_x", "qoffset_y", "qoffset_z",
                     "sform_code", "srow_x", "srow_y", "srow_z"]

    for field in fieldsToMatch:
        v1 = header1.get(field)
        v2 = header2.get(field)

        # Use slightly more complicated check to properly match nan values
        if not (np.allclose(v1, v2, atol=0.0, equal_nan=True)):
            errorMsg = (f"NIfTI headers don't match on field: {field} "
                        f"(v1: {v1}, v2: {v2})")
            return (False, errorMsg)

    # Two NIfTI headers are append-compatible in 2 cases:
    #
    # 1) Pixel dimensions are equal for all defined dimensions, and dimensions
    # are equal across the xyz dimensions (last dimension, time, can be equal or
    # not). Note that the number of dimensions is defined in the 'dim' field,
    # and that sometimes the pixel dimensions or dimensions field will have 0's
    # or 1's beyond the defined number of dimensions; these should be ignored
    # for determining append compatibility, as they are irrelevant.
    #
    # 2) One image has one fewer dimension than the other, and all shared
    # dimensions and pixel dimensions are exactly equal

    # 'dim' corresponds to the dimensions of the image
    dimensions1 = header1.get("dim")
    dimensions2 = header2.get("dim")

    # In NIfTI, the 0th index of the 'dim' field is the # of dimensions
    nDimensions1 = dimensions1[0]
    nDimensions2 = dimensions2[0]

    # 'pixdim' corresponds to the size of each pixel in real-world units
    # (e.g., mm, um, etc.)
    pixdim1 = header1.get("pixdim")
    pixdim2 = header2.get("pixdim")

    dimensionMatch = False
    # Case 1
    if nDimensions1 == nDimensions2:
        pixdimEqual = np.array_equal(pixdim1[:nDimensions1 + 1],
                                     pixdim2[:nDimensions2 + 1])
        xyzEqual = np.array_equal(dimensions1[:nDimensions1],
                                  dimensions2[:nDimensions2])

        if pixdimEqual and xyzEqual:
            dimensionMatch = True
    # Case 2
    else:
        dimensionsDifferBy1 = abs(nDimensions1 - nDimensions2) == 1
        if dimensionsDifferBy1:

            nSharedDimensions = min(nDimensions1, nDimensions2)
            # Arrays are 1-indexed as # dimensions is stored in first slot
            sharedDimensionsMatch = \
                np.array_equal(dimensions1[1:nSharedDimensions + 1],
                               dimensions2[1:nSharedDimensions + 1])
            if sharedDimensionsMatch:
                # Arrays are 1-indexed, which matches how the "dim" array
                # lists the number of dimensions first (index 0), and then
                # the dimension in its corresponpding slot (i.e., 1st
                # dimension in index 1). The pixel dimensions should be
                # equal across images.
                sharedPixdimMatch = \
                    np.array_equal(pixdim1[:nSharedDimensions + 1],
                                   pixdim2[:nSharedDimensions + 1])
                if sharedPixdimMatch:
                    dimensionMatch = True

    if not dimensionMatch:
        errorMsg = ("NIfTI headers not append compatible due to mismatch "
                    "in dimensions and pixdim fields.\n"
                    f"Dim 1: {dimensions1} | Dim 2: {dimensions2}\n"
                    f"Pixdim 1: {pixdim1} | Pixdim 2: {pixdim2}\n")
        return (False, errorMsg)

    # Compare xyzt_units (spatial and temporal dimension units)
    field = 'xyzt_units'
    xyztUnits1 = header1[field]
    xyztUnits2 = header2[field]

    # NOTE: If units are 'unknown' (represented by value 0, in NIfTi
    # header), then we assume the header is incomplete and don't thrown an
    # error. Errors are only thrown when explicit conflicts are found
    # between defined and non-matching units.

    # If all units are unknown, don't bother checking sub-units as they'll
    # also be 0
    if xyztUnits1 == 0 or xyztUnits2 == 0:
        unitsMatch = True
    else:
        # Bottom 3 bits of xyzt units is dedicated to the spatial units.
        # Thus, modding by 2^3 = 8 leaves just those bits.
        spatialUnits1 = xyztUnits1 % 8
        spatialUnits2 = xyztUnits2 % 8
        spatialUnknown = spatialUnits1 == 0 or spatialUnits2 == 0
        if spatialUnknown:
            spatialMatch = True
        else:
            spatialMatch = np.array_equal(spatialUnits1, spatialUnits2)

        # Next 3 bits of xyzt units dedicated to temopral units. Thus,
        # subtracting out the spatial units' contribution leaves just the
        # temporal units.
        temporalUnits1 = xyztUnits1 - spatialUnits1
        temporalUnits2 = xyztUnits2 - spatialUnits2
        temporalUnknown = temporalUnits1 == 0 or temporalUnits2 == 0
        if temporalUnknown:
            temporalMatch = True
        else:
            temporalMatch = np.array_equal(temporalUnits1, temporalUnits2)

        unitsMatch = (spatialMatch and temporalMatch)

    if not unitsMatch:
        errorMsg = (
            f"NIfTI headers not append compatible due to mismatch in "
            f"xyzt_units field (spatial match: {spatialMatch}, "
            f"temporal match: {temporalMatch}. "
            f"xyzt_units 1: {xyztUnits1} | xyzt_units 2: {xyztUnits2}")
        return (False, errorMsg)

    return (True, "")


def niftiImagesAppendCompatible(img1: nib.Nifti1Image,
                                img2: nib.Nifti1Image) -> Tuple[bool, str]:
    """
    Verifies that two Nifti images have headers matching along a defined set of
    NIfTI header fields which should not change during a continuous fMRI
    scanning session.

    This is primarily intended as a safety check, and does not conclusively
    determine that two images are valid to append to together or are part of the
    same scanning session.

    Args:
        img1: First Nifti image to compare
        img2: Second Nifti image to compare

    Returns:
        True if the image headers match along the required dimensions, False
            otherwise.

    """
    return niftiHeadersAppendCompatible(img1.header, img2.header)


def metadataAppendCompatible(meta1: dict, meta2: dict) -> Tuple[bool, str]:
    """
    Verifies two metadata dictionaries match in a set of required fields. If a
    field is present in only one or neither of the two dictionaries, this is
    considered a match.

    This is primarily intended as a safety check, and does not conclusively
    determine that two images are valid to append to together or are part of the
    same series.

    Args:
        meta1: First metadata dictionary
        meta2: Second metadata dictionary

    Returns:
        True if all keys that are present in both dictionaries have equivalent
            values, false otherwise.

    """
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

    # If a particular metadata field is not defined (i.e., 'None'), then
    # there can't be a conflict in value; thus, short-circuit and skip the
    # rest of the check if a None value is found for a field.
    for field in matchFields:
        value1 = meta1.get(field, None)
        if value1 is None:
            continue

        value2 = meta2.get(field, None)
        if value2 is None:
            continue

        if value1 != value2:
            errorMsg = (f"Metadata doesn't match on field: {field} "
                        f"(value 1: {value1}, value 2: {value2}")
            return (False, errorMsg)

    return (True, "")


# Given Pandas DataFrame representation of an events file, sets the datatypes to
# match the BIDS Standard
def correctEventsFileDatatypes(df: pd.DataFrame) -> pd.DataFrame:
    # The Pandas astype method throws an error if any columns it's asked to
    # switch the dtypes of aren't present, so pre-filter the columns to be only
    # the ones that are present in the DataFrame to process
    targetColsToDtypes = {col: dtype for col, dtype in
                          BIDS_EVENT_COL_TO_DTYPE.items() if col in df.columns}
    return df.astype(targetColsToDtypes)


# Writes out a BIDS events file with proper formatting from a Pandas dataframe
def writeDataFrameToEvents(df: pd.DataFrame, path: str) -> None:
    # Tab-separated file without the Pandas index written out (including the
    # Pandas index adds a spurious column in the first position of the TSV file
    # that confuses later readers of the file)
    with open(path, mode='w') as eventsFile:
        df.to_csv(eventsFile, index=False, sep='\t')
