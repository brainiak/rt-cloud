"""
BidsInterface is a client interface (i.e. for the experiment script running in the cloud) that
provides data access to BIDS data.

To support RPC calls from the client, there will be two instances of dataInterface, one
at the cloud projectServer which is a stub to forward requests (started with dataRemote=True),
and another at the control room computer, run as a service and with dataRemote=False.

When not using RPC, i.e. when the projectServer is run without --dataRemote, there will be only
one instance of dataInterface, as part of the projectServer with dataRemote=False.
"""
import os
import time
from rtCommon.remoteable import RemoteableExtensible
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.bidsCommon import getDicomMetadata
from rtCommon.imageHandling import convertDicomImgToNifti
from rtCommon.dataInterface import DataInterface
from rtCommon.openNeuro import OpenNeuroCache
from rtCommon.errors import RequestError, MissingMetadataError


class BidsInterface(RemoteableExtensible):
    """
    Provides functions for accessing remote or local BIDS data depending on if dataRemote flag
    is set true or false.

    If dataRemote=True, then the RemoteExtensible parent class takes over and forwards all
    requests to a remote server via a callback function registered with the RemoteExtensible
    object. In that case *none* of the methods below will be locally invoked.

    If dataRemote=False, then the methods below will be invoked locally and the RemoteExtensible
    parent class is inoperable (i.e. does nothing).
    """
    def __init__(self, dataRemote=False, allowedDirs=[], scannerClockSkew=0):
        """
        Args:
            dataRemote (bool): Set to true for a passthrough instance that will forward requests.
                               Set to false for the actual instance running remotely
            allowedDirs (list): Only applicable for DicomToBidsStreams. Indicates the
                                directories that Dicom files are allowed to be read from.
            scannerClockSkew (float): number of seconds the scanner's clock is ahead of the
                data server clock
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
        # Store the allowed directories to be used by the DicomToBidsStream class
        self.allowedDirs = allowedDirs
        self.scannerClockSkew = scannerClockSkew
        self.openNeuroCache = OpenNeuroCache(cachePath="/tmp/openneuro")


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
            streamId: An int identifier to be used when calling stream functions, such as getIncremental()
        """
        # TODO - allow multiple simultaneous streams to be instantiated
        streamId = 1
        dicomBidsStream = DicomToBidsStream(self.allowedDirs)
        dicomBidsStream.initStream(dicomDir, dicomFilePattern, dicomMinSize, **entities)
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
            streamId: An int identifier to be used when calling stream functions, such as getIncremental()
        """
        # TODO - allow multiple simultaneous streams to be instantiated
        streamId = 1
        bidsStream = BidsStream(archivePath, **entities)
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
        if 'subject' not in entities or 'run' not in entities:
            raise RequestError("initOpenNeuroStream: Must specify subject and run number")
        archivePath = self.openNeuroCache.downloadData(dsAccessionNumber, **entities)
        # TODO - allow multiple simultaneous streams to be instantiated
        streamId = 1
        bidsStream = BidsStream(archivePath, **entities)
        self.streamMap[streamId] = bidsStream
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

    def closeStream(self, streamId):
        # remove the stream from the map
        self.streamMap.pop(streamId, None)

    def getClockSkew(self, callerClockTime: float, roundTripTime: float) -> float:
        """
        Returns the clock skew between the caller's computer and the scanner clock.
        This function is assumed to be running in the scanner room and have adjustments
        to translate this server's clock to the scanner clock.
        Value returned is in seconds. A positive number means the scanner clock
        is ahead of the caller's clock. The caller should add the skew to their
        localtime to get the time in the scanner's clock.

        Args:
            callerClockTime - current time (secs since epoch) of caller's clock
            roundTripTime - measured RTT in seconds to remote caller
        Returns:
            Clockskew - seconds the scanner's clock is ahead of the caller's clock
        """
        # Adjust the caller's clock forward by 1/2 round trip time
        callerClockAdjToNow = callerClockTime + roundTripTime / 2.0
        now = time.time()
        # calcluate the time this server's clock is ahead of the caller's clock
        skew = now - callerClockAdjToNow
        # add the time skew from this server to the scanner clock
        totalSkew = skew + self.scannerClockSkew
        return totalSkew

    def ping(self) -> float:
        """Returns seconds since the epoch"""
        return time.time()


class DicomToBidsStream():
    """
    A class that watches for DICOM file creation in a specified directory and with
    a specified file pattern. When DICOM files arrive it converts them to BIDS
    incrementals and returns the BIDS incremental. This lets a real-time classification
    script process data directly as BIDS as it arrives from the scanner.
    """

    def __init__(self, allowedDirs=[]):
        self.allowedDirs = allowedDirs

    def initStream(self, dicomDir, dicomFilePattern, dicomMinSize, **entities):
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
        if 'subject' not in entities.keys():
            raise MissingMetadataError("Entities must include 'subject' field")
        if 'task' not in entities.keys():
            raise MissingMetadataError("Entities must include 'task' field")
        if 'suffix' not in entities.keys():
            entities['suffix'] = 'bold'
        if 'datatype' not in entities.keys():
            entities['datatype'] = 'func'
        self.entities = entities
        self.dicomDir = dicomDir
        self.dicomFilePattern = dicomFilePattern
        # TODO - restrict allowed directories, check that dicomDir is in allowed dir
        self.dataInterface = DataInterface(dataRemote=False,
                                           allowedDirs=self.allowedDirs,
                                           allowedFileTypes=['.dcm'])
        self.dicomStreamId = self.dataInterface.initScannerStream(dicomDir,
                                                                  dicomFilePattern,
                                                                  dicomMinSize)
        self.nextVol = 0

    def getNumVolumes(self) -> int:
        """
        Return the number of brain volumes in the run, unknowable by this
        interface ahead of time for a real-time DICOM stream
        """
        raise NotImplementedError('getNumVolumes not implemented for DicomBidsStream')

    def getIncremental(self, volIdx=-1) -> BidsIncremental:
        """
        Get the BIDS incremental for the corresponding DICOM image indicated
        by the volIdx, where volIdx is equivalent to TR id.

        VolIdx acts similar to a file_seek pointer. If a volIdx >= 0 is supplied
        the volume pointer is advanced to that position. If no volIdx or
        a volIdx < 0 is supplied, then the next image volume after the previous
        position is returned and the pointer is incremented.

        Args:
            volIdx: The volume index (or TR) within the run to retrieve.
        Returns:
            BidsIncremental for the matched DICOM for the run/volume
        """
        if volIdx >= 0:
            # reset the next volume to the user specified volume
            self.nextVol = volIdx
        else:
            # use the default next volume
            pass
        # wait for the dicom and create a bidsIncremental
        dcmImg = self.dataInterface.getImageData(self.dicomStreamId, self.nextVol)
        dicomMetadata = getDicomMetadata(dcmImg)
        dicomMetadata.update(self.entities)
        niftiImage = convertDicomImgToNifti(dcmImg)
        incremental = BidsIncremental(niftiImage, dicomMetadata)
        self.nextVol += 1
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
        self.bidsRun = self.bidsArchive.getBidsRun(**entities)
        self.numVolumes = self.bidsRun.numIncrementals()
        self.nextVol = 0

    def getNumVolumes(self) -> int:
        """Return the number of brain volumes in the run"""
        return self.numVolumes

    def getIncremental(self, volIdx=-1) -> BidsIncremental:
        """
        Get a BIDS incremental for the indicated index in the current subject/run
        VolIdx acts similar to a file_seek pointer. If a volIdx >= 0 is supplied
        the volume pointer is advanced to that position. If no volIdx or
        a volIdx < 0 is supplied, then the next image volume after the previous
        position is returned and the pointer is incremented.

        Args:
            volIdx: The volume index (or TR) within the run to retrieve.
        Returns:
            BidsIncremental of that volume index within this subject/run
        """
        if volIdx >= 0:
            # reset the next volume to the user specified volume
            self.nextVol = volIdx
        else:
            # use the default next volume
            pass

        if self.nextVol < self.numVolumes:
            incremental = self.bidsRun.getIncremental(self.nextVol)
            self.nextVol += 1
            return incremental
        else:
            return None
