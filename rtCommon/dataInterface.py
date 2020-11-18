"""
Client module for receiving and sending files to/from a remote FileWatcher. 
Can also be used in local-mode accessing local files without a FileWatcher.
"""
import os
import re
import time
import glob
import chardet
import logging
from pathlib import Path
from typing import List, Any
import rtCommon.utils as utils
import rtCommon.projectUtils as projUtils
import rtCommon.wsRequestStructs as req
from rtCommon.fileWatcher import FileWatcher
from rtCommon.errors import StateError, RequestError, InvocationError, ValidationError, NotImplementedError
from rtCommon.webServer import processPyScriptRequest
from rtCommon.structDict import StructDict
from rtCommon.types import StrOrBytes
from rtCommon.imageHandling import readDicomFromBuffer


# def initScannerStream(self, imgDir: str, filePattern: str) -> int: {}  // returns streamId
# def initOpenNeuroStream(self, dataset: str, subject: str, session: str, run: str, task: str) -> int: {}  // returns streamId
# def getImageData(self, streamId: int, imageIndex: int=None) -> bytes: {}
# def getBidsIncremental(self, streamId: int, imageIndex: int=None) -> Any: {}  // return a BIDS-I image (typed as Any for now)


class DataInterface:
    """
    Provides functions for accessing remote or local files depending on configuration
    """
    def __init__(self, dataremote=False):
        """
        if dataremote is true requests will be sent to a remote FileWatcher
        """
        self.local = not dataremote
        self.fileWatcher = None
        self.initWatchSet = False
        self.currentStreamId = 0
        self.streamInfo = None
        if self.local:
            self.fileWatcher = FileWatcher()

    def __del__(self):
        if self.fileWatcher is not None:
            self.fileWatcher.__del__()
            self.fileWatcher = None

    def isDataRemote(self) -> bool:
        """Indicates whether operating in remote or local mode."""
        return not self.local

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
        if self.local:
            self._initWatch(imgDir, '*' + file_ext, minFileSize, demoStep)
        else:
            # make remote call
            # self.currentStreamId = remotecall()
            # return self.currentStreamId
            self._initWatch(imgDir, '*' + file_ext, minFileSize, demoStep)
            # raise NotImplementedError("Remote initScannerStream not implemented yet")
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
                if self.local:
                    data = self._watchFile(filename, timeout)
                else:
                    # raise NotImplementedError("Remote getImageData not implemented yet")
                    data = self._watchFile(filename, timeout)
                # TODO - Inject error here and see if commpipe remains open
                dicomImg = readDicomFromBuffer(data)
                # check that pixel array is complete
                dicomImg.convert_pixel_data()
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

    def initOpenNeuroStream(self, dataset: str, subject: str, 
                            session: str, run: str, task: str,
                            demoStep: int=0) -> int:
        """
        Intialize a data stream from an OpenNeuro dataset

        Returns: streamId - An identifier used when calling getImageData()
        """
        if self.local:
            self.currentStreamId = self.currentStreamId + 1
            # TODO create an openNeuro client object
            openNeuroClient = None
            self.streamInfo = StructDict({
                'streamId': self.currentStreamId,
                'type': 'openneuro',
                'dataset': dataset,
                'subject': subject,
                'session': session,
                'run': run,
                'task': task,
                'demoStep': demoStep,
                'imgIndex': 0,
                'client': openNeuroClient,

            })
            # return self.currentStreamId
            raise NotImplementedError("initOpenNeuroStream not implemented yet")
        else:
            raise NotImplementedError("Remote initOpenNeuroStream not implemented yet")

    def getBidsIncremental(self, streamId: int, imageIndex: int=None) -> Any:
        """
        Returns:
            a BIDS-Incremental image (typed as Any for now)
        """
        if self.local:
            if self.streamInfo.type == 'scanner':
                # TODO: convert Dicom matching pattern to Bids-I and return Bids-I
                pass
            elif self.streamInfo.type == 'openneuro':
                # TODO: call openneuro client to get next image and return it
                pass
            else:
                raise RequestError(f"Stream type {self.streamInfo.type} not supported")
        raise NotImplementedError("getBidsIncremental")

    def getFile(self, filename: str) -> bytes:
        """Returns a file's data immediately or fails if the file doesn't exist."""
        data = None
        if self.local:
            # TODO - BIDS Integration: with flag convert dicom to BIDS-I here?
            with open(filename, 'rb') as fp:
                data = fp.read()
        else:
            getFileCmd = req.getFileReqStruct(filename)
            retVals = processPyScriptRequest(getFileCmd)
            data = retVals.data
        # Consider - detect string encoding - but this could be computationally expenise on large data
        # encoding = chardet.detect(data)['encoding']
        # if encoding == 'ascii':
        #     data = data.decode(encoding)
        # TODO - Add to BIDS archive here? And in the other file methods, or do this outside of dataInterface?
        return data

    def getNewestFile(self, filepattern: str) -> bytes:
        """Searches for files matching filePattern and returns the most recently created one."""
        data = None
        if self.local:
            baseDir, filePattern = os.path.split(filepattern)
            if not os.path.isabs(baseDir):
                # TODO - handle relative paths
                pass
            filename = utils.findNewestFile(baseDir, filePattern)
            if filename is None:
                # No file matching pattern
                raise FileNotFoundError('No file found matching pattern {}'.format(filePattern))
            elif not os.path.exists(filename):
                raise FileNotFoundError('File missing after match {}'.format(filePattern))
            else:
                with open(filename, 'rb') as fp:
                    data = fp.read()
        else:
            getNewestFileCmd = req.getNewestFileReqStruct(filePattern)
            retVals = processPyScriptRequest(getNewestFileCmd)
            data = retVals.data
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
        if self.local:
            self.fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
        else:
            initWatchCmd = req.initWatchReqStruct(dir, filePattern, minFileSize, demoStep)
            _ = processPyScriptRequest(initWatchCmd)
        self.initWatchSet = True
        return

    def _watchFile(self, filename: str, timeout: int=5) -> bytes:
        """Watches for a specific file to be created and returns the file data.

        InitWatch() must be called first, before watching for specific files.
        If filename includes the full path, the path must match that used in initWatch().
        """
        data = None
        if not self.initWatchSet:
            raise StateError("DataInterface: watchFile() called without an initWatch()")
        if self.local:
            foundFilename = self.fileWatcher.waitForFile(filename, timeout=timeout)
            if foundFilename is None:
                raise TimeoutError("WatchFile: Timeout {}s: {}".format(timeout, filename))
            else:
                with open(foundFilename, 'rb') as fp:
                    data = fp.read()
        else:
            watchCmd = req.watchFileReqStruct(filename, timeout=timeout)
            retVals = processPyScriptRequest(watchCmd)
            data = retVals.data
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
        if type(data) == str:
            data = data.encode()

        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'wb+') as binFile:
                binFile.write(data)
        else:
            try:
                fileHash = None
                putFileCmd = req.putFileReqStruct(filename)
                for putFilePart in projUtils.generateDataParts(data, putFileCmd, compress):
                    fileHash = putFilePart.get('fileHash')
                    _ = processPyScriptRequest(putFilePart)
            except Exception as err:
                # Send error notice to clear any partially cached data on the server side
                # Add fileHash to message and send status=400 to notify
                if fileHash:
                    putFileCmd['fileHash'] = fileHash
                    putFileCmd['status'] = 400
                    _ = processPyScriptRequest(putFileCmd)
                raise err
        return

    def listFiles(self, filepattern: str) -> List[str]:
        """Lists files matching regex filePattern from the remote filesystem"""
        if self.local:
            if not os.path.isabs(filepattern):
                errStr = "listFiles must have an absolute path: {}".format(filepattern)
                raise RequestError(errStr)
            fileList = []
            for filename in glob.iglob(filepattern, recursive=True):
                if os.path.isdir(filename):
                    continue
                fileList.append(filename)
        else:
            listCmd = req.listFilesReqStruct(filepattern)
            retVals = processPyScriptRequest(listCmd)
            fileList = retVals.get('fileList')
            if type(fileList) is not list:
                errStr = "Invalid fileList reponse type {}: expecting list".format(type(fileList))
                raise StateError(errStr)
        return fileList

    def allowedFileTypes(self) -> List[str]:
        """Returns file extensions which remote filesystem will allow to read and write"""
        if self.local:
            return ['*']
        else:
            cmd = req.allowedFileTypesReqStruct()
            retVals = processPyScriptRequest(cmd)
            fileTypes = retVals.get('fileTypes')
            if type(fileTypes) is not list:
                errStr = "Invalid fileTypes reponse type {}: expecting list".format(type(fileTypes))
                raise StateError(errStr)
        return fileTypes

    def uploadFolderToCloud(self, srcDir, outputDir):
        """Copies a folder (directory) from the remote to the system where this call is run"""
        allowedFileTypes = self.allowedFileTypes()
        logging.info('Uploading folder {} to cloud'.format(srcDir))
        logging.info('UploadFolder limited to file types: {}'.format(allowedFileTypes))
        dirPattern = os.path.join(srcDir, '**')  # ** wildcard means include sub-directories
        fileList = self.listFiles(dirPattern)
        # The src prefix is the part of the path to eliminate in the destination path
        # This will be everything except the last subdirectory in srcDir
        srcPrefix = os.path.dirname(srcDir)
        self.uploadFilesFromList(fileList, outputDir, srcDirPrefix=srcPrefix)

    def uploadFilesToCloud(self, srcFilePattern, outputDir):
        """
        Copies files matching (regex) srcFilePattern from the remote onto the system 
            where this call is being made.
        """
        # get the list of files to upload
        fileList = self.listFiles(srcFilePattern)
        self.uploadFilesFromList(fileList, outputDir)

    def uploadFilesFromList(self, fileList, outputDir, srcDirPrefix=None):
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
                data = self.getFile(file)
            except Exception as err:
                if type(err) is IsADirectoryError or 'IsADirectoryError' in str(err):
                    continue
                raise(err)
            outputFilename = os.path.normpath(outputDir + '/' + subDir + '/' + filename)
            logging.info('upload: {} --> {}'.format(file, outputFilename))
            utils.writeFile(outputFilename, data)

    def downloadFolderFromCloud(self, srcDir, outputDir, deleteAfter=False):
        """Copies a directory from the system where this call is made to the remote system."""
        allowedFileTypes = self.allowedFileTypes()
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
        self.downloadFilesFromList(filteredList, outputDir, srcDirPrefix=srcPrefix)
        if deleteAfter:
            utils.deleteFilesFromList(filteredList)

    def downloadFilesFromCloud(self, srcFilePattern, outputDir, deleteAfter=False):
        """
        Copies files matching srcFilePattern from the system where this call is made
            to the remote system.
        """
        fileList = [x for x in glob.iglob(srcFilePattern)]
        self.downloadFilesFromList(fileList, outputDir)
        if deleteAfter:
            utils.deleteFilesFromList(fileList)

    def downloadFilesFromList(self, fileList, outputDir, srcDirPrefix=None):
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
            self.putFile(outputFilename, data)
        return
