"""-----------------------------------------------------------------------------

bidsIncremental.py (Last Updated: 10/22/20)

This script includes all of the functions that are needed to convert between
DICOM, BIDS-Incremental (BIDS-I), and BIDS formats.

-----------------------------------------------------------------------------"""

import pydicom
import re
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
    # DICOM key names by removing non-alphanumeric characters
    # NOTE: Keys like 'Frame of Reference UID' become 'FrameofReferenceUID',
    # which might be different than the expected behavior
    removalRegex = re.compile('[^a-zA-z]')
    ignoredTags = ['Pixel Data']

    for elem in dicomImg:
        if elem.name in ignoredTags:
            continue

        cleanedKey = removalRegex.sub("", elem.name)
        # in DICOM, public tags have even group numbers and private tags are odd
        # http://dicom.nema.org/dicom/2013/output/chtml/part05/chapter_7.html
        if elem.tag.group % 2 == 0:
            publicMeta[cleanedKey] = str(elem.value)
        else:
            privateMeta[cleanedKey] = str(elem.value)

    return (publicMeta, privateMeta)
