"""-----------------------------------------------------------------------------

bidsArchive.py

Implements interacting with an on-disk BIDS Archive.

-----------------------------------------------------------------------------"""
from typing import List, Tuple, Union
import functools
import json
import logging
import os
import re

from bids.config import set_option as bc_set_option
from bids.exceptions import (
    NoMatchError,
)
from bids.layout import (
    BIDSDataFile,
    BIDSFile,
    BIDSImageFile,
    BIDSLayout,
)
from bids.layout.writing import write_to_file as bids_write_to_file
import nibabel as nib
import numpy as np

from rtCommon.bidsCommon import (
    PYBIDS_PSEUDO_ENTITIES,
    correct3DHeaderTo4D,
    getNiftiData,
)
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.errors import (
    DimensionError,
    MetadataMismatchError,
    MissingMetadataError,
    QueryError,
    StateError,
)

# Silence future warning
bc_set_option('extension_initial_dot', True)

logger = logging.getLogger(__name__)


def failIfEmpty(func):
    @functools.wraps(func)
    def emptyFailWrapFunction(*args, **kwargs):
        if args[0].data is None:
            raise StateError("Dataset empty")
        else:
            return func(*args, **kwargs)

    return emptyFailWrapFunction


class BidsArchive:
    def __init__(self, rootPath: str):
        """
        BidsArchive represents a BIDS-formatted dataset on disk. It offers an
        API for querying that dataset, and also adds special methods to add
        BidsIncrementals to the dataset and extract portions of the dataset as
        BidsIncrementals.

        Args:
            rootPath: Path to the archive on disk (either absolute or relative
            to current working directory).

        Examples:
            >>> archive = BidsArchive('dataset')
            >>> str(archive)
            Root: ...t-cloud/docs/tutorials/dataset | Subjects: 1 |
            Sessions: 0 | Runs: 1
            >>> archive = BidsArchive('/tmp/downloads/dataset')
            >>> str(archive)
            Root: /tmp/downloads/dataset | Subjects: 20 |
            Sessions: 3 | Runs: 2
        """
        self.rootPath = os.path.abspath(rootPath)
        # Formatting initialization logic this way enables the creation of an
        # empty BIDS archive that an incremntal can then be appended to
        try:
            self.data = BIDSLayout(rootPath)
        except Exception as e:
            logger.debug("Failed to open dataset at %s (%s)",
                         self.rootPath, str(e))
            self.data: BIDSLayout = None

    def __str__(self):
        out = str(self.data)
        if 'BIDS Layout' in out:
            out = out.replace('BIDS Layout', 'Root')

        return out

    # Enable accessing underlying BIDSLayout properties without inheritance
    def __getattr__(self, attr):
        originalAttr = attr

        # If the attr is in the format getXyz, convert to get_xyz for forwarding
        # to the BIDSLayout object However, Some requests shouldn't be
        # auto-forwarded, even if they're in the right form.
        # List:
        # getMetadata: Too similar to getSidecarMetadata, users may accidentally
        #     call getMetadata which forwards to get_metadata and has different
        #     behavior than getSidecarMetadata
        excludedAttributes = ['getMetadata']

        if attr not in excludedAttributes:
            pattern = re.compile("get[A-Z][a-z]+")
            if pattern.match(attr) is not None:
                attr = attr.lower()
                attr = attr[0:3] + '_' + attr[3:]

        if not self.isEmpty():
            try:
                return getattr(self.data, attr)
            except AttributeError:
                raise AttributeError("{} object has no attribute {}".format(
                    self.__class__.__name__, originalAttr))

    """ Utility functions """
    @staticmethod
    def _stripLeadingSlash(path: str) -> str:
        """
        Strips a leading / from the path, if it exists. This prevents paths
        defined relative to dataset root (/sub-01/ses-01) from being interpreted
        as being relative to the root of the filesystem.

        Args:
            path: Path to strip leading slash from.

        Examples:
            >>> path = '/sub-01/ses-01/func/sub-01_task-test_bold.nii.gz'
            >>> BidsArchive._stripLeadingSlash(path)
            'sub-01/ses-01/func/sub-01_task-test_bold.nii.gz'
            >>> path = 'sub-01/ses-01/func/sub-01_task-test_bold.nii.gz'
            'sub-01/ses-01/func/sub-01_task-test_bold.nii.gz'
        """
        if len(path) >= 1 and path[0] == "/":
            return path[1:]
        else:
            return path

    def absPathFromRelPath(self, relPath: str) -> str:
        """
        Makes an absolute path from the relative path within the dataset.
        """
        return os.path.join(self.rootPath, self._stripLeadingSlash(relPath))

    def tryGetFile(self, path: str) -> BIDSFile:
        """
        Tries to get a file from the archive using different interpretations of
        the target path. Interpretations considered are:
        1) Path with leading slash, relative to filesystem root
        2) Path with leading slash, relative to archive root
        3) Path with no leading slash, assume relative to archive root

        Args:
            path: Path to the file to attempt to get.

        Returns:
            BIDSFile (or subclass) if a matching file was found, None otherwise.

        Examples:
            >>> archive = BidsArchive('/path/to/archive')
            >>> filename = 'sub-01_task-test_bold.nii.gz'
            >>> archive.tryGetFile('/tmp/archive/sub-01/func/' + filename)
            <BIDSImageFile filename=/tmp/archive/sub-01/func/sub-01_task-test\
            _bold.nii.gz
            >>> archive.tryGetFile('/' + filename)
            <BIDSImageFile filename=/tmp/archive/sub-01/func/sub-01_task-test\
            _bold.nii.gz
            >>> archive.tryGetFile(filename)
            <BIDSImageFile filename=/tmp/archive/sub-01/func/sub-01_task-test\
            _bold.nii.gz
        """
        # 1) Path with leading slash, relative to filesystem root
        # 3) Path with no leading slash, assume relative to archive root
        archiveFile = self.data.get_file(path)
        if archiveFile is not None:
            return archiveFile

        # 2) Path with leading slash, relative to archive root
        strippedRootPath = self._stripLeadingSlash(path)
        archiveFile = self.get_file(strippedRootPath)
        if archiveFile is not None:
            return archiveFile

        return None

    @failIfEmpty
    def dirExistsInArchive(self, relPath: str) -> bool:
        return os.path.isdir(self.absPathFromRelPath(relPath))

    @failIfEmpty
    def getImages(self, matchExact: bool = False,
                  **entities) -> List[BIDSImageFile]:
        """
        Return all images that have the provided entities. If no entities are
        provided, then all images are returned.

        Args:
            matchExact: Only return images that have exactly the provided
                entities, no more and no less.
            **entities: Entities that returned images must have.

        Returns:
            A list of images matching the provided entities (empty if there are
            no matches, and containing at most a single image if an exact match
            is requested).

        Examples:
            >>> archive = BidsArchive('/path/to/archive')

            Using a dictionary to provide target entities.

            >>> entityDict = {'subject': '01', 'datatype': 'func'}
            >>> images = archive.getImages(**entityDict)

            Using keyword arguments to provide target entities.

            >>> images = archive.getImages(subject='01', datatype='func')

            Accessing properties of the image.

            >>> image = images[0]
            >>> print(image.get_image()
            (64, 64, 27, 3)
            >>> print(image.path)
            /tmp/archive/func/sub-01_task-test_bold.nii
            >>> print(image.filename)
            sub-01_task-test_bold.nii

            An exact match must have exactly the same entities; since images
            must also have the task entity in their filename, the above
            entityDict will yield no exact matches in the archive.

            >>> images = archive.getImages(entityDict, matchExact=True)
            ERROR "No images were an exact match for: {'subject': '01',
            'datatype': 'func'}"
            >>> print(len(images))
            0
        """
        # Validate image extension specified
        extension = entities.pop('extension', None)
        if extension is not None:
            if extension != '.nii' and extension != '.nii.gz':
                raise ValueError('Extension for images must be either .nii or '
                                 '.nii.gz')

        results = self.data.get(**entities)
        results = [r for r in results if type(r) is BIDSImageFile]

        if len(results) == 0:
            logger.debug(f"Found no images with all entities: {entities}")
            return []
        elif matchExact:
            for result in results:
                # Only BIDSImageFiles are checked, so extension is irrelevant
                result_entities = result.get_entities()
                result_entities.pop('extension', None)

                if result_entities == entities:
                    return [result]

            logger.debug(f"Found no images exactly matching: {entities}")
            return []
        else:
            return results

    def _updateLayout(self):
        """
        Updates the layout of the dataset so that any new metadata or image
        files are added to the index.
        """
        # Updating layout is currently quite expensive. However, the underlying
        # PyBids implementation uses a SQL database to store the index, and it
        # has no public methods to cleanly and incrementally update the DB.
        self.data = BIDSLayout(self.rootPath)

    def _addImage(self, img: nib.Nifti1Image, path: str,
                  updateLayout: bool = True) -> None:
        """
        Replace the image in the dataset at the provided path, creating the path
        if it does not exist.

        Args:
            img: The image to add to the archive
            path: Relative path in archive at which to add image
            updateLayout: Update the underlying layout object upon conclusion of
                the image addition.
        """
        bids_write_to_file(path, img.to_bytes(), content_mode='binary',
                           root=self.rootPath, conflicts='overwrite')

        if updateLayout:
            self._updateLayout()

    def _addMetadata(self, metadata: dict, path: str,
                     updateLayout: bool = True) -> None:
        """
        Replace the sidecar metadata in the dataset at the provided path,
        creating the path if it does not exist.

        Args:
            metadata: Metadata key/value pairs to add.
            path: Relative path in archive at which to add image
            updateLayout: Update the underlying layout object upon conclusion of
                the metadata addition.
        """
        metadataJSONString = json.dumps(metadata, ensure_ascii=False, indent=4)
        bids_write_to_file(path, contents=metadataJSONString,
                           content_mode='text', root=self.rootPath,
                           conflicts='overwrite')

        if updateLayout:
            self._updateLayout()

    def isEmpty(self) -> bool:
        return (self.data is None)

    @failIfEmpty
    def getSidecarMetadata(self, image: Union[str, BIDSImageFile],
                           includeEntities: bool = True) -> dict:
        """
        Get metadata for the file at the provided path in the dataset. Sidecar
        metadata is always returned, and BIDS entities present in the filename
        are returned by default (this can be disabled).

        Args:
            image: Path or BIDSImageFile pointing to the image file to get
                metadata for.
            includeEntities: False to return only the metadata in the image's
                sidecar JSON files.  True to additionally include the entities
                in the filename (e.g., 'subject', 'task', and 'session').
                Defaults to True.

        Raises:
            TypeError: If image is not a str or BIDSImageFile.

        Returns:
            Dictionary with sidecar metadata for the file and any metadata that
                can be extracted from the filename (e.g., subject, session).

        Examples:
            >>> archive = BidsArchive('/path/to/archive')
            >>> path = archive.getImages()[0].path
            >>> archive.getSidecarMetadata(path)
            {'AcquisitionMatrixPE': 320, 'AcquisitionNumber': 1, ... }
        """
        if isinstance(image, BIDSImageFile):
            target = image
        elif type(image) is str:
            target = self.tryGetFile(image)
            if target is None:
                raise NoMatchError("File doesn't exist, can't get metadata")
        else:
            raise TypeError("Expected image as str or BIDSImageFile "
                            f"(got {type(image)})")

        # Counter-intuitively, in PyBids, 'None' returns all available entities,
        # both those from the filename and those from the sidecar metadata. True
        # returns only the metadata in the sidecar file, and False returns only
        # entities in the filename.
        metadataParameter = None if includeEntities else True

        return target.get_entities(metadata=metadataParameter)

    @failIfEmpty
    def getEvents(self, matchExact: bool = False,
                  **entities) -> List[BIDSDataFile]:
        """
        Gets data from scanner run event files in the archive. Event files to
        retrieve can be filtered by entities present in the files' names.

        Args:
            matchExact: Whether to only return events files that have exactly
                the same entities as provided (no more, no less)
            entities: Keyword arguments for entities to filter by. Provide in
                the format entity='value'.

        Returns:
            A list of BIDSDataFile objects encapsulating the events files
            matching the provided entities (empty if there are no matches, and
            containing at most a single object if an exact match is requested).

        Raises:
            ValueError: If the 'extension' entity is provided and not valid for
                an events file (i.e., not '.tsv' or '.tsv.gz')

        Examples:
            >>> archive = BidsArchive('.')
            >>> archive.getEvents()
            [<BIDSDataFile filename='/tmp/dataset/sub-01/func/\
            sub-01_task-test_events.tsv'>, <BIDSDataFile
            filename='/tmp/dataset/sub-02/func/sub-02_task-test_events.tsv'>]
            >>> sub1Events = archive.getEvents(subject='01')
            [<BIDSDataFile filename='/tmp/dataset/sub-01/func/\
            sub-01_task-test_events.tsv'>]
            >>> eventsDataFrame = sub1Events[0].get_df()
            >>> print(eventsDataFrame[:][:1])
                onset   duration    trial_type
            0   0       30          rest
        """
        # Validate image extension specified
        validExtensions = ['.tsv', '.tsv.gz']
        extension = entities.get('extension', None)
        if extension is not None and extension not in validExtensions:
            raise ValueError(f'Extension must be one of {validExtensions}')

        entities['suffix'] = 'events'

        results = self.data.get(**entities)

        if len(results) == 0:
            logger.debug(f"No event files have all provided entities: "
                         f"{entities}")
            return []
        elif matchExact:
            for result in results:
                if result.get_entities() == entities:
                    return [result]

            logger.debug(f"No event files were an exact match for: {entities}")
            return []
        else:
            return results

    @staticmethod
    def _imagesAppendCompatible(img1: nib.Nifti1Image,
                                img2: nib.Nifti1Image) -> Tuple[bool, str]:
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
            True if the headers match along the required dimensions, false
            otherwise.

        """
        fieldsToMatch = ["intent_p1", "intent_p2", "intent_p3", "intent_code",
                         "dim_info", "datatype", "bitpix",
                         "slice_duration", "toffset", "scl_slope", "scl_inter",
                         "qform_code", "quatern_b", "quatern_c", "quatern_d",
                         "qoffset_x", "qoffset_y", "qoffset_z",
                         "sform_code", "srow_x", "srow_y", "srow_z"]

        header1 = img1.header
        header2 = img2.header

        for field in fieldsToMatch:
            v1 = header1.get(field)
            v2 = header2.get(field)

            # Use slightly more complicated check to properly match nan values
            if not (np.allclose(v1, v2, atol=0.0, equal_nan=True)):
                errorMsg = (f"NIfTI headers don't match on field: {field} "
                            f"(v1: {v1}, v2: {v2})")
                return (False, errorMsg)

        # Two NIfTI headers are append-compatible in 2 cases:
        # 1) Pixel dimensions are exactly equal, and dimensions are equal except
        # for in the final dimension
        # 2) One image has one fewer dimension than the other, and all shared
        # dimensions and pixel dimensions are exactly equal
        dimensionMatch = True

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

        # Case 1
        if nDimensions1 == nDimensions2:
            pixdimEqual = np.array_equal(pixdim1, pixdim2)
            allButFinalEqual = np.array_equal(dimensions1[:nDimensions1],
                                              dimensions2[:nDimensions2])

            if not (pixdimEqual and allButFinalEqual):
                dimensionMatch = False
        # Case 2
        else:
            dimensionMatch = False

            dimensionsDifferBy1 = abs(nDimensions1 - nDimensions2) == 1
            if dimensionsDifferBy1:

                nSharedDimensions = min(nDimensions1, nDimensions2)
                # Arrays are 1-indexed as # dimensions is stored in first slot
                sharedDimensionsMatch = \
                    np.array_equal(dimensions1[1:nSharedDimensions + 1],
                                   dimensions2[1:nSharedDimensions + 1])
                if sharedDimensionsMatch:

                    # Arrays are 1-indexed as value used in one method of
                    # voxel-to-world coordination translation is stored in the
                    # first slot (value should be equal across images)
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

    @staticmethod
    def _metadataAppendCompatible(meta1: dict, meta2: dict) -> Tuple[bool, str]:
        """
        Verifies two metadata dictionaries match in a set of required fields. If
        a field is present in only one or neither of the two dictionaries, this
        is considered a match.

        This is primarily intended as a safety check, and does not conclusively
        determine that two images are valid to append to together or are part of
        the same series.

        Args:
            meta1: First metadata dictionary
            meta2: Second metadata dictionary

        Returns:
            True if all keys that are present in both dictionaries have
            equivalent values, False otherwise.

        """
        matchFields = ["Modality", "MagneticFieldStrength", "ImagingFrequency",
                       "Manufacturer", "ManufacturersModelName",
                       "InstitutionName", "InstitutionAddress",
                       "DeviceSerialNumber", "StationName", "BodyPartExamined",
                       "PatientPosition", "EchoTime",
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

    def appendIncremental(self,
                          incremental: BidsIncremental,
                          makePath: bool = True,
                          validateAppend: bool = True) -> bool:
        """
        Appends a BIDS Incremental's image data and metadata to the archive,
        creating new directories if necessary (this behavior can be overridden).

        Args:
            incremental: BIDS Incremental to append
            makePath: Create new directory path for BIDS-I data if needed.
                (default: True).
            validateAppend: Compares image metadata and NIfTI headers to check
                that the images being appended are part of the same sequence and
                don't conflict with each other (default: True).

        Raises:
            RuntimeError: If the image to append to in the archive is not either
                3D or 4D.
            StateError: If the image path within the BIDS-I would result in
                directory creation and makePath is set to False.
            ValidationError: If the data to append is incompatible with existing
                data in the archive.

        Returns:
            True if the append succeeded, False otherwise.

        Examples:
            Assume we have a NIfTI image 'image' and a metadata dictionary
            'metdata' with all required metadata for a BIDS Incremental.

            >>> archive = BidsArchive('.')
            >>> incremental = BidsIncremental(image, metadata)
            >>> archive.appendIncremental(incremental)

            If we don't want to create any new files/directories in the archive,
            makePath can be set to false.

            >>> archive = BidsArchive('/tmp/emptyDirectory')
            >>> archive.appendIncremental(incremental, makePath=False)
            False
        """
        # 1) Create target paths for image in archive
        dataDirPath = incremental.dataDirPath
        imgPath = incremental.imageFilePath
        metadataPath = incremental.metadataFilePath

        # 2) Verify we have a valid way to append the image to the archive.
        # 4 cases:
        # 2.0) Archive is empty and must be created
        # 2.1) Image already exists within archive, append this NIfTI to it
        # 2.2) Image doesn't exist in archive, but rest of the path is valid for
        # the archive; create new Nifti file within the archive
        # 2.3) No image append possible and no creation possible; fail append

        # 2.0) Archive is empty and must be created
        if self.isEmpty():
            if makePath:
                incremental.writeToDisk(self.rootPath)
                self._updateLayout()
                return True
            else:
                # If can't create new files in an empty archive, no valid append
                return False

        # 2.1) Image already exists within archive, append this NIfTI to it
        imageFile = self.tryGetFile(imgPath)
        if imageFile is not None:
            logger.debug("Image exists in archive, appending")
            archiveImg = imageFile.get_image()

            # Validate header match
            if validateAppend:
                compatible, errorMsg = self._imagesAppendCompatible(
                    incremental.image,
                    archiveImg)
                if not compatible:
                    raise MetadataMismatchError(
                        "NIfTI headers not append compatible: " + errorMsg)

                compatible, errorMsg = self._metadataAppendCompatible(
                    incremental.imageMetadata,
                    self.getSidecarMetadata(imageFile))
                if not compatible:
                    raise MetadataMismatchError(
                        "Image metadata not append compatible: " + errorMsg)

            # Ensure archive image is 4D, expanding if not
            archiveData = getNiftiData(archiveImg)
            nDimensions = len(archiveData.shape)
            if nDimensions < 3 or nDimensions > 4:
                # RT-Cloud assumes 3D or 4D NIfTI images, other sizes have
                # unknown interpretations
                raise DimensionError("Expected image to have 3 or 4 dimensions "
                                     f"(got {nDimensions})")

            if nDimensions == 3:
                archiveData = np.expand_dims(archiveData, 3)
                correct3DHeaderTo4D(archiveImg, incremental.getMetadataField(
                    "RepetitionTime"))

            # Create the new, combined image to replace the old one
            # TODO(spolcyn): Replace this with Nibabel's concat_images function
            # when the dtype issue with save/load cycle is fixed
            # https://github.com/nipy/nibabel/issues/986
            newArchiveData = np.concatenate(
                (archiveData, getNiftiData(incremental.image)), axis=3)
            newImg = nib.Nifti1Image(newArchiveData,
                                     affine=archiveImg.affine,
                                     header=archiveImg.header)
            newImg.update_header()
            self._addImage(newImg, imgPath)
            return True

        # 2.2) Image doesn't exist in archive, but rest of the path is valid for
        # the archive; create new Nifti file within the archive
        if self.dirExistsInArchive(dataDirPath) or makePath:
            logger.debug("Image doesn't exist in archive, creating")
            self._addImage(incremental.image, imgPath, updateLayout=False)
            self._addMetadata(incremental.imageMetadata, metadataPath,
                              updateLayout=False)
            self._updateLayout()
            return True

        # 2.3) No image append possible and no creation possible; fail append
        return False

    @failIfEmpty
    def getIncremental(self, imageIndex: int = 0, **entities) \
            -> BidsIncremental:
        """
        Creates a BIDS Incremental from the specified part of the archive.

        Args:
            imageIndex: Index of 3-D image to select in a 4-D image volume.
            entities: Keyword arguments for entities to filter by. Provide in
                the format entity='value'.

        Returns:
            BIDS-Incremental file with the specified image of the archive and
            its associated metadata.

        Raises:
            IndexError: If the provided imageIndex goes beyond the bounds of the
                volume specified in the archive.
            MissingMetadataError: If the archive lacks the required metadata to
                make a BIDS Incremental out of an image in the archive.
            NoMatchError: When no images that match the provided entities are
                found in the archive
            RuntimeError:
                1) When too many images that match the provided entities
                are found in the archive.
                2) If the image matching the provided entities has fewer
                than 3 dimensions or greater than 4.

        Examples:
            >>> archive = BidsArchive('.')
            >>> inc = archive.getIncremental(subject='01', task='test')
            >>> entityFilterDict = {'subject': '01', 'task': 'test'}
            >>> inc2 = archive.getIncremental(**entityFilterDict)
            >>> inc == inc2
            True

            By default, getIncremental has an imageIndex of 0. Changing that
            parameter will return a different 3-D image from the volume, using
            the same search metadata.

            >>> inc.imageDimensions
            (64, 64, 27, 1)
            >>> inc3 = archive.getIncremental(imageIndex=1, **entityFilterDict)
            >>> inc2 != inc3
            True
        """
        if imageIndex < 0:
            raise IndexError(f"Image index must be >= 0 (got {imageIndex})")

        candidates = self.getImages(**entities)

        # Throw error if not exactly one match
        if len(candidates) == 0:
            raise NoMatchError("Unable to find any data in archive that matches"
                               f" all provided entities: {entities}")
        elif len(candidates) > 1:
            raise QueryError("Provided entities matched more than one image "
                             "file; try specifying more to narrow to one match "
                             f"(expected 1, got {len(candidates)})")

        # Create BIDS-I
        candidate = candidates[0]
        image = candidate.get_image()

        # Process error conditions and extract image from volume if necessary
        nDimensions = len(image.dataobj.shape)
        if nDimensions == 3:
            if imageIndex != 0:
                raise IndexError(f"Matching image was a 3-D NIfTI; {imageIndex}"
                                 f" too high for a 3-D NIfTI (must be 0)")
        elif nDimensions == 4:
            numImages = image.dataobj.shape[3]

            if imageIndex < numImages:
                # Directly slice Nibabel dataobj for increased memory efficiency
                image = image.__class__(image.dataobj[..., imageIndex],
                                        affine=image.affine,
                                        header=image.header)
                image.update_header()
            else:
                raise IndexError(f"Image index {imageIndex} too large for NIfTI"
                                 f" volume of length {numImages}")
        else:
            raise DimensionError("Expected image to have 3 or 4 dimensions "
                                 f"(got {nDimensions})")
        metadata = self.getSidecarMetadata(candidate)

        # BIDS-I should only be given official entities used in a BIDS Archive
        for pseudoEntity in PYBIDS_PSEUDO_ENTITIES:
            metadata.pop(pseudoEntity)

        try:
            return BidsIncremental(image, metadata)
        except MissingMetadataError as e:
            raise MissingMetadataError("Archive lacks required metadata for "
                                       "BIDS Incremental creation: " + str(e))
