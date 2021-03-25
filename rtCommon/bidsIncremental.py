"""-----------------------------------------------------------------------------

bidsIncremental.py

Implements the BIDS Incremental data type used for streaming BIDS data between
different applications.

-----------------------------------------------------------------------------"""
from copy import deepcopy
from operator import eq as opeq
from typing import Any, Callable
import json
import os

from bids.layout import BIDSImageFile
from bids.layout.writing import build_path as bids_build_path
import logging
import nibabel as nib
import numpy as np
import pandas as pd

from rtCommon.bidsCommon import (
    BIDS_DIR_PATH_PATTERN,
    BIDS_FILE_PATTERN,
    BidsFileExtension,
    DATASET_DESC_REQ_FIELDS,
    DEFAULT_DATASET_DESC,
    PYBIDS_PSEUDO_ENTITIES,
    adjustTimeUnits,
    correct3DHeaderTo4D,
    filterEntities,
    getNiftiData,
    loadBidsEntities,
    metadataFromProtocolName,
    symmetricDictDifference,
)
from rtCommon.errors import MissingMetadataError

logger = logging.getLogger(__name__)


class BidsIncremental:
    ENTITIES = loadBidsEntities()
    REQUIRED_IMAGE_METADATA = ['subject', 'task', 'suffix', 'datatype',
                               'RepetitionTime']

    """
    BIDS Incremental data format suitable for streaming BIDS Archives
    """
    def __init__(self, image: nib.Nifti1Image, imageMetadata: dict,
                 datasetMetadata: dict = None):
        """
        Initializes a BIDS Incremental object with provided image and metadata.

        Args:
            image: NIfTI image as an NiBabel NiftiImage or PyBids BIDSImageFile
            imageMetadata: Metadata for image, which must include all variables
                in BidsIncremental.REQUIRED_IMAGE_METADATA.
            datasetMetadata: Top-level dataset metadata for the BIDS dataset
                to be placed in a dataset_description.json. Defaults to None and
                a default description is used.

        Raises:
            MissingMetadataError: If any required metadata is missing.
            TypeError: If the image is not an Nibabel Nifti1Image or
                Nifti2Image.

        Examples:
            >>> import nibabel as nib
            >>> imageMetadata = {'subject': '01', 'task': 'test',
                                 'suffix': 'bold', 'datatype': 'func',
                                 'RepetitionTime': 1.5}
            >>> image = nib.load('/tmp/testfile.nii')
            >>> datasetMetadata = {'Name': 'Example Dataset',
                                   'BIDSVersion': '1.5.1',
                                   'Authors': 'The RT-Cloud Authors'}
            >>> incremental = BidsIncremental(image, imageMetadata,
                datasetMetadata)
            >>> print(incremental)
            "Image shape: (64, 64, 27, 1); Metadata Key Count: 6; BIDS-I
            Version: 1"
        """
        # TODO(spolcyn): Enable a BIDS incremental to store an index that
        # specifies where the image should be inserted into the archive. This
        # would extend capabilities beyond just appending.

        """ Do basic input validation """
        # IMAGE
        validTypes = [nib.Nifti1Image, nib.Nifti2Image, BIDSImageFile]
        if image is None or type(image) not in validTypes:
            raise TypeError("Image must be one of " +
                            str([typ.__name__ for typ in validTypes]) +
                            f"(got {type(image)})")
        if type(image) is BIDSImageFile:
            image = image.get_image()

        # DATASET METADATA
        if datasetMetadata is not None:
            missingFields = [field for field in DATASET_DESC_REQ_FIELDS
                             if datasetMetadata.get(field, None) is None]
            if missingFields:
                raise MissingMetadataError(
                    f"Dataset description needs: {str(missingFields)}")

        """ Process, validate, and store image metadata """
        imageMetadata = self._preprocessMetadata(imageMetadata)
        self._exceptIfMissingMetadata(imageMetadata)
        self._imgMetadata = self._postprocessMetadata(imageMetadata)

        """ Store dataset metadata """
        if datasetMetadata is None:
            self.datasetMetadata = DEFAULT_DATASET_DESC
        else:
            self.datasetMetadata = deepcopy(datasetMetadata)

        """ Validate and store image """
        # Remove singleton dimensions past the 3rd dimension
        # Note: this function does not remove trailing 1's if the image is 3-D,
        # (i.e., 160x160x1 image will retain that shape), so a later check is
        # needed to ensure that the 3rd dimension is > 1
        image = nib.funcs.squeeze_image(image)

        # BIDS-I is currently used for BOLD data, and according to the BIDS
        # Standard, BOLD data must be in 4-D NIfTI files. Thus, upgrade 3-D to
        # 4-D images with singleton final dimension, if necessary.
        imageShape = image.shape
        if len(imageShape) < 3:
            raise ValueError("Image must have at least 3 dimensions")
        elif len(imageShape) == 3:
            if imageShape[2] <= 1:
                raise ValueError("Image's 3rd (and any higher) dimensions are "
                                 " <= 1, which means it is a 2D image; images "
                                 "must have at least 3 dimensions")

            newData = np.expand_dims(getNiftiData(image), -1)
            image = image.__class__(newData, image.affine, image.header)
            correct3DHeaderTo4D(image, self._imgMetadata['RepetitionTime'])

        assert len(image.shape) == 4

        self.image = image

        # Configure README
        self.readme = "Generated BIDS-Incremental Dataset from RT-Cloud"

        # Configure events file
        eventDefaultHeaders = ['onset', 'duration', 'response_time']
        self.events = pd.DataFrame(columns=eventDefaultHeaders)

        # BIDS-I version for serialization
        self.version = 1

    def __str__(self):
        return ("Image shape: {}; Metadata Key Count: {}; BIDS-I Version: {}"
                .format(self.imageDimensions,
                        len(self._imgMetadata.keys()),
                        self.version))

    def __eq__(self, other):
        def reportDifference(valueName: str, d1: dict, d2: dict,
                             equal: Callable[[Any, Any], bool] = opeq) -> None:
            logger.debug(valueName + " didn't match")
            difference = symmetricDictDifference(d1, d2, equal)
            logger.debug(valueName + " difference: %s", difference)

        # Compare image headers
        if self.image.header != other.image.header:
            reportDifference("Image headers",
                             dict(self.image.header),
                             dict(other.image.header),
                             np.array_equal)
            return False

        # Compare image metadata
        if self._imgMetadata != other._imgMetadata:
            reportDifference("Image metadata",
                             self._imgMetadata,
                             other._imgMetadata,
                             np.array_equal)
            return False

        # Compare full image data
        if not np.array_equal(self.imageData, other.imageData):
            differences = self.imageData != other.imageData
            logger.debug("Image data didn't match")
            logger.debug("Difference count: %d (%f%%)",
                         np.sum(differences),
                         np.sum(differences) / np.size(differences) * 100.0)
            return False

        # Compare dataset metadata
        if self.datasetMetadata != other.datasetMetadata:
            reportDifference("Dataset metadata",
                             self.datasetMetadata,
                             other.datasetMetadata)
            return False

        if not self.readme == other.readme:
            logger.debug(f"Readmes didn't match\nself: {self.readme}\n"
                         f"other: {other.readme}")
            return False

        if not pd.DataFrame.equals(self.events, other.events):
            logger.debug(f"Events file didn't match\n"
                         f"self: {self.events}\n"
                         f"other: {other.events}")
            return False

        return True

    def __getstate__(self):
        # Use a shallow copy of __dict__ to avoid modifying the actual
        # Incremental object during serialization.
        state = self.__dict__.copy()

        # Serialize NIfTI image using class-specific method, and store its
        # specific NIfTI1/NIfTI2 class object for deserialization
        state['image'] = self.image.to_bytes()
        state['niftiImageClass'] = self.image.__class__

        return state

    def __setstate__(self, state):
        self.__dict__ = state

        if self.version == 1:
            # Read bytes into NIfTI object
            self.image = self.niftiImageClass.from_bytes(self.image)
            del self.niftiImageClass

    def _preprocessMetadata(self, imageMetadata: dict) -> dict:
        """
        Pre-process metadata to extract any additonal metadata that might be
        embedded in the provided metadata, like ProtocolName, and ensure that
        certain metadata values (e.g., RepetitionTime) are within
        BIDS-specified ranges.

        Args:
            imageMetadata: Metadata dictionary provided to BIDS incremental to
                search for additional, embedded metadata

        Returns:
            Original dictionary with all embedded metadata added explicitly and
                values within BIDS-specified ranges.
        """
        # Process ProtocolName
        protocolName = imageMetadata.get("ProtocolName", None)
        parsedMetadata = metadataFromProtocolName(protocolName)
        logger.debug(f"From ProtocolName '{protocolName}', got: "
                     f"{parsedMetadata}")

        # TODO(spolcyn): Attempt to extract the repetition time directly from
        # the NIfTI header when possible

        # TODO(spolcyn): Correctly handle timing such that any one one of these
        # 5 timing methods work from a user perspective (currently,
        # RepetitionTime is required)
        """
         Timing may be represented one of 5 ways, with 5 relevant variables:
         Variables:
         RepetitionTime (RT), SliceTiming (ST), AcquisitionDuration (AD),
         DelayTime (DT), and VolumeTiming (VT)
         A) RT AND NOT AD AND NOT VT
         B) NOT RT AND ST AND NOT DT AND VT
         C) NOT RT AND AD AND NOT DT AND VT
         D) RT AND ST AND NOT AD AND NOT VT
         E) RT AND NOT AD AND DT AND NOT VT
         https://bids-specification.readthedocs.io/en/latest/04-modality-specific-files/01-magnetic-resonance-imaging-data.html#required-fields
        """

        parsedMetadata.update(imageMetadata)
        adjustTimeUnits(parsedMetadata)

        return parsedMetadata

    def _exceptIfMissingMetadata(self, imageMetadata: dict) -> None:
        """
        Ensure that all required metadata is present.

        Args:
            imageMetadata: Metadata dictionary to check for missing metadata

        Raises:
            MissingMetadataError: If not all required metadata is present.
        """
        missingImageMetadata = self.findMissingImageMetadata(imageMetadata)
        if missingImageMetadata != []:
            raise MissingMetadataError(f"Image metadata missing required "
                                       f"fields: {missingImageMetadata}")

    def _postprocessMetadata(self, imageMetadata: dict) -> dict:
        """
        Post-process metadata once all required fields are given (e.g., to
        create derived fields like 'TaskName' from 'task').

        Args:
            imageMetadata: Metadata dictionary to post-process.

        Returns:
            Metadata dictionary with derived fields set.
        """
        # Ensure datatype is 'func'
        if imageMetadata['datatype'] != 'func':
            raise NotImplementedError("BIDS Incremental for BIDS datatypes "
                                      "other than 'func' is not yet implemented"
                                      f" (got '{imageMetadata['datatype']}')")

        # TaskName is required BIDS metadata that can be derived from the
        # required field, 'task'
        imageMetadata["TaskName"] = imageMetadata["task"]

        # Some fields must be numbers in the BIDS standard
        numberFields = ["RepetitionTime", "EchoTime"]
        for field in numberFields:
            value = imageMetadata.get(field)
            if value: 
                imageMetadata[field] = float(value)

        return imageMetadata

    @staticmethod
    def createImageMetadataDict(subject: str, task: str, suffix: str,
                                datatype: str, repetitionTime: int):
        """
        Creates an image metadata dictionary for a BIDS-I with all of the
        basic required fields using the correct key names.

        Args:
            subject: Subject ID (e.g., '01')
            task: Task ID (e.g., 'story')
            suffix: Imaging method (e.g., 'bold')
            datatype: Data type (e.g., 'func' or 'anat')
            repetitionTime: TR time, in seconds, used for the imaging run

        Returns:
            Dictionary with the provided information ready for use in a BIDS-I

        """
        return {"subject": subject, "task": task, "suffix": suffix,
                'datatype': datatype, "RepetitionTime": repetitionTime}

    @classmethod
    def findMissingImageMetadata(cls, imageMeta: dict) -> list:
        """
        Creates a list of all required metadata fields that the argument
        dictionary is missing.

        Args:
            imageMeta: Metadata dictionary to check for missing fields

        Returns:
            List of required fields missing in the provided dictionary.

        Examples:
            >>> meta = {'subject': '01', 'task': 'test', 'suffix': 'bold',
                        'datatype': 'func'}
            >>> BidsIncremental.findMissingImageMetadata(meta)
            ['RepetitionTime']
        """
        return [f for f in cls.REQUIRED_IMAGE_METADATA if f not in imageMeta]

    @classmethod
    def isCompleteImageMetadata(cls, imageMeta: dict) -> bool:
        """
        Verifies that all required metadata fields for BIDS-I construction are
        present in the dictionary.

        Args:
            imageMeta: The dictionary with the metadata fields

        Returns:
            True if all required fields are present in the dictionary, False
            otherwise.

        Examples:
            >>> meta = {'subject': '01', 'task': 'test', 'suffix': 'bold',
                        'datatype': 'func'}
            >>> BidsIncremental.isCompleteImageMetadata(meta)
            False
        """
        return len(cls.findMissingImageMetadata(imageMeta)) == 0

    def _exceptIfNotBids(self, entityName: str) -> None:
        """
        Raise an exception if the argument is not a valid BIDS entity
        """
        if self.ENTITIES.get(entityName) is None:
            raise ValueError(f"{entityName} is not a valid BIDS entity name")

    def getMetadataField(self, field: str, strict: bool = False) -> Any:
        """
        Get value for the field in the incremental's metadata, if it exists.

        Args:
            field: Metadata field to retrieve a value for.
            default: Default value to return if field is not present.
            strict: Only allow getting fields that are defined as BIDS entities
                in the standard.


        Returns:
            Entity's value, or None if the entity isn't present in the metadata.

        Raises:
            ValueError: If 'strict' is True and 'field' is not a BIDS entity.
            KeyError: If the field is not present in the Incremental's metadata
                and not default value is provided.

        Examples:
            >>> incremental.getMetadataField('task')
            'faces'
            >>> incremental.getMetadataField('RepetitionTime')
            1.5
            >>> incremental.getMetadataField('RepetitionTime', strict=True)
            ValueError: RepetitionTime is not a valid BIDS entity name
        """
        if strict:
            self._exceptIfNotBids(field)

        try:
            return self._imgMetadata[field]
        except KeyError:
            raise KeyError(f"'{field}' is not in the Incremental's metadata")

    def setMetadataField(self, field: str, value: Any,
                         strict: bool = False) -> None:
        """
        Set metadata field to provided value in Incremental's metadata.

        Args:
            field: Metadata field to set value for.
            value: Value to set for the provided entity.
            strict: Only allow setting fields that are defined as BIDS entities
                in the standard.

        Raises:
            ValueError: If 'strict' is True and 'field' is not a BIDS entity.
        """
        if strict:
            self._exceptIfNotBids(field)
        if field:
            self._imgMetadata[field] = value
        else:
            raise ValueError("Metadata field to set cannot be None")

    def removeMetadataField(self, field: str, strict: bool = False) -> None:
        """
        Remove a piece of metadata from the incremental's metadata.

        Args:
            field: BIDS entity name to retrieve a value for.
            strict: Only allow removing fields that are defined as BIDS entities
                in the standard.

        Raises:
            ValueError: If 'strict' is True and 'field' is not a BIDS entity.
            RuntimeError: If the field to be removed is required by the
                Incremental.
        """
        if field in self.REQUIRED_IMAGE_METADATA:
            raise RuntimeError(f"'{field}' is required and cannot be removed")
        if strict:
            self._exceptIfNotBids(field)
        self._imgMetadata.pop(field, None)

    @property
    def imageMetadata(self):
        return self._imgMetadata.copy()

    @property
    def suffix(self) -> str:
        return self._imgMetadata.get("suffix")

    @property
    def datatype(self) -> str:
        """ func or anat """
        return self._imgMetadata.get("datatype")

    @property
    def entities(self) -> dict:
        # Metadata dictionary filtered down to just BIDS entities
        return filterEntities(self._imgMetadata)

    @property
    def imageDimensions(self) -> tuple:
        return self.imageHeader.get_data_shape()

    @property
    def imageHeader(self):
        return self.image.header

    @property
    def imageData(self) -> np.ndarray:
        return getNiftiData(self.image)

    """
    BEGIN BIDS-I ARCHIVE EMULTATION API

    A BIDS-I is meant to emulate a valid BIDS archive. Thus, an API is included
    that enables generating paths and filenames that would corresopnd to this
    BIDS-I's data if it were actually in an on-disk archive.

    """
    def makeBidsFileName(self, extension: BidsFileExtension) -> str:
        """
        Create the a BIDS-compatible file name based on the metadata. General
        format of the filename, per BIDS standard 1.4.1, is as follows (items in
        [square brackets] are considered optional):

        sub-<label>[_ses-<label>]_task-<label>[_acq-<label>] [_ce-<label>]
        [_dir-<label>][_rec-<label>][_run-<index>]
        [_echo-<index>]_<contrast_label >.ext

        Args:
            extension: The extension for the file, e.g., 'nii' for images or
                'json' for metadata

        Return:
            Filename from metadata according to BIDS standard 1.4.1.
        """
        entities = {key: self._imgMetadata[key] for key in self.ENTITIES.keys()
                    if self._imgMetadata.get(key, None) is not None}

        entities["extension"] = extension.value
        if extension == BidsFileExtension.EVENTS:
            entities["suffix"] = "events"
        else:
            entities["suffix"] = self._imgMetadata["suffix"]

        return bids_build_path(entities, BIDS_FILE_PATTERN)

    @property
    def datasetName(self) -> str:
        return self.datasetMetadata["Name"]

    @property
    def imageFileName(self) -> str:
        # TODO(spolcyn): Support writing to a compressed NIfTI file
        return self.makeBidsFileName(BidsFileExtension.IMAGE)

    @property
    def metadataFileName(self) -> str:
        return self.makeBidsFileName(BidsFileExtension.METADATA)

    @property
    def eventsFileName(self) -> str:
        return self.makeBidsFileName(BidsFileExtension.EVENTS)

    @property
    def imageFilePath(self) -> str:
        return os.path.join(self.dataDirPath, self.imageFileName)

    @property
    def metadataFilePath(self) -> str:
        return os.path.join(self.dataDirPath, self.metadataFileName)

    @property
    def eventsFilePath(self) -> str:
        return os.path.join(self.dataDirPath, self.eventsFileName)

    @property
    def dataDirPath(self) -> str:
        """
        Path to where this incremental's data would be in a BIDS archive,
        relative to the archive root.

        Returns:
            Path string relative to root of the imaginary dataset.

        Examples:
            >>> print(bidsi.dataDirPath)
            sub-01/ses-2011/anat
        """
        return bids_build_path(self._imgMetadata, BIDS_DIR_PATH_PATTERN)

    def writeToDisk(self, datasetRoot: str, onlyData=False) -> None:
        """
        Writes the incremental's data to a directory on disk. NOTE: The
        directory is assumed to be empty, and no checks are made for data that
        would be overwritten.

        Args:
            datasetRoot: Path to the root of the BIDS archive to be written to.
            onlyData: Only write out the NIfTI image and sidecar metadata
                (Default False). Useful if writing an incremental out to an
                existing archive and you don't want to overwrite existing README
                or dataset_description.json files.

        Examples:
            >>> from bidsArchive import BidsArchive
            >>> incremental = BidsIncremental(image, metadata)
            >>> root = '/tmp/emptyDirectory'
            >>> incremental.writeToDisk(root)
            >>> archive = BidsArchive(root)
            >>> print(archive)
            Root: /tmp/emptyDirectory | Subjects: 1 | Sessions: 1 | Runs: 1
        """
        # TODO(spolcyn): Support writing to a compressed NIfTI file

        dataDirPath = os.path.join(datasetRoot, self.dataDirPath)
        descriptionPath = os.path.join(datasetRoot, "dataset_description.json")
        readmePath = os.path.join(datasetRoot, "README")

        imagePath = os.path.join(dataDirPath, self.imageFileName)
        metadataPath = os.path.join(dataDirPath, self.metadataFileName)
        eventsPath = os.path.join(dataDirPath, self.eventsFileName)

        os.makedirs(dataDirPath, exist_ok=True)
        nib.save(self.image, imagePath)

        # Write out image metadata
        with open(metadataPath, mode='w') as metadataFile:
            metadataToWrite = {key: self._imgMetadata[key] for key in
                               self._imgMetadata if key not in self.ENTITIES and
                               key not in PYBIDS_PSEUDO_ENTITIES}
            json.dump(metadataToWrite, metadataFile, sort_keys=True, indent=4)

        with open(eventsPath, mode='w') as eventsFile:
            self.events.to_csv(eventsFile, sep='\t')

        if not onlyData:
            # Write out dataset description
            with open(descriptionPath, mode='w') as description:
                json.dump(self.datasetMetadata, description, indent=4)

            # Write out readme
            with open(readmePath, mode='w') as readme:
                readme.write(self.readme)

    """ END BIDS-I ARCHIVE EMULTATION API """
