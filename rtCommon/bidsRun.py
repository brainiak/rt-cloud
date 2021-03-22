"""-----------------------------------------------------------------------------

bidsRun.py

Implements the BIDS Run data type used for representing full fMRI scanning runs
as sequences of BIDS incrementals.

-----------------------------------------------------------------------------"""
import logging

import numpy as np

from rtCommon.bidsCommon import (
    getNiftiData,
    metadataAppendCompatible,
    niftiImagesAppendCompatible,
    symmetricDictDifference,
)
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.errors import MetadataMismatchError

logger = logging.getLogger(__name__)


class BidsRun:
    def __init__(self, **entities):
        self.incrementals = []
        self._entities = entities

    def __eq__(self, other):
        if self.numIncrementals() == other.numIncrementals():
            if self.getRunEntities() == other.getRunEntities():
                if self.incrementals == other.incrementals:
                    return True
        return False

    def getIncremental(self, index: int) -> BidsIncremental:
        """
        Returns the incremental in the run at the provided index.

        Arguments:
            index: Which image of the run to get (0-indexed)

        Returns:
            Incremental at provided index.

        Raises:
            IndexError: If index is out of bounds for this run.

        Examples:
            >>> print(run.numIncrementals())
            5
            >>> inc = run.getIncremental(1)
            >>> inc2 = run.getIncremental(5)
            IndexError
        """
        try:
            return self.incrementals[index]
        except IndexError:
            raise IndexError(f"Index {index} out of bounds for run with "
                             f"{self.numIncrementals()} incrementals")

    def appendIncremental(self, incremental: BidsIncremental,
                          validateAppend: bool = True) -> None:
        """
        Appends an incremental to this run's data, setting the run's entities if
        the run is empty.

        Arguments:
            incremental: The incremental to add to the run.
            validateAppend: Validate the incremental matches the current run's
                data (default True). Turning off is useful for efficiently
                creating a whole run at once from an existing image volume,
                where all data is known to be match already.

        Raises:
            MetadataMismatchError: If either the incremental's entities, its
                images's NIfTI header, or its metadata doesn't match the
                existing run's data.

        Examples:
            Suppose a NIfTI image and metadata dictionary are available in the
            environment.

            >>> incremental = BidsIncremental(image, metadata)
            >>> run = BidsRun()
            >>> run.appendIncremental(incremental)
            >>> metadata['subject'] = 'new_subject'
            >>> incremental2 = BidsIncremental(image, metadata)
            >>> run.appendIncremental(incremental2)
            MetadataMismatchError
        """
        # Set this run's entities if not already present
        if len(self._entities) == 0:
            self._entities = incremental.entities

        if validateAppend:
            if not incremental.entities == self._entities:
                entityDifference = symmetricDictDifference(self._entities,
                                                           incremental.entities)
                errorMsg = ("Incremental's BIDS entities do not match this "
                            f"run's entities (difference: {entityDifference})")
                raise MetadataMismatchError(errorMsg)

            if self.numIncrementals() > 0:
                canAppend, niftiErrorMsg = \
                    niftiImagesAppendCompatible(incremental.image,
                                                self.incrementals[-1].image)

                if not canAppend:
                    errorMsg = ("Incremental's NIfTI header not compatible "
                                f" with this run's images ({niftiErrorMsg})")
                    raise MetadataMismatchError(errorMsg)

                canAppend, metadataErrorMsg = metadataAppendCompatible(
                    incremental.imageMetadata,
                    self.incrementals[-1].imageMetadata)

                if not canAppend:
                    errorMsg = ("Incremental's metadata not compatible "
                                f" with this run's images ({metadataErrorMsg})")
                    raise MetadataMismatchError(errorMsg)

        # Slice up the incremental into smaller incrementals if it has multiple
        # images in its image volume
        imagesInVolume = incremental.imageDimensions[3]
        if imagesInVolume == 1:
            self.incrementals.append(incremental)
        else:
            # Split up the incremental into single-image volumes
            image = incremental.image
            imageData = getNiftiData(image)
            affine = image.affine
            header = image.header
            metadata = incremental.imageMetadata

            for imageIdx in range(imagesInVolume):
                newData = imageData[..., imageIdx]
                newImage = incremental.image.__class__(newData, affine, header)
                newIncremental = BidsIncremental(newImage, metadata)
                self.incrementals.append(newIncremental)

    def asSingleIncremental(self) -> BidsIncremental:
        """
        Coalesces the entire run into a single BIDS-I that can be sent over a
        network, written to disk, or added to an archive.

        Returns:
            BidsIncremental with all image data and metadata represented by the
                incrementals composing the run.

        Examples:
            >>> incremental = run.asSingleIncremental()
            >>> incremental.writeToDisk('/tmp/new_dataset')
        """
        numIncrementals = self.numIncrementals()
        refIncremental = self.getIncremental(0)
        newImageShape = refIncremental.imageDimensions[:3] + (numIncrementals,)
        metadata = refIncremental.imageMetadata

        # It is critical to set the dtype of the array according to the source
        # image's dtype. Without doing so, int data may be cast to float (the
        # numpy default type for a new array), which Nibabel will then write
        # float data to disk using the NIfTI scl_scope header scaling field.
        # This procedure almost always results in less precision than offered by
        # the original ints, which means images at either end of a round-trip
        # (read image data/put image data in numpy array/save image data/read
        # image from disk) will have arrays with slightly different values.
        newDataArray = np.zeros(newImageShape, order='F',
                                dtype=refIncremental.image.dataobj.dtype)

        for incIdx in range(numIncrementals):
            incremental = self.getIncremental(incIdx)
            newDataArray[..., incIdx] = getNiftiData(incremental.image)[..., 0]

        newImage = refIncremental.image.__class__(newDataArray,
                                                  refIncremental.image.affine,
                                                  refIncremental.image.header)

        return BidsIncremental(newImage, metadata)

    def numIncrementals(self) -> int:
        """
        Returns number of incrementals in this run.
        """
        return len(self.incrementals)

    def getRunEntities(self) -> dict:
        """
        Returns dictionary of the BIDS entities associated with this run.

        Examples:
            >>> print(run.getRunEntities())
            {'subject': '01', 'session': '01', 'task': 'test', run: 1,
            'datatype': 'func', 'suffix': 'bold'}
        """
        return self._entities
