# Creates the various test NIfTI files used in the test suite from the source
# DICOM image

import os
import logging

import nibabel as nib
import numpy as np

from rtCommon.imageHandling import convertDicomFileToNifti
from rtCommon.bidsCommon import correct3DHeaderTo4D
from tests.common import (
    test_dicomPath,
    test_3DNifti1Path,
    test_3DNifti2Path,
    test_4DNifti1Path,
    test_4DNifti2Path
)

logger = logging.getLogger(__name__)

ALL_TEST_FILE_PATHS = [test_3DNifti1Path, test_3DNifti2Path,
                       test_4DNifti1Path, test_4DNifti2Path]


def haveAllNiftiTestFiles():
    for path in ALL_TEST_FILE_PATHS:
        if not os.path.exists(path):
            logger.warning("Don't have required test file: %s", path)
            return False

    return True

def deleteNiftiTestFiles():
    """
    Delete existing existing NIfTI files with target names to avoid dcm2niix
    creating lots of duplicates with different names
    """
    for path in ALL_TEST_FILE_PATHS:
        if os.path.exists(path):
            logger.info("Removing existing: %s", path)
            os.remove(path)


def createNiftiTestFiles(shouldValidate: bool = True):
    """
    Create base 3D NIfTI1 file all others are created from
    """
    convertDicomFileToNifti(test_dicomPath, test_3DNifti1Path)

    # When loading a NIfTI image, a mmap is created to its data. When
    # overwriting that same image using the mmap'd data, sometimes a bus error
    # can occur. This is because the file is truncated when writing starts, so
    # the mmap doesn't point to data anymore. Loading the file into memory
    # (mmap=False) fixes this issue.
    nifti1_3D = nib.load(test_3DNifti1Path, mmap=False)

    # Extract the TR time, then eliminate pixel dimension data past 3rd
    # dimension, as a 3D image really should only have 3D data, and having more
    # can complicate later comparisons.

    # these values are correct for the DICOM we have, but is not robust
    TR_TIME = nifti1_3D.header['pixdim'][4]
    nifti1_3D.header['pixdim'][4:] = 1

    # TODO(spolcyn): Take datatype, units, etc from the DICOM directly
    nifti1_3D.header['datatype'] = 512  # unsigned short -
    nifti1_3D.header['xyzt_units'] = 2  # just millimeters
    nib.save(nifti1_3D, test_3DNifti1Path)

    """
    Create NIfTI2 version of 3D base
    """
    nifti2_3D = nib.Nifti2Image(nifti1_3D.dataobj,
                                nifti1_3D.affine,
                                nifti1_3D.header)
    nib.save(nifti2_3D, test_3DNifti2Path)

    """
    Create 4D Nifti1 from base 3D Nifti1
    """

    # This method copied *exactly* from nibabel/funcs.py, except for adding the
    # dtype specifier to the out_data = np.empty(...) line
    def concat_images_patched(images, check_affines=True, axis=None):
        r""" Concatenate images in list to single image, along specified dimension
        Parameters
        ----------
        images : sequence
           sequence of ``SpatialImage`` or filenames of the same dimensionality\s
        check_affines : {True, False}, optional
           If True, then check that all the affines for `images` are nearly
           the same, raising a ``ValueError`` otherwise.  Default is True
        axis : None or int, optional
            If None, concatenates on a new dimension.  This requires all images to
            be the same shape.  If not None, concatenates on the specified
            dimension.  This requires all images to be the same shape, except on
            the specified dimension.
        Returns
        -------
        concat_img : ``SpatialImage``
           New image resulting from concatenating `images` across last
           dimension
        """
        images = [nib.load(img) if not hasattr(img, 'get_data')
                  else img for img in images]
        n_imgs = len(images)
        if n_imgs == 0:
            raise ValueError("Cannot concatenate an empty list of images.")
        img0 = images[0]
        affine = img0.affine
        header = img0.header
        klass = img0.__class__
        shape0 = img0.shape
        n_dim = len(shape0)
        if axis is None:
            # collect images in output array for efficiency
            out_shape = (n_imgs, ) + shape0
            out_data = np.empty(out_shape, dtype=img0.header.get_data_dtype())
        else:
            # collect images in list for use with np.concatenate
            out_data = [None] * n_imgs
        # Get part of shape we need to check inside loop
        idx_mask = np.ones((n_dim,), dtype=bool)
        if axis is not None:
            idx_mask[axis] = False
        masked_shape = np.array(shape0)[idx_mask]
        for i, img in enumerate(images):
            if len(img.shape) != n_dim:
                raise ValueError(f'Image {i} has {len(img.shape)} dimensions, image 0 has {n_dim}')
            if not np.all(np.array(img.shape)[idx_mask] == masked_shape):
                raise ValueError(f'shape {img.shape} for image {i} not compatible with '
                                 f'first image shape {shape0} with axis == {axis}')
            if check_affines and not np.all(img.affine == affine):
                raise ValueError(f'Affine for image {i} does not match affine for first image')
            # Do not fill cache in image if it is empty
            out_data[i] = np.asanyarray(img.dataobj)

        if axis is None:
            out_data = np.rollaxis(out_data, 0, out_data.ndim)
        else:
            out_data = np.concatenate(out_data, axis=axis)

        return klass(out_data, affine, header)

    """
    Create 4D Nifti1 from base 3D Nifti1
    """
    nifti1_4D = concat_images_patched([nifti1_3D, nifti1_3D])

    # TODO(spolcyn): Set this progamatically according to DICOM datatype
    nifti1_4D.header["datatype"] = 512  # unsigned short
    nifti1_4D.header['bitpix'] = 16  # 16 bits for unsigned short
    correct3DHeaderTo4D(nifti1_4D, repetitionTime=TR_TIME)
    nib.save(nifti1_4D, test_4DNifti1Path)

    """
    Create 4D Nifti2 from 3D Nifti2
    """
    nifti2_4D = nib.concat_images([nifti2_3D, nifti2_3D])
    correct3DHeaderTo4D(nifti2_4D, repetitionTime=TR_TIME)
    nib.save(nifti2_4D, test_4DNifti2Path)

    if not shouldValidate:
        return

    """
    Validate created Nifti files by comparing headers and data that should match
    """

    """ Helpers for validation """
    # https://brainder.org/2015/04/03/the-nifti-2-file-format/
    NIFTI2_REMOVED_FIELDS = ['data_type', 'db_name', 'extents', 'session_error',
                             'regular', 'glmin', 'glmax']
    NIFTI2_CHANGED_FIELDS = ['sizeof_hdr', 'magic']

    def headersMatch(niftiA, niftiB,
                     ignoredKeys: list = [],
                     specialHandlers: dict = {}) -> bool:
        """
        Verify that two NIfTI headers match. A list of keys to ignore can be
        provided (e.g., if comparing NIfTI1 and NIfTI2) or special handlers for
        particular keys (e.g., a 3D NIfTI and 4D NIfTI that should match in the
        first 3 dimensions of their shape).

        Args:
            niftiA, niftiB: NiBabel NIfTI images with headers
            ignoredKeys: Keys to skip comparing
            specialHandlers: Map of field name to function taking two arguments,
                returning 'true' if the values should be considered equal, false
                otherwise.

        Returns:
            True if the headers are equal, false otherwise.
        """
        header1 = niftiA.header
        header2 = niftiB.header

        for key in header1:
            if key in ignoredKeys:
                continue

            v1 = header1.get(key, None)
            v2 = header2.get(key, None)

            if np.array_equal(v1, v2):
                continue
            # Check for nan equality
            else:
                if np.issubdtype(v1.dtype, np.inexact) and \
                        np.allclose(v1, v2, atol=0.0, equal_nan=True):
                    continue
                # If key is special and handler returns true, continue
                elif key in specialHandlers and \
                        specialHandlers[key](v1, v2):
                    continue
                else:
                    logger.warning("--------------------\n"
                                 "Difference found!"
                                 f"Key: {key}\nHeader 1: {v1}\nHeader 2: {v2}")
                    return False

        return True

    def dataMatch(niftiA, niftiB) -> bool:
        return np.array_equal(niftiA.dataobj, niftiB.dataobj)

    # Used when dimensions will increased by one in the 3D to 4D conversion
    def dim3Dto4DHandler(v1: np.ndarray, v2: np.ndarray) -> bool:
        return v1[0] + 1 == v2[0] and v1[4] + 1 == v2[4]

    # Used when pixdim is different in 4th dimension for a 4D image vs. 3D
    def pixdim3Dto4DHandler(v1: np.ndarray, v2: np.ndarray) -> bool:
        return np.array_equal(v1[1:3], v2[1:3])

    # Used when xyzt units is different in 4th (time) dimension for a 4D image
    # vs. 3D which doesn't have one
    def xyztunits3Dto4DHandler(v1: np.ndarray, v2: np.ndarray) -> bool:
        # all spatial units (m, mm, um) have codes < 8, % 8 removes any temporal
        # units
        return np.array_equal(v1 % 8, v2 % 8)

    handlerMap3Dto4D = {'dim': dim3Dto4DHandler, 'pixdim': pixdim3Dto4DHandler,
                        'xyzt_units': xyztunits3Dto4DHandler}

    """ Actual validation """

    """ 3D Nifti2 """
    ignoredKeys = NIFTI2_REMOVED_FIELDS + NIFTI2_CHANGED_FIELDS
    errorString = "{} for Nifti1 3D and Nifti2 3D did not match"

    assert type(nib.load(test_3DNifti2Path)) is nib.Nifti2Image
    assert headersMatch(nifti1_3D, nifti2_3D, ignoredKeys=ignoredKeys), \
        errorString.format("Headers")
    assert dataMatch(nifti1_3D, nifti2_3D), errorString.format("Image data")

    """ 4D Nifti1 """
    errorString = "{} for Nifti1 3D and Nifti1 4D did not match"

    # First compare to the 3D Nifti1 it's derived from
    assert headersMatch(nifti1_3D, nifti1_4D,
                        specialHandlers=handlerMap3Dto4D), \
        errorString.format("Headers")
    assert np.array_equal(nifti1_3D.dataobj, nifti1_4D.dataobj[..., 0])
    assert np.array_equal(nifti1_3D.dataobj, nifti1_4D.dataobj[..., 1])

    nifti1_4D_fromdisk = nib.load(test_4DNifti1Path)

    # Then ensure the in-memory and on-disk representation are the same
    assert headersMatch(nifti1_4D, nifti1_4D_fromdisk), \
        errorString.format("Headers")
    assert dataMatch(nifti1_4D, nifti1_4D_fromdisk), \
        errorString.format("Image data")

    """ 4D Nifti2 """
    errorString = "{} for Nifti2 3D and Nifti2 4D did not match"

    assert headersMatch(nifti2_3D, nifti2_4D,
                        specialHandlers=handlerMap3Dto4D), \
        errorString.format("Headers")
    assert np.array_equal(nifti2_3D.dataobj, nifti2_4D.dataobj[..., 0])
    assert np.array_equal(nifti2_3D.dataobj, nifti2_4D.dataobj[..., 1])

    """ 4D Nifti1 and 4D Nifti2 data """
    errorString = "{} for Nifti1 4D and Nifti2 4D did not match"

    ignoredKeys = NIFTI2_REMOVED_FIELDS + NIFTI2_CHANGED_FIELDS
    assert headersMatch(nifti1_4D, nifti2_4D, ignoredKeys=ignoredKeys), \
        errorString.format("Image data")
    assert dataMatch(nifti1_4D, nifti2_4D), errorString.format("Headers")
