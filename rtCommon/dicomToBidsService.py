"""-----------------------------------------------------------------------------

dicomToBidsService.py

A very basic DICOM to BIDS-I converter.

-----------------------------------------------------------------------------"""

import pydicom

from rtCommon.bidsCommon import getDicomMetadata
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.imageHandling import convertDicomImgToNifti


def dicomToBidsInc(dicomImg: pydicom.dataset.Dataset,
                   extraMetadata: dict = {}) -> BidsIncremental:
    # TODO(spolcyn): Do this all in memory -- dicom2nifti is promising
    # Currently, there are 4 disk operations:
    # 1) Read DICOM (by dcm2niix)
    # 2) Write NIfTI
    # 3) Read NIfTI
    # 4) Read DICOM (for metadata)

    # NOTE: This is not the final version of this method.
    # The conversion from DICOM to BIDS-I and gathering all required metadata
    # can be complex, as DICOM doesn't necessarily have the metadata required
    # for BIDS in it by default. Thus, another component should handle the logic
    # and error handling surrounding this.
    niftiImage = convertDicomImgToNifti(dicomImg)
    metadata = getDicomMetadata(dicomImg)
    metadata.update(extraMetadata)

    return BidsIncremental(image=niftiImage, imageMetadata=metadata)
