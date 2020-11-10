# Request structures for making remote calls over web sockets

# helper function for creating remote subject request
def resultStruct(runId, trId, value):
    cmd = {'cmd': 'resultValue',
           'runId': runId,
           'trId': trId,
           'value': value,
           }
    return cmd

# Set of helper functions for creating remote file requests
def getFileReqStruct(filename, compress=False):
    cmd = {'cmd': 'getFile',
           'route': 'dataserver',
           'filename': filename,
           'compress': compress}
    return cmd


def getNewestFileReqStruct(filename, compress=False):
    cmd = {'cmd': 'getNewestFile',
           'route': 'dataserver',
           'filename': filename,
           'compress': compress}
    return cmd


def listFilesReqStruct(filePattern):
    cmd = {'cmd': 'listFiles', 'route': 'dataserver', 'filename': filePattern}
    return cmd


def allowedFileTypesReqStruct():
    cmd = {'cmd': 'getAllowedFileTypes', 'route': 'dataserver'}
    return cmd


def watchFileReqStruct(filename, timeout=5, compress=False):
    cmd = {'cmd': 'watchFile',
           'route': 'dataserver',
           'filename': filename,
           'timeout': timeout,
           'compress': compress}
    return cmd


def initWatchReqStruct(dir, filePattern, minFileSize, demoStep=0):
    cmd = {
        'cmd': 'initWatch',
        'route': 'dataserver',
        'dir': dir,
        'filename': filePattern,
        'minFileSize': minFileSize
    }
    if demoStep is not None and demoStep > 0:
        cmd['demoStep'] = demoStep
    return cmd


def putTextFileReqStruct(filename, str):
    cmd = {
        'cmd': 'putTextFile',
        'route': 'dataserver',
        'filename': filename,
        'text': str,
    }
    return cmd


def putBinaryFileReqStruct(filename):
    cmd = {
        'cmd': 'putBinaryFile',
        'route': 'dataserver',
        'filename': filename,
    }
    return cmd