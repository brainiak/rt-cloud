"""-----------------------------------------------------------------------------

bidsRun.py

Implements the BIDS Run data type used for representing full fMRI scanning runs
as sequences of BIDS incrementals.

-----------------------------------------------------------------------------"""
from copy import deepcopy
import logging
import warnings

import numpy as np
import pandas as pd

from rtCommon.bidsCommon import (
    metadataAppendCompatible,
    niftiHeadersAppendCompatible,
    symmetricDictDifference,
)
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.errors import MetadataMismatchError

logger = logging.getLogger(__name__)


class BidsRun:
    def __init__(self, **entities):
        self._dataArrays = []
        self._entities = entities
        self._imageMetadata = None
        self._imageHeader = None
        self._imageAffine = None
        self._imageKlass = None

        self._readme = None
        self._datasetDescription = None
        self._events = None

    def __eq__(self, other):
        if self.numIncrementals() != other.numIncrementals():
            return False
        if self.getRunEntities() != other.getRunEntities():
            return False
        if self._imageMetadata != other._imageMetadata:
            return False
        if not np.array_equal(self._imageHeader, other._imageHeader):
            return False
        if not np.array_equal(self._imageAffine, other._imageAffine):
            return False
        if self._imageKlass != other._imageKlass:
            return False
        if self._readme != other._readme:
            return False
        if self._datasetDescription != other._datasetDescription:
            return False
        if not pd.DataFrame.equals(self._events, other._events):
            return False
        for (arr1, arr2) in zip(self._dataArrays, other._dataArrays):
            if not np.array_equal(arr1, arr2):
                return False

        return True

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
            dataArray = self._dataArrays[index]
            image = self._imageKlass(dataArray, self._imageAffine,
                                     self._imageHeader)
            return BidsIncremental(image, self._imageMetadata)
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
            self._entities = incremental.getEntities()

        if self._imageMetadata is None:
            self._imageMetadata = incremental.getImageMetadata()

        if self._imageHeader is None:
            self._imageHeader = incremental.image.header.copy()

        if self._imageAffine is None:
            self._imageAffine = incremental.image.affine.copy()

        if self._imageKlass is None:
            self._imageKlass = incremental.image.__class__

        if self._readme is None:
            self._readme = incremental.readme

        if self._datasetDescription is None:
            self._datasetDescription = deepcopy(incremental.datasetDescription)

        if self._events is None:
            self._events = incremental.events.copy(deep=True)

        if validateAppend:
            entityDifference = \
                symmetricDictDifference(self._entities,
                                        incremental.getEntities())
            if len(entityDifference) != 0:
                # Two cases:
                # 1) New incremental matches all existing entities, and just
                # adds new, more specific ones (update run)
                # 2) New incremental doesn't match some existing entities (fail)
                mismatchKeys = [key for key in entityDifference.keys() if key
                                in self._entities]
                if len(mismatchKeys) == 0:
                    # Add new, more specific entities
                    self._entities.update(incremental.getEntities())
                else:
                    errorMsg = ("Incremental's BIDS entities do not match this "
                                "run's entities (difference: "
                                f"{entityDifference})")
                    raise MetadataMismatchError(errorMsg)

            if self.numIncrementals() > 0:
                canAppend, niftiErrorMsg = \
                    niftiHeadersAppendCompatible(incremental.image.header,
                                                 self._imageHeader)

                if not canAppend:
                    errorMsg = ("Incremental's NIfTI header not compatible "
                                f" with this run's images ({niftiErrorMsg})")
                    raise MetadataMismatchError(errorMsg)

                canAppend, metadataErrorMsg = metadataAppendCompatible(
                    incremental.getImageMetadata(),
                    self._imageMetadata)

                if not canAppend:
                    errorMsg = ("Incremental's metadata not compatible "
                                f" with this run's images ({metadataErrorMsg})")
                    raise MetadataMismatchError(errorMsg)

            # Verify readme
            if not incremental.readme == self._readme:
                errorMsg = ("Incremental's readme doesn't match run's readme "
                            "(incremental: {}, run: {})"
                            .format(incremental.readme, self._readme))
                raise MetadataMismatchError(errorMsg)

            # Verify dataset description
            datasetDescriptionDifference = \
                symmetricDictDifference(self._datasetDescription,
                                        incremental.datasetDescription)
            if len(datasetDescriptionDifference) != 0:
                errorMsg = ("Incremental's dataset description doesn't match "
                            "run's dataset description {}"
                            .format(datasetDescriptionDifference))
                raise MetadataMismatchError(errorMsg)

            # Verify first part of new events file matches all rows in existing
            # events file
            incrementalSubset = incremental.events.iloc[0:len(self._events)]
            if not incrementalSubset.equals(self._events):
                errorMsg = ("Run's existing events must be found in first part "
                            "of incremental's events file, weren't: "
                            "\nexisting:\n{existing}\n"
                            "\nnew:\n{new}\n".format(
                                existing=self._events, new=incrementalSubset))
                raise MetadataMismatchError(errorMsg)

        # Update events file with new events
        newRowSubset = incremental.events.iloc[len(self._events):]
        self._events = self._events.append(newRowSubset, ignore_index=True)

        # Slice up the incremental into smaller component images if it has
        # multiple images in its image volume
        imagesInVolume = incremental.getImageDimensions()[3]

        try:
            import indexed_gzip  # noqa
        except ImportError:
            warnings.warn("Package 'indexed_gzip' not available: appending BIDS"
                          " Incremental that uses a gzipped NIfTI file as its "
                          "underlying data source will be very slow. Install "
                          "the 'indexed_gzip' package with 'conda install "
                          "indexed_gzip' to improve performance.")

        # Slice the dataobj so we ensure that data is read into memory
        newArrays = [incremental.image.dataobj[..., imageIdx] for imageIdx in
                     range(imagesInVolume)]
        if len(self._dataArrays) == 0:
            self._dataArrays = newArrays
        else:
            self._dataArrays.extend(newArrays)

    def asSingleIncremental(self) -> BidsIncremental:
        """
        Coalesces the entire run into a single BIDS-I that can be sent over a
        network, written to disk, or added to an archive.

        Returns:
            BidsIncremental with all image data and metadata represented by the
                incrementals composing the run, or None if the run is empty.

        Examples:
            >>> incremental = run.asSingleIncremental()
            >>> incremental.writeToDisk('/tmp/new_dataset')
        """
        if self.numIncrementals() == 0:
            return None

        numIncrementals = self.numIncrementals()
        newImageShape = self._imageHeader.get_data_shape()[:3] + \
            (numIncrementals,)

        # It is critical to set the dtype of the array according to the source
        # image's dtype. Without doing so, int data may be cast to float (the
        # numpy default type for a new array), which Nibabel will then write
        # float data to disk using the NIfTI scl_scope header scaling field.
        # This procedure almost always results in less precision than offered by
        # the original ints, which means images at either end of a round-trip
        # (read image data/put image data in numpy array/save image data/read
        # image from disk) will have arrays with slightly different values.
        #
        # Also, note that pre-declaring the array and then using it as the out
        # array is substantially faster than just letting np.stack create and
        # return a new array, as of this writing (~60% faster on one test)
        newDataArray = np.empty(newImageShape, order='F',
                                dtype=self._dataArrays[0].dtype)
        np.stack(self._dataArrays, axis=3, out=newDataArray)

        newImage = self._imageKlass(newDataArray, self._imageAffine,
                                    self._imageHeader)

        return BidsIncremental(newImage, self._imageMetadata)

    def numIncrementals(self) -> int:
        """
        Returns number of incrementals in this run.
        """
        return len(self._dataArrays)

    def getRunEntities(self) -> dict:
        """
        Returns dictionary of the BIDS entities associated with this run.

        Examples:
            >>> print(run.getRunEntities())
            {'subject': '01', 'session': '01', 'task': 'test', run: 1,
            'datatype': 'func', 'suffix': 'bold'}
        """
        return self._entities
