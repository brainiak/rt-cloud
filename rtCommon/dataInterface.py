"""
DataInterface is a client interface (i.e. for the experiment script running in the cloud) that
provides data access, such as reading and writing files.

To support RPC calls from the client, there will be two instances of dataInterface, one
at the cloud projectServer which is a stub to forward requests (started with dataRemote=True),
and another at the control room computer, run as a service and with dataRemote=False.

When not using RPC, i.e. when the projectServer is run without --dataRemote, there will be only
one instance of dataInterface, as part of the projectServer with dataRemote=False.
"""
import os
import re
import time
import glob
import threading
import logging
from pathlib import Path
from typing import List, Union
import pydicom
import rtCommon.utils as utils
from rtCommon.remoteable import RemoteableExtensible
from rtCommon.fileWatcher import FileWatcher
from rtCommon.errors import StateError, RequestError, InvocationError, ValidationError
from rtCommon.structDict import StructDict
from rtCommon.imageHandling import readDicomFromBuffer, anonymizeDicom


class DataInterface(RemoteableExtensible):
    """
    Provides functions for accessing remote or local files depending on if dateRemote flag is
    set true or false. 

    If dataRemote=True, then the RemoteExtensible parent class takes over and forwards all
    requests to a remote server via a callback function registered with the RemoteExtensible object.
    In that case *none* of the methods below will be locally invoked.

    If dataRemote=False, then the methods below will be invoked locally and the RemoteExtensible
    parent class is inoperable (i.e. does nothing).
    """
    def __init__(self, dataRemote :bool=False, allowedDirs :List[str]=None, 
                 allowedFileTypes :List[str]=None, scannerClockSkew :float=0):
        """
        Args:
            dataRemote (bool): whether data will be served from the local instance or requests forwarded
                to a remote instance for handling.
            allowedDirs (list): list of directories from which files are allowed to be read/writting. File
                operations will not be permitted unless the file path is a child of an allowed directory.
            allowedFileTypes (list): list of file extensions, such as '.dcm', '.txt', for which file
                operations are permitted. No file operations will be done unless the file extension matches
                one on the list.
            scannerClockSkew (float): number of seconds the scanner's clock is ahead of the
                data server clock
        """
        super().__init__(isRemote=dataRemote)
        if dataRemote is True:
            return
        self.initWatchSet = False
        self.watchDir = None
        self.currentStreamId = 0
        self.streamInfo = None
        self.allowedDirs = allowedDirs
        self.scannerClockSkew = scannerClockSkew
        # Remove trailing slash from dir names
        if allowedDirs is not None:
            self.allowedDirs = [dir.rstrip('/') for dir in allowedDirs]
        self.allowedFileTypes = allowedFileTypes
        # make sure allowed file extensions start with '.'
        if allowedFileTypes is not None:
            if allowedFileTypes[0] != '*':
                for i in range(len(allowedFileTypes)):
                    if not allowedFileTypes[i].startswith('.'):
                        allowedFileTypes[i] = '.' + allowedFileTypes[i]
        self.fileWatchLock = threading.Lock()
        # instantiate local FileWatcher
        self.fileWatcher = FileWatcher()

    def __del__(self):
        if hasattr(self, "fileWatcher"):
            if self.fileWatcher is not None:
                self.fileWatcher.__del__()
                self.fileWatcher = None

    def initScannerStream(self, imgDir: str, filePattern: str, minFileSize: int,
                          anonymize: bool=True, demoStep: int=0) -> int:
        """
        Initialize a data stream context with image directory and filepattern.
        Once the stream is initialized call getImageData() to retrieve image data.
        NOTE: currently only one stream at a time is supported.

        Args:
            imgDir: the directory where the images are or will be written from the MRI scanner.
            filePattern: a pattern of the image file names that has a TR tag which will be used
                to index the images, for example 'scan01_{TR:03d}.dcm'. In this example a call to
                getImageData(imgIndex=6) would look for dicom file 'scan01_006.dcm'.
            minFileSize: Minimum size of the file to return (continue waiting if below this size)
            anonymize: Whether to remove participant specific fields from the Dicom header

        Returns:
            streamId: An identifier used when calling getImageData()
        """
        self._checkAllowedDirs(imgDir)
        self._checkAllowedFileTypes(filePattern)
        
        # check that filePattern has {TR} in it
        if not re.match(r'.*{TR.*', filePattern):
            raise InvocationError(r"initScannerStream filePattern must have a {TR} pattern")
        self.currentStreamId = self.currentStreamId + 1
        self.streamInfo = StructDict({
            'streamId': self.currentStreamId,
            'type': 'scanner',
            'imgDir': imgDir,
            'filePattern': filePattern,
            'minFileSize': minFileSize,
            'anonymize': anonymize,
            'demoStep': demoStep,
            'imgIndex': 0,
        })
        _, file_ext = os.path.splitext(filePattern)
        self.initWatch(imgDir, '*' + file_ext, minFileSize, demoStep)
        return self.currentStreamId


    def getImageData(self, streamId: int, imageIndex: int=None, timeout: int=5) -> pydicom.dataset.FileDataset:
        """
        Get data from a stream initialized with initScannerStream

        Args:
            streamId: Id of a previously opened stream.
            imageIndex: Which image from the stream to retrieve. If left blank it will
                retrieve the next image in the stream (next after either the last request or
                starting from 0 if no previous requests)
            timeout: Max number of seconds to wait for image data to be available
        Returns:
            The bytes array representing the image data
            returns pydicom.dataset.FileDataset
        """
        if self.currentStreamId == 0 or self.currentStreamId != streamId or self.streamInfo.streamId != streamId:
            raise ValidationError(f"StreamID mismatch {self.currentStreamId} : {streamId}")

        if imageIndex is None:
            imageIndex = self.streamInfo.imgIndex
        filename = self.streamInfo.filePattern.format(TR=imageIndex)

        if timeout <= 0:
            # Don't allow infinite timeout
            raise RequestError("getImageData: timeout parameter must be > 0 secs")

        loop_timeout = 5  # 5 seconds per loop
        endTime = time.time() + timeout
        while time.time() < endTime:
            time_remaining = endTime - time.time()
            if time_remaining < loop_timeout:
                loop_timeout = time_remaining
            try:
                data = self.watchFile(filename, loop_timeout)
                dicomImg = readDicomFromBuffer(data)
                # Convert pixel data to a numpy.ndarray internally.
                # Note: the conversion cause error in pickle encoding
                # dicomImg.convert_pixel_data()
                self.streamInfo.imgIndex = imageIndex + 1
                if self.streamInfo.anonymize is True:
                    dicomImg = anonymizeDicom(dicomImg)
                return dicomImg
            except TimeoutError as err:
                logging.info(f"Waiting for {filename} ...")
                pass
            except ValidationError as err:
                # readDicomFromBuffer will raise ValidationError if Dicom seems
                # corrupted. Retry for up to timeout.
                logging.info(f"Dicom not completely written, retry ...")
                time.sleep(0.05)
                pass
            except Exception as err:
                errMsg = f"getImageData Error, filename {filename} err: {err}"
                logging.error(errMsg)
                raise RequestError(errMsg)
        raise RequestError(f"getImageData: Dicom file {self.streamInfo.imgDir}/{filename} not found or corrupted")

    def getFile(self, filename: str) -> bytes:
        """Returns a file's data immediately or fails if the file doesn't exist."""
        fileDir, fileCheck = os.path.split(filename)
        self._checkAllowedDirs(fileDir)
        self._checkAllowedFileTypes(fileCheck)

        data = None
        if not os.path.exists(filename):
            raise FileNotFoundError(f'File not found {filename}')
        with open(filename, 'rb') as fp:
            data = fp.read()
        # Consider - detect string encoding - but this could be computationally expenise on large data
        # encoding = chardet.detect(data)['encoding']
        # if encoding == 'ascii':
        #     data = data.decode(encoding)
        return data

    def getNewestFile(self, filepattern: str) -> bytes:
        """Searches for files matching filePattern and returns the data from the newest one."""
        data = None
        baseDir, filePattern = os.path.split(filepattern)
        self._checkAllowedDirs(baseDir)
        if not os.path.isabs(baseDir):
            # TODO - handle relative paths
            pass
        filename = utils.findNewestFile(baseDir, filePattern)
        self._checkAllowedFileTypes(filename)
        if filename is None:
            # No file matching pattern
            raise FileNotFoundError('No file found matching pattern {}'.format(filePattern))
        elif not os.path.exists(filename):
            raise FileNotFoundError('File missing after match {}'.format(filePattern))
        else:
            with open(filename, 'rb') as fp:
                data = fp.read()
        return data

    def initWatch(self, dir: str, filePattern: str, minFileSize: int, demoStep: int=0) -> None:
        """Initialize a watch directory for files matching filePattern.

        No data is returned by this function, but a filesystem watch is established.
        After calling initWatch, use watchFile() to watch for a specific file's arrival.

        Args:
            dir: Directory to watch for arrival (creation) of new files
            filePattern: Regex style filename pattern of files to watch for (i.e. \*.dcm)
            minFileSize: Minimum size of the file to return (continue waiting if below this size)
            demoStep: Minimum interval (in seconds) to wait before returning files.
                Useful for demos replaying existing files while mimicking original timing.
        """
        self._checkAllowedDirs(dir)
        self._checkAllowedFileTypes(filePattern)
        self.fileWatchLock.acquire()
        if self.initWatchSet is True:
            # Stop the previous watch to start a new one
            assert self.fileWatcher is not None
            self.fileWatcher.__del__()
            self.fileWatcher = FileWatcher()
        self.initWatchSet = False
        try:
            self.fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
            self.watchDir = dir
            self.initWatchSet = True
        finally:
            self.fileWatchLock.release()
        return

    def watchFile(self, filename: str, timeout: int=5) -> bytes:
        """Watches for a specific file to be created and returns the file data.

        InitWatch() must be called first, before watching for specific files.
        If filename includes the full path, the path must match that used in initWatch().

        Args:
            filename: Filename to watch for
            timeout: Max number of seconds to wait for file to be available
        Returns:
            The file data
        """
        data = None
        if not self.initWatchSet:
            raise StateError("DataInterface: watchFile() called without an initWatch()")

        # check filename dir matches initWatch dir
        fileDir, fileCheck = os.path.split(filename)
        if fileDir not in ('', None):
            if fileDir != self.watchDir:
                raise RequestError("DataInterface: watchFile: filepath doesn't match "
                                    f"watch directory: {fileDir}, {self.watchDir}")
            self._checkAllowedDirs(fileDir)
        self._checkAllowedFileTypes(fileCheck)

        self.fileWatchLock.acquire()
        try:
            foundFilename = self.fileWatcher.waitForFile(filename, timeout=timeout, timeCheckIncrement=0.25)
        finally:
            self.fileWatchLock.release()
        if foundFilename is None:
            raise TimeoutError("WatchFile: Timeout {}s: {}".format(timeout, filename))
        else:
            with open(foundFilename, 'rb') as fp:
                data = fp.read()
        return data

    def putFile(self, filename: str, data: Union[str, bytes], compress: bool=False) -> None:
        """
        Create a file (filename) and write the bytes or text to it. 
        In remote mode the file is written at the remote.

        Args:
            filename: Name of file to create
            data: data to write to the file
            compress: Whether to compress the data in transit (not within the file),
                only has affect in remote mode.
        """
        fileDir, fileCheck = os.path.split(filename)
        self._checkAllowedDirs(fileDir)
        self._checkAllowedFileTypes(fileCheck)

        if type(data) == str:
            data = data.encode()
        elif type(data) == float or type(data) == int:
            data = str(data)
            data = data.encode()

        outputDir = os.path.dirname(filename)
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)
        with open(filename, 'wb+') as binFile:
            binFile.write(data)
        return

    def listFiles(self, filepattern: str) -> List[str]:
        """Lists files matching the regex filePattern"""
        fileDir, fileCheck = os.path.split(filepattern)
        self._checkAllowedDirs(fileDir)
        self._checkAllowedFileTypes(fileCheck)
        if not os.path.isabs(filepattern):
            errStr = "listFiles must have an absolute path: {}".format(filepattern)
            raise RequestError(errStr)
        fileList = []
        for filename in glob.iglob(filepattern, recursive=True):
            if os.path.isdir(filename):
                continue
            fileList.append(filename)
        fileList = self._filterFileList(fileList)
        return fileList

    def listDirs(self, dirpattern: str) -> List[str]:
        """Lists directories matching the regex filePattern"""
        parentDir, _ = os.path.split(dirpattern)
        self._checkAllowedDirs(parentDir)
        if not os.path.isabs(dirpattern):
            errStr = "listFiles must have an absolute path: {}".format(dirpattern)
            raise RequestError(errStr)
        dirList = []
        for item in glob.iglob(dirpattern, recursive=False):
            if os.path.isfile(item):
                continue
            dirList.append(item)
        return dirList

    def getAllowedFileTypes(self) -> List[str]:
        """Returns the list of file extensions which are allowed for read and write"""
        return self.allowedFileTypes

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
        return skew + self.scannerClockSkew

    def ping(self) -> float:
        """Returns seconds since the epoch"""
        return time.time()

    def _checkAllowedDirs(self, dir: str) -> bool:
        if self.allowedDirs is None or len(self.allowedDirs) == 0:
            raise ValidationError('DataInterface: no allowed directories are set')
        if dir is None:
            return True
        if self.allowedDirs[0] == '*':
            return True
        dirMatch = False
        for allowedDir in self.allowedDirs:
            if dir.startswith(allowedDir):
                dirMatch = True
                break
        if dirMatch is False:
            raise ValidationError(
                f'Path {dir} not within list of allowed directories {self.allowedDirs}. '
                'Make sure you specified a full (absolute) path. '
                'Specify allowed directories with FileServer -d parameter.')
        return True

    def _checkAllowedFileTypes(self, filename: str) -> bool:
        """ Class-private function for checking if a file is allowed."""
        if self.allowedFileTypes is None or len(self.allowedFileTypes) == 0:
            raise ValidationError('DataInterface: no allowed file types are set')
        if filename is None or filename == '':
            return True
        if self.allowedFileTypes[0] == '*':
            return True
        if filename[-1] == '*':
            # wildcards will be filtered later
            return True
        fileExtension = Path(filename).suffix
        if fileExtension not in self.allowedFileTypes:
            raise ValidationError(
                f"File type {fileExtension} not in list of allowed file types {self.allowedFileTypes}. "
                "Specify allowed filetypes with FileServer -f parameter.")
        return True

    def _filterFileList(self, fileList: List[str]) -> List[str]:
        """Class-private funtion to filter a list of files to include only allowed ones.
            Args: fileList - list of files to filter
            Returns: filtered fileList - containing only the allowed files
        """
        if self.allowedFileTypes is None or len(self.allowedFileTypes) == 0:
            raise ValidationError('DataInterface: no allowed file types are set')
        if self.allowedFileTypes[0] == '*':
            return fileList
        filteredList = []
        for filename in fileList:
            if os.path.isdir(filename):
                continue
            fileExtension = Path(filename).suffix
            if fileExtension in self.allowedFileTypes:
                filteredList.append(filename)
        return filteredList


