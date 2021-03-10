"""
BidsInterface is a client interface (i.e. for the experiment script running in the cloud) that
provides data access to BIDs data.

To support RPC calls from the client, there will be two instances of dataInterface, one
at the cloud projectServer which is a stub to forward requests (started with dataRemote=True),
and another at the control room computer, run as a service and with dataRemote=False.

When not using RPC, i.e. when the projectServer is run without --dataRemote, there will be only
one instance of dataInterface, as part of the projectServer with dataRemote=False.
"""
import os
import glob
import nibabel as nib
from rtCommon.remoteable import RemoteableExtensible
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.bidsCommon import getDicomMetadata
from rtCommon.imageHandling import convertDicomImgToNifti
from rtCommon.dataInterface import DataInterface
from rtCommon.errors import ValidationError, RequestError


class BidsInterface(RemoteableExtensible):
    """
    Provides functions for accessing remote or local BIDs data depending on if dateRemote flag
    is set true or false.

    If dataRemote=True, then the RemoteExtensible parent class takes over and forwards all
    requests to a remote server via a callback function registered with the RemoteExtensible
    object. In that case *none* of the methods below will be locally invoked.

    If dataRemote=False, then the methods below will be invoked locally and the RemoteExtensible
    parent class is inoperable (i.e. does nothing).
    """
    def __init__(self, dataRemote=False):
        """
        Args:
            dataRemote (bool): Set to true for a passthrough instance that will forward requests.
                               Set to false for the actual instance running remotely
        """
        super().__init__(isRemote=dataRemote)
        if dataRemote is True:
            return
        # local version initialization here
        # TODO - make multithread streams possible
        #      - get next streamId in thread safe way
        #      - cleanup stale streams
        nextStreamId = 1
        self.streamMap = {}

    def initDicomBidsStream(self, dicomDir, dicomFilePattern, dicomMinSize, **entities) -> int:
        """
        Intialize a data stream that watches a directory for DICOM files to be written that
        match the given file pattern. When a DICOM is written it will be converted to a BIDS
        incremental and returned.
        Args:
            dicomDir: the directory where the images are or will be written from the MRI scanner.
            dicomFilePattern: a pattern of the image file names that has a TR tag which will be used
                to index the images, for example 'scan01_{TR:03d}.dcm'. In this example a call to
                getImageData(imgIndex=6) would look for dicom file 'scan01_006.dcm'.
            minFileSize: Minimum size of the file to return (continue waiting if below this size)
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that will be
                required to fill in the BIDS metadata in the BIDS Incremental
        Returns:
            streamId: An identifier used when calling stream functions, such as getIncremental()
        """
        streamId = 1
        dicomBidsStream = DicomToBidsStream(dicomDir, dicomFilePattern, dicomMinSize, **entities)
        self.streamMap[streamId] = dicomBidsStream
        return streamId

    def initBidsStream(self, archivePath, **entities) -> int:
        """
        Initialize a data stream from an existing BIDS archive.
        Args:
            archivePath: Full path to the BIDS archive
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that
                define the particular subject/run of the data to stream
        Returns:
            streamId: An identifier used when calling stream functions, such as getIncremental()
        """
        streamId = 1
        bidsStream = BidsStream(datasetPath, **entities)
        self.streamMap[streamId] = bidsStream
        return streamId

    def initOpenNeuroStream(self, dsAccessionNumber, **entities) -> int:
        """
        Initialize a data stream that replays an OpenNeuro dataset.
        Args:
            dsAccessionNumber: OpenNeuro accession number of the dataset to replay
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that
                define the particular subject/run of the data to stream
        Returns:
            streamId: An identifier used when calling stream functions, such as getIncremental()
        """
        streamId = 1
        openNeuroStream = OpenNeuroStream(dsAccessionNumber, **entities)
        self.streamMap[streamId] = openNeuroStream
        return streamId

    def getIncremental(self, streamId, volIdx=-1) -> BidsIncremental:
        """
        Get a BIDS Incremental from a stream
        Args:
            streamId: The stream handle returned by the initXXStream call
            volIdx: The brain volume index of the image to return. If -1 is
                entered it will return the next volume
        Returns:
            A BidsIncremental containing the image volume
        """
        stream = self.streamMap[streamId]
        bidsIncremental = stream.getIncremental(volIdx)
        return bidsIncremental

    def getNumVolumes(self, streamId) -> int:
        """
        Return the number of image volumes contained in the stream. This is only
        defined for Bids/OpenNeuro streams (not for DicomBidsStreams)
        Args:
            streamId: The stream handle returned by the initXXStream call
        Returns:
            An int of the number of volumes
        """
        stream = self.streamMap[streamId]
        return stream.getNumVolumes()


