import os
from rtCommon.fileWatcher import FileWatcher
from rtCommon.utils import findNewestFile
import rtCommon.webClientUtils as wcutils
from rtCommon.errors import RequestError, StateError


class FileInterface:
    def __init__(self, filesremote=False, webpipes=None):
        self.local = not filesremote
        self.webpipes = webpipes
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
            getFileCmd = wcutils.getFileReqStruct(filename)
            retVals = wcutils.clientWebpipeCmd(self.webpipes, getFileCmd)
            if retVals.statusCode != 200:
                raise RequestError('getFile_remote: statusCode not 200: {}: {}'
                                   .format(retVals.statusCode, retVals.error))
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
            getNewestFileCmd = wcutils.getNewestFileReqStruct(filePattern)
            retVals = wcutils.clientWebpipeCmd(self.webpipes, getNewestFileCmd)
            if retVals.statusCode != 200:
                raise RequestError('getNewestFile_remote: statusCode not 200: {}: {}'
                                   .format(retVals.statusCode, retVals.error))
            data = retVals.data
        return data

    def initWatch(self, dir, filePattern, minFileSize, demoStep=0):
        if self.local:
            self.fileWatcher.initFileNotifier(dir, filePattern, minFileSize, demoStep)
        else:
            initWatchCmd = wcutils.initWatchReqStruct(dir, filePattern, minFileSize, demoStep)
            wcutils.clientWebpipeCmd(self.webpipes, initWatchCmd)
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
            watchCmd = wcutils.watchFileReqStruct(filename, timeout=timeout)
            retVals = wcutils.clientWebpipeCmd(self.webpipes, watchCmd)
            if retVals.statusCode != 200:
                raise RequestError('watchFile_remote: statusCode not 200: {}: {}'
                                   .format(retVals.statusCode, retVals.error))
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
            putFileCmd = wcutils.putTextFileReqStruct(filename, text)
            wcutils.clientWebpipeCmd(self.webpipes, putFileCmd)
        return

    def putBinaryFile(self, filename, data):
        if self.local:
            outputDir = os.path.dirname(filename)
            if not os.path.exists(outputDir):
                os.makedirs(outputDir)
            with open(filename, 'wb+') as binFile:
                binFile.write(data)
        else:
            putFileCmd = wcutils.putBinaryFileReqStruct(filename, data)
            wcutils.clientWebpipeCmd(self.webpipes, putFileCmd)
        return