#################################################################################
### Helper Function to upload and download sets of files from or to the cloud ###
#################################################################################
def uploadFilesFromList(dataInterface, fileList :List[str], outputDir :str, srcDirPrefix=None) -> None:
    """
    Copies files in fileList from the remote onto the system where this call is being made.
    """
    for file in fileList:
        fileDir, filename = os.path.split(file)
        if srcDirPrefix is not None and fileDir.startswith(srcDirPrefix):
            # Get just the part of fileDir after the srcDirPrefix
            subDir = fileDir.replace(srcDirPrefix, '')
        else:
            subDir = ''
        try:
            data = dataInterface.getFile(file)
        except Exception as err:
            if type(err) is IsADirectoryError or 'IsADirectoryError' in str(err):
                continue
            raise(err)
        outputFilename = os.path.normpath(outputDir + '/' + subDir + '/' + filename)
        logging.info('upload: {} --> {}'.format(file, outputFilename))
        print('upload: {} --> {}'.format(file, outputFilename))
        utils.writeFile(outputFilename, data)

def downloadFilesFromList(dataInterface, fileList :List[str], outputDir :str, srcDirPrefix=None) -> None:
    """
    Copies files in fileList from this computer to the remote.
    """
    for file in fileList:
        if os.path.isdir(file):
            continue
        with open(file, 'rb') as fp:
            data = fp.read()
        fileDir, filename = os.path.split(file)
        if srcDirPrefix is not None and fileDir.startswith(srcDirPrefix):
            # Get just the part of fileDir after the srcDirPrefix
            subDir = fileDir.replace(srcDirPrefix, '')
        else:
            subDir = ''
        outputFilename = os.path.normpath(outputDir + '/' + subDir + '/' + filename)
        logging.info('download: {} --> {}'.format(file, outputFilename))
        print('download: {} --> {}'.format(file, outputFilename))
        dataInterface.putFile(outputFilename, data)
    return