class DicomToBidsStream():
    """
    A class that watches for DICOM file creation in a specified directory and with
    a specified file pattern. When DICOM files arrive it converts them to BIDS
    incrementals and returns the BIDS incremental. This lets a real-time classification
    script process data directly as BIDS as it arrives from the scanner.
    """
    def __init__(self, dicomDir, dicomFilePattern, dicomMinSize, **entities):
        """
        Intialize a new DicomToBids stream, watches for Dicoms and streams as BIDS
        Args:
            dicomDir: The directory where the scanner will write new DICOM files
            dicomFilePattern: A regex style pattern of the DICOM filenames to
                watch for. They should include a {TR} tag with optional formatting.
                For example filenames like '001_000013_000005.dcm' would have a
                pattern '001_000013_{TR:06d}.dcm' where the volume number (TR)
                will be filled in by a 6 digit leading zeros value.
            dicomMinSize: Minimum size of the file to return (will continue waiting
                if below this size)
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that
                define the particular subject/run of the data to stream
        """
        # TODO - make sure dicomPattern has {TR} in it
        # TODO - restrict allowed directories, check that dicomDir is in allowed dir
        if 'suffix' not in entities.keys():
            entities['suffix'] = 'bold'
        if 'datatype' not in entities.keys():
            entities['datatype'] = 'func'
        self.entities = entities
        self.dicomDir = dicomDir
        self.dicomFilePattern = dicomFilePattern
        self.dataInterface = DataInterface(dataRemote=False, allowedDirs=['*'], allowedFileTypes=['.dcm'])
        self.dicomStreamId = self.dataInterface.initScannerStream(dicomDir, dicomFilePattern, dicomMinSize)
        self.initialized = True

    def getNumVolumes(self) -> int:
        """
        Return the number of brain volumes in the run, unknowable by this
        interface ahead of time for a real-time DICOM stream
        """
        raise NotImplementedError('getNumVolumes not implemented for DicomBidsStream')

    def getIncremental(self, volIdx) -> BidsIncremental:
        """
        Get the BIDS incremental for the corresponding DICOM image indicated
            by the volIdx, where volIdx is equivalent to TR id.
        Args:
            volIdx: The volume index (or TR) within the run to retrieve.
        Returns:
            BidsIncremental for the matched DICOM for the run/volume
        """
        # wait for the dicom and create a bidsIncremental
        dcmImg = self.dataInterface.getImageData(self.dicomStreamId, volIdx)
        dicomMetadata = getDicomMetadata(dcmImg)
        dicomMetadata.update(self.entities)
        niftiImage = convertDicomImgToNifti(dcmImg)
        incremental = BidsIncremental(niftiImage, dicomMetadata)
        return incremental


class BidsStream:
    """
    A class that opens a BIDS archive and prepares to stream the data as
    BIDS incrementals.
    """
    def __init__(self, archivePath, **entities):
        """
        Args:
            archivePath: Absolute path of the BIDS archive.
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that
                define the particular subject/run of the data to stream
        """
        self.bidsArchive = BidsArchive(archivePath)
        # TODO - when we have BidsRun
        # self.bidsRun = self.bidsArchive.getBidsRun(**entities)
        images = self.bidsArchive.getImages(**entities)
        if len(images) == 0:
            raise ValidationError('No matching images found')
        if len(images) > 1:
            raise ValidationError('More than one match, please give more specific subject/session/task/run')
        self.bidsImage = images[0]
        self.niftiImage = self.bidsImage.get_image()
        self.filename = self.niftiImage.get_filename()
        self.imgVolumes = nib.four_to_three(self.niftiImage)
        self.metadata = self.bidsArchive.getSidecarMetadata(self.filename, includeEntities=True)
        self.metadata.pop('extension')
        self.numVolumes = len(self.imgVolumes)
        self.nextVol = 0

    def getNumVolumes(self) -> int:
        """Return the number of brain volumes in the run"""
        # TODO - when we have BidsRun
        # return self.bidsRun.getNumVolumes()
        return self.numVolumes

    def getIncremental(self, volIdx) -> BidsIncremental:
        """
        Get a BIDS incremental for the indicated index in the current subject/run
        Args:
            volIdx: The volume index (or TR) within the run to retrieve.
        Returns:
            BidsIncremental of that volume index within this subject/run
        """
        # TODO - when we have BidsRun
        # return self.bidsRun.getIncremental(volIdx)
        if volIdx < 0:
            volIdx = self.nextVol
        if volIdx < self.numVolumes:
            self.nextVol += 1
            return BidsIncremental(self.imgVolumes[volIdx], self.metadata)
        else:
            return None


class OpenNeuroStream(BidsStream):
    """
    A BidsStream from an OpenNeuro dataset. The OpenNeuro dataset will be automatically
    downloaded at the remote as needed to satisfy the stream of data.
    """
    def __init__(self, dsAccessionNumber, **entities):
        """
        Args:
            dsAccessionNumber: The OpenNeruo specific accession number for the dataset
                to stream.
            entities: BIDS entities (subject, session, task, run, suffix, datatype) that
                define the particular subject/run of the data to stream
        """
        subject = entities.get('subject')
        run = entities.get('run')
        if subject is None or run is None:
            raise RequestError("OpenNeuroStream: Must specify subject and run number")
        # TODO - Use OpenNeuroService when it is available, to download
        #   and access the dataset and get dataset entities
        # OpenNeuroService to provide path to dataset
        datasetPath = tmpDownloadOpenNeuro(dsAccessionNumber, subject, run)
        super().__init__(datasetPath, **entities)


def tmpDownloadOpenNeuro(dsAccessNumber, subject, run) -> str:
    """
    Temporary function used until we integrate in the OpenNeuro service. Downloads
    a portion of an OpenNeuro dataset corresponding to the subject/run.
    Args:
        dsAccessionNumber: The OpenNeruo specific accession number for the dataset
            to stream.
        subject: the specific subject name within the OpenNeuro dataset to download
        run: the specific run within the subject's data to download.
    Returns:
        Absolute path to where the dataset has been downloaded.

    """
    tmpDir = '/tmp/openneuro'
    datasetDir = os.path.join(tmpDir, dsAccessNumber)
    # check if already downloaded
    includePattern = f'sub-{subject}/func/*run-{run:02d}*'
    files = glob.glob(os.path.join(datasetDir, includePattern))
    if len(files) == 0:
        os.makedirs(datasetDir, exist_ok = True)
        awsCmd = f'aws s3 sync --no-sign-request s3://openneuro.org/{dsAccessNumber} ' \
                f'{datasetDir} --exclude "*/*" --include "{includePattern}"'
        print(f'run {awsCmd}')
        os.system(awsCmd)
    return datasetDir
