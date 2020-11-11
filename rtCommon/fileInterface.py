"""
Client module for receiving and sending files to/from a remote FileWatcher. 
Can also be used in local-mode accessing local files without a FileWatcher.
"""
import os
import glob
import logging
from pathlib import Path
import rtCommon.utils as utils
import rtCommon.projectUtils as projUtils
import rtCommon.wsRequestStructs as req
from rtCommon.fileWatcher import FileWatcher
from rtCommon.errors import StateError, RequestError
from rtCommon.webServer import processPyScriptRequest



class FileInterface:
    """
    Provides functions for accessing remote or local files depending on configuration
    """
    def __init__(self, filesremote=False):
        """
        if filesremote is true requests will be sent to a remote FileWatcher
        """
        self.local = not filesremote
        self.fileWatcher = None
        self.initWatchSet = False
        if self.local:
            self.fileWatcher = FileWatcher()

    def __del__(self):
        if self.fileWatcher is not None:
            self.fileWatcher.__del__()
            self.fileWatcher = None

    def areFilesremote(self):
        """Indicates whether operating in remote or local mode."""
        return not self.local

    def getFile(self, filename):
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
        # TODO - Add to BIDS archive here? And in the other file methods, or do this outside of fileInterface?
        return data

    def getNewestFile(self, filePattern):
        """Searches for files matching filePattern and returns the most recently created one."""
        data = None
        if self.local:
            baseDir, filePattern = os.path.split(filePattern)
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

    def initWatch(self, dir, filePattern, minFileSize, demoStep=0):
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

    def watchFile(self, filename, timeout=5):
        """Watches for a specific file to be created and returns the file data.

        InitWatch() must be called first, before watching for specific files.
        If filename includes the full path, the path must match that used in initWatch().
        """
        data = None
        if not self.initWatchSet:
            raise StateError("FileInterface: watchFile() called without an initWatch()")
        if self.local:
            retVal = self.fileWatcher.waitForFile(filename, timeout=timeout)
            if retVal is None:
                raise TimeoutError("WatchFile: Timeout {}s: {}".format(timeout, filename))
            else:
                with open(filename, 'rb') as fp:
                    data = fp.read()
        else:
            watchCmd = req.watchFileReqStruct(filename, timeout=timeout)
            retVals = processPyScriptRequest(watchCmd)
            data = retVals.data
        return data

    def putTextFile(self, filename, text):
        """
        Writes text to file filename. In remote mode the file is written at the remote.
        """
        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'w+') as textFile:
                textFile.write(text)
        else:
            putFileCmd = req.putTextFileReqStruct(filename, text)
            _ = processPyScriptRequest(putFileCmd)
        return

    def putBinaryFile(self, filename, data, compress=False):
        """
        Writes data to file filename. In remote mode the file is written at the remote.

        Args:
            filename: Name of file to create
            data: Binary data to write to the file
            compress: Whether to compress the data in transit (not when written to file)
        """
        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'wb+') as binFile:
                binFile.write(data)
        else:
            try:
                fileHash = None
                putFileCmd = req.putBinaryFileReqStruct(filename)
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

    def listFiles(self, filePattern):
        """Lists files matching regex filePattern from the remote filesystem"""
        if self.local:
            if not os.path.isabs(filePattern):
                errStr = "listFiles must have an absolute path: {}".format(filePattern)
                raise RequestError(errStr)
            fileList = []
            for filename in glob.iglob(filePattern, recursive=True):
                if os.path.isdir(filename):
                    continue
                fileList.append(filename)
        else:
            listCmd = req.listFilesReqStruct(filePattern)
            retVals = processPyScriptRequest(listCmd)
            fileList = retVals.get('fileList')
            if type(fileList) is not list:
                errStr = "Invalid fileList reponse type {}: expecting list".format(type(fileList))
                raise StateError(errStr)
        return fileList

    def allowedFileTypes(self):
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
            self.putBinaryFile(outputFilename, data)
        return