def uploadFolderToCloud(dataInterface, srcDir :str, outputDir :str) -> None:
    """
    Copies a folder (directory) from the remote to the system where this call is run
    """
    allowedFileTypes = dataInterface.getAllowedFileTypes()
    print('Uploading folder {} to cloud'.format(srcDir))
    logging.info('Uploading folder {} to cloud'.format(srcDir))
    logging.info('UploadFolder limited to file types: {}'.format(allowedFileTypes))
    dirPattern = os.path.join(srcDir, '**')  # ** wildcard means include sub-directories
    fileList = dataInterface.listFiles(dirPattern)
    # The src prefix is the part of the path to eliminate in the destination path
    # This will be everything except the last subdirectory in srcDir
    srcPrefix = os.path.dirname(srcDir)
    uploadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=srcPrefix)

def uploadFilesToCloud(dataInterface, srcFilePattern :str, outputDir :str):
    """
    Copies files matching (regex) srcFilePattern from the remote onto the system 
        where this call is being made.
    """
    # get the list of files to upload
    fileList = dataInterface.listFiles(srcFilePattern)
    uploadFilesFromList(dataInterface, fileList, outputDir)

def downloadFolderFromCloud(dataInterface, srcDir :str, outputDir :str, deleteAfter=False) -> None:
    """
    Copies a directory from the system where this call is made to the remote system.
    """
    allowedFileTypes = dataInterface.getAllowedFileTypes()
    print('Downloading folder {} from the cloud'.format(srcDir))
    logging.info('Downloading folder {} from the cloud'.format(srcDir))
    logging.info('DownloadFolder limited to file types: {}'.format(allowedFileTypes))
    dirPattern = os.path.join(srcDir, '**')
    fileList = [x for x in glob.iglob(dirPattern, recursive=True)]
    filteredList = []
    for filename in fileList:
        fileExtension = Path(filename).suffix
        if fileExtension in allowedFileTypes or '*' in allowedFileTypes:
            filteredList.append(filename)
    # The src prefix is the part of the path to eliminate in the destination path
    # This will be everything except the last subdirectory in srcDir
    srcPrefix = os.path.dirname(srcDir)
    downloadFilesFromList(dataInterface, filteredList, outputDir, srcDirPrefix=srcPrefix)
    if deleteAfter:
        utils.deleteFilesFromList(filteredList)

def downloadFilesFromCloud(dataInterface, srcFilePattern :str, outputDir :str, deleteAfter=False) -> None:
    """
    Copies files matching srcFilePattern from the system where this call is made
        to the remote system.
    """
    fileList = [x for x in glob.iglob(srcFilePattern)]
    downloadFilesFromList(dataInterface, fileList, outputDir)
    if deleteAfter:
        utils.deleteFilesFromList(fileList)


# Previous - distinguished which functions should always run locally (i.e. upload and download
# functions) using this class definition.
#
# # This is a more specific class adding function the cloud client would run locally
# class DataInterfaceClient(DataInterface):
#     def __init__(self, dataRemote=False):
#         super().__init__(dataRemote)
#         localOnlyFunctions = [
#             'uploadFilesFromList',
#             'downloadFilesFromList',
#             'uploadFolderToCloud',
#             'uploadFilesToCloud',
#             'downloadFolderFromCloud',
#             'downloadFilesFromCloud',
#         ]
#         self.addLocalAttributes(localOnlyFunctions)

