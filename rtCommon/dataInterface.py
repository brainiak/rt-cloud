"""
Client module for receiving and sending files to/from a remote FileWatcher. 
Can also be used in local-mode accessing local files without a FileWatcher.
"""
import os
import re
import time
import glob
import chardet
import threading
import logging
from pathlib import Path
from typing import List, Any
import rtCommon.utils as utils
from rtCommon.remoteable import RemoteableExtensible
from rtCommon.fileWatcher import FileWatcher
from rtCommon.errors import StateError, RequestError, InvocationError, ValidationError, NotImplementedError
from rtCommon.structDict import StructDict
from rtCommon.rtTypes import StrOrBytes
from rtCommon.imageHandling import readDicomFromBuffer


# This is the most general purpose one (for example used in the control room file server)
class DataInterface(RemoteableExtensible):
    """
    Provides functions for accessing remote or local files depending on configuration
    """
    def __init__(self, dataremote=False, allowedDirs=None, allowedFileTypes=None):
        super().__init__(dataremote)
        if dataremote is True:
            return
        self.initWatchSet = False
        self.currentStreamId = 0
        self.streamInfo = None
        self.allowedDirs = allowedDirs
        self.allowedFileTypes = allowedFileTypes
        self.fileWatchLock = threading.Lock()
        # instantiate local FileWatcher
        self.fileWatcher = FileWatcher()

    def __del__(self):
        if self.fileWatcher is not None:
            self.fileWatcher.__del__()
            self.fileWatcher = None

    def initScannerStream(self, imgDir: str, filePattern: str,
                          minFileSize: int, demoStep: int=0) -> int:
        """
        Initialize a data stream context with image directory and filepattern.
        Once the stream is initialized call getImageData() to retrieve image data.
        NOTE: currently only one stream at a time is supported.

        Args:
            imgDir: the directory where the images are or will be written from the MRI scanner.
            filePattern: a pattern of the image file names that has a TR tag which will be used
                to index the images, for example 'scan01_{TR:03d}.dcm'. In this example a call to
                getImageData(imgIndex=6) would look for dicom file 'scan01_006.dcm'.

        Returns:
            streamId: An identifier used when calling getImageData()
        """
        self.checkAllowedDirs(imgDir)
        self.checkAllowedFileTypes(filePattern)
        
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
            'demoStep': demoStep,
            'imgIndex': 0,
        })
        _, file_ext = os.path.splitext(filePattern)
        self._initWatch(imgDir, '*' + file_ext, minFileSize, demoStep)
        return self.currentStreamId


    def getImageData(self, streamId: int, imageIndex: int=None, timeout: int=5):
        """
        Get data from a stream initialized with initScannerStream or initOpenNeuroStream

        Args:
            streamId: Id of a previously opened stream.
            imageIndex: Which image from the stream to retrieve. If left blank it will
                retrieve the next image in the stream (next after either the last request or 
                starting from 0 if no previous requests)
        Returns:
            The bytes array representing the image data
            returns pydicom.dataset.FileDataset
        """
        if self.currentStreamId == 0 or self.currentStreamId != streamId:
            raise ValidationError(f"StreamID mismatch {self.currentStreamId} : {streamId}")

        if imageIndex is None:
            imageIndex = self.currentStreamId.imgIndex
        filename = self.streamInfo.filePattern.format(TR=imageIndex)

        retries = 0
        while retries < 5:
            retries += 1
            try:
                data = self._watchFile(filename, timeout)
                # TODO - Inject error here and see if commpipe remains open
                dicomImg = readDicomFromBuffer(data)
                # Convert pixel data to a numpy.ndarray internally.
                # Note: the conversion cause error in pickle encoding
                # dicomImg.convert_pixel_data()
                # successful
                self.streamInfo.imgIndex = imageIndex + 1
                return dicomImg
            except TimeoutError as err:
                logging.warning(f"Timeout waiting for {filename}. Retry in 100 ms")
                time.sleep(0.1)
            except Exception as err:
                logging.error(f"getImageData Error, filename {filename} err: {err}")
                return None
        return None

    def getFile(self, filename: str) -> bytes:
        """Returns a file's data immediately or fails if the file doesn't exist."""
        fileDir, fileCheck = os.path.split(filename)
        self.checkAllowedDirs(fileDir)
        self.checkAllowedFileTypes(fileCheck)

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
        """Searches for files matching filePattern and returns the most recently created one."""
        data = None
        baseDir, filePattern = os.path.split(filepattern)
        self.checkAllowedDirs(baseDir)
        if not os.path.isabs(baseDir):
            # TODO - handle relative paths
            pass
        filename = utils.findNewestFile(baseDir, filePattern)
        self.checkAllowedFileTypes(filename)
        if filename is None:
            # No file matching pattern
            raise FileNotFoundError('No file found matching pattern {}'.format(filePattern))
        elif not os.path.exists(filename):
            raise FileNotFoundError('File missing after match {}'.format(filePattern))
        else:
            with open(filename, 'rb') as fp:
                data = fp.read()
        return data

    def _initWatch(self, dir: str, filePattern: str, minFileSize: int, demoStep: int=0) -> None:
        """Initialize a watch directory for files matching filePattern.

        No data is returned by this function, but a filesystem watch is established.
        After calling initWatch, use watchFile() to watch for a specific file's arrival.

        Args:
            dir: Directory to watch for arrival (creation) of new files
            filePattern: Regex style filename pattern of files to watch for (i.e. *.dcm)
            minFileSize: Minimum size of the file to return (continue waiting if below this size)
            demoStep: Minimum interval (in seconds) to wait before returning files.
                Useful for demos replaying existing files while mimicking original timing.
        """
        self.checkAllowedDirs(dir)
        self.checkAllowedFileTypes(filePattern)
        self.fileWatchLock.acquire()
        try:
            self.fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
        finally:
            self.fileWatchLock.release()
        self.initWatchSet = True
        return

    def _watchFile(self, filename: str, timeout: int=5) -> bytes:
        """Watches for a specific file to be created and returns the file data.

        InitWatch() must be called first, before watching for specific files.
        If filename includes the full path, the path must match that used in initWatch().
        """
        self.checkAllowedFileTypes(filename)
        data = None
        if not self.initWatchSet:
            raise StateError("DataInterface: watchFile() called without an initWatch()")
        self.fileWatchLock.acquire()
        try:
            foundFilename = self.fileWatcher.waitForFile(filename, timeout=timeout)
        finally:
            self.fileWatchLock.release()
        if foundFilename is None:
            raise TimeoutError("WatchFile: Timeout {}s: {}".format(timeout, filename))
        else:
            with open(foundFilename, 'rb') as fp:
                data = fp.read()
        return data

    def putFile(self, filename: str, data: StrOrBytes, compress: bool=False) -> None:
        """
        Writes bytes or text file filename. In remote mode the file is written at the remote.

        Args:
            filename: Name of file to create
            data: data to write to the file
            compress: Whether to compress the data in transit (not within the file),
                only has affect in remote mode.
        """
        fileDir, fileCheck = os.path.split(filename)
        self.checkAllowedDirs(fileDir)
        self.checkAllowedFileTypes(fileCheck)

        if type(data) == str:
            data = data.encode()

        outputDir = os.path.dirname(filename)
        if not os.path.exists(outputDir):
            os.makedirs(outputDir)
        with open(filename, 'wb+') as binFile:
            binFile.write(data)
        return

    def listFiles(self, filepattern: str) -> List[str]:
        """Lists files matching regex filePattern from the remote filesystem"""
        fileDir, fileCheck = os.path.split(filepattern)
        self.checkAllowedDirs(fileDir)
        self.checkAllowedFileTypes(fileCheck)
        if not os.path.isabs(filepattern):
            errStr = "listFiles must have an absolute path: {}".format(filepattern)
            raise RequestError(errStr)
        fileList = []
        for filename in glob.iglob(filepattern, recursive=True):
            if os.path.isdir(filename):
                continue
            fileList.append(filename)
        fileList = self.filterFileList(fileList)
        return fileList

    def getAllowedFileTypes(self) -> List[str]:
        """Returns file extensions which remote filesystem will allow to read and write"""
        if self.allowedFileTypes is None:
            return ['*']
        else:
            return self.allowedFileTypes

    def checkAllowedDirs(self, dir):
        if dir is None:
            return True
        if self.allowedDirs is not None:
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

    def checkAllowedFileTypes(self, filename):
        if filename is None or filename == '':
            return True
        if self.allowedFileTypes is not None:
            if filename[-1] == '*':
                # wildcards will be filtered later
                return True
            fileExtension = Path(filename).suffix
            if fileExtension not in self.allowedFileTypes:
                raise ValidationError(
                    f"File type {fileExtension} not in list of allowed file types {self.allowedFileTypes}. "
                    "Specify allowed filetypes with FileServer -f parameter.")
        return True

    def filterFileList(self, fileList):
        filteredList = []
        for filename in fileList:
            if os.path.isdir(filename):
                continue
            fileExtension = Path(filename).suffix
            if fileExtension in self.allowedFileTypes:
                filteredList.append(filename)
        return filteredList

