"""-----------------------------------------------------------------------------

bidsIncremental.py (Last Updated: 10/22/20)

This script includes all of the functions that are needed to convert between
DICOM, BIDS-Incremental (BIDS-I), and BIDS formats.

-----------------------------------------------------------------------------"""

import pydicom
from rtCommon.errors import ValidationError


def getMetadata(dicomImg: pydicom.dataset.Dataset) -> (dict, dict):
    """
    Returns the public and private metadata from the provided DICOM image.

    Args:
        dicomImg: A pydicom object to read metadata from.
    Returns:
        Tuple of 2 dictionaries, the first containing the public metadata from
        the image and the second containing the private metadata.
    """
    if not isinstance(dicomImg, pydicom.dataset.Dataset):
        raise ValidationError("Expected pydicom.dataset.Dataset as argument")

    publicMeta = {}
    privateMeta = {}

    # BIDS recommends CamelCase for the key names, which can be obtained from
    # DICOM key names by removing spaces, apostrophes, and parantheses
    # NOTE: Keys like 'Frame of Reference UID' become 'FrameofReferenceUID',
    # which might be different than the expected behavior
    removalMap = {ord(c): None for c in " \'()-"}
    ignoredTags = ['Pixel Data']

    for elem in dicomImg:
        if elem.name in ignoredTags:
            continue

        toInsert = publicMeta if elem.tag.group % 2 == 0 else privateMeta
        toInsert[elem.name.translate(removalMap)] = str(elem.value)

    return (publicMeta, privateMeta)
