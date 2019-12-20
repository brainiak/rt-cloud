import os
import glob
from rtCommon.fileWatcher import FileWatcher
from rtCommon.utils import findNewestFile
import rtCommon.projectUtils as projUtils
from rtCommon.errors import StateError, RequestError


class FileInterface:
    def __init__(self, filesremote=False, commPipes=None):
        self.local = not filesremote
        self.commPipes = commPipes
        self.fileWatcher = None
        self.initWatchSet = False
        if self.local:
            self.fileWatcher = FileWatcher()

    def __del__(self):
        if self.fileWatcher is not None:
            self.fileWatcher.__del__()
            self.fileWatcher = None

    def getFile(self, filename):
        data = None
        if self.local:
            with open(filename, 'rb') as fp:
                data = fp.read()
        else:
            getFileCmd = projUtils.getFileReqStruct(filename)
            retVals = projUtils.clientSendCmd(self.commPipes, getFileCmd)
            data = retVals.data
        return data

    def getNewestFile(self, filePattern):
        data = None
        if self.local:
            baseDir, filePattern = os.path.split(filePattern)
            if not os.path.isabs(baseDir):
                # TODO - handle relative paths
                pass
            filename = findNewestFile(baseDir, filePattern)
            if filename is None:
                # No file matching pattern
                raise FileNotFoundError('No file found matching pattern {}'.format(filePattern))
            elif not os.path.exists(filename):
                raise FileNotFoundError('File missing after match {}'.format(filePattern))
            else:
                with open(filename, 'rb') as fp:
                    data = fp.read()
        else:
            getNewestFileCmd = projUtils.getNewestFileReqStruct(filePattern)
            retVals = projUtils.clientSendCmd(self.commPipes, getNewestFileCmd)
            data = retVals.data
        return data

    def initWatch(self, dir, filePattern, minFileSize, demoStep=0):
        if self.local:
            self.fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
        else:
            initWatchCmd = projUtils.initWatchReqStruct(dir, filePattern, minFileSize, demoStep)
            projUtils.clientSendCmd(self.commPipes, initWatchCmd)
        self.initWatchSet = True
        return

    def watchFile(self, filename, timeout=5):
        data = None
        if not self.initWatchSet:
            raise StateError("FileInterface: watchFile() called without an initWatch()")
        if self.local:
            retVal = self.fileWatcher.waitForFile(filename, timeout=timeout)
            if retVal is None:
                raise FileNotFoundError("WatchFile: Timeout {}s: {}".format(timeout, filename))
            else:
                with open(filename, 'rb') as fp:
                    data = fp.read()
        else:
            watchCmd = projUtils.watchFileReqStruct(filename, timeout=timeout)
            retVals = projUtils.clientSendCmd(self.commPipes, watchCmd)
            data = retVals.data
        return data

    def putTextFile(self, filename, text):
        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'w+') as textFile:
                textFile.write(text)
        else:
            putFileCmd = projUtils.putTextFileReqStruct(filename, text)
            projUtils.clientSendCmd(self.commPipes, putFileCmd)
        return

    def putBinaryFile(self, filename, data, compress=False):
        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'wb+') as binFile:
                binFile.write(data)
        else:
            try:
                fileHash = None
                putFileCmd = projUtils.putBinaryFileReqStruct(filename)
                for putFilePart in projUtils.generateDataParts(data, putFileCmd, compress):
                    fileHash = putFilePart.get('fileHash')
                    projUtils.clientSendCmd(self.commPipes, putFilePart)
            except Exception as err:
                # Send error notice to clear any partially cached data on the server side
                # Add fileHash to message and send status=400 to notify
                if fileHash:
                    putFileCmd['fileHash'] = fileHash
                    putFileCmd['status'] = 400
                    projUtils.clientSendCmd(self.commPipes, putFileCmd)
                raise err
        return

    def listFiles(self, filePattern):
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
            listCmd = projUtils.listFilesReqStruct(filePattern)
            retVals = projUtils.clientSendCmd(self.commPipes, listCmd)
            fileList = retVals.get('fileList')
            if type(fileList) is not list:
                errStr = "Invalid fileList reponse type {}: expecting list".format(type(fileList))
                raise StateError(errStr)
        return fileList

    def allowedFileTypes(self):
        if self.local:
            return ['*']
        else:
            cmd = projUtils.allowedFileTypesReqStruct()
            retVals = projUtils.clientSendCmd(self.commPipes, cmd)
            fileTypes = retVals.get('fileTypes')
            if type(fileTypes) is not list:
                errStr = "Invalid fileTypes reponse type {}: expecting list".format(type(fileTypes))
                raise StateError(errStr)
        return fileTypes