# # This is a more specific class adding function the cloud client would run locally
# class DataInterfaceClient(DataInterface):
#     def __init__(self, dataremote=False):
#         super().__init__(dataremote)
#         localOnlyFunctions = [
#             'uploadFilesFromList',
#             'downloadFilesFromList',
#             'uploadFolderToCloud',
#             'uploadFilesToCloud',
#             'downloadFolderFromCloud',
#             'downloadFilesFromCloud',
#         ]
#         self.addLocalAttributes(localOnlyFunctions)

### Helper Function to upload and download sets of files ###
def uploadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=None):
    """
    Copies files in fileList from the remote onto the system
        where this call is being made.
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
        utils.writeFile(outputFilename, data)

def downloadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=None):
    """Copies files in fileList from this computer to the remote."""
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
        dataInterface.putFile(outputFilename, data)
    return

def uploadFolderToCloud(dataInterface, srcDir, outputDir):
    """Copies a folder (directory) from the remote to the system where this call is run"""
    allowedFileTypes = dataInterface.getAllowedFileTypes()
    logging.info('Uploading folder {} to cloud'.format(srcDir))
    logging.info('UploadFolder limited to file types: {}'.format(allowedFileTypes))
    dirPattern = os.path.join(srcDir, '**')  # ** wildcard means include sub-directories
    fileList = dataInterface.listFiles(dirPattern)
    # The src prefix is the part of the path to eliminate in the destination path
    # This will be everything except the last subdirectory in srcDir
    srcPrefix = os.path.dirname(srcDir)
    uploadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=srcPrefix)

def uploadFilesToCloud(dataInterface, srcFilePattern, outputDir):
    """
    Copies files matching (regex) srcFilePattern from the remote onto the system 
        where this call is being made.
    """
    # get the list of files to upload
    fileList = dataInterface.listFiles(srcFilePattern)
    uploadFilesFromList(dataInterface, fileList, outputDir)

def downloadFolderFromCloud(dataInterface, srcDir, outputDir, deleteAfter=False):
    """Copies a directory from the system where this call is made to the remote system."""
    allowedFileTypes = dataInterface.getAllowedFileTypes()
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

def downloadFilesFromCloud(dataInterface, srcFilePattern, outputDir, deleteAfter=False):
    """
    Copies files matching srcFilePattern from the system where this call is made
        to the remote system.
    """
    fileList = [x for x in glob.iglob(srcFilePattern)]
    downloadFilesFromList(dataInterface, fileList, outputDir)
    if deleteAfter:
        utils.deleteFilesFromList(fileList)

