import os
from rtCommon.errors import StateError
import threading
import random
import time
import pytest

import rtCommon.fileWatcher as fileWatcher
from tests.common import tmpDir, rtCloudPath

test_sampleProjectPath = os.path.join(rtCloudPath, 'projects', 'sample')
test_sampleProjectDicomPath = os.path.join(test_sampleProjectPath,
    'dicomDir', '20190219.0219191_faceMatching.0219191_faceMatching')
watchTmpPath = os.path.join(tmpDir, 'filewatcher')
rndTimeouts = [random.random()*2 for i in range(10)]
# rndTimeouts = [.05, .05, .05, .05, .05, .05, .05, .05, .05, .05]
exitThread = False


def copyFilesThread(numFiles=10):
    global exitThread, watchTmpPath, rndTimeouts
    print(f'numfiles {numFiles}')
    for i in range(numFiles):
        if exitThread:
            return
        # sleepTime = random.random() * 2  # random number from 0 to 2 seconds
        time.sleep(rndTimeouts[i])
        dicomName = os.path.join(test_sampleProjectDicomPath, f'001_000013_00000{i}.dcm')
        print(f'copying {dicomName}')
        os.system(f'cp {dicomName} {watchTmpPath}')


def clearWatchDir():
    global watchTmpPath
    if os.path.exists(watchTmpPath):
        os.system(f'rm {watchTmpPath}/*.dcm')
    else:
        os.makedirs(watchTmpPath, exist_ok=True)


def startCopyThread(numFiles=10):
     # start a thread that will copy a image over every 0-2 seconds
    global exitThread
    exitThread = False
    copyThread = threading.Thread(name='copyThread', target=copyFilesThread, kwargs={'numFiles': numFiles})
    copyThread.setDaemon(True)
    copyThread.start()
    return copyThread


def test_waitForFile():
    global exitThread, watchTmpPath, rndTimeouts

    clearWatchDir()

    watcher = fileWatcher.FileWatcher()
    watcher.initFileNotifier(watchTmpPath, '*.dcm', 300000)

    copyThread = startCopyThread()
    try:
        # call waitForFile
        for i in range(10):
            dicomName = f'001_000013_00000{i}.dcm'
            tout = rndTimeouts[i] + 0.1
            result = watcher.waitForFile(dicomName, timeout=tout, timeCheckIncrement=0.5)
            print(f'Got {result}')
            # assert filename match
            assert result == os.path.join(watchTmpPath, dicomName)
            # assert file found by event trigger
            assert watcher.foundWithFileEvent == True or watcher.waitLoopCount == 0
    finally:
        exitThread = True
        copyThread.join()


def test_waitForFile_noEvents():
    # Init a file watcher on the wrong pattern
    #  so that only checkFileTimeouts will find the file
    global exitThread, watchTmpPath, rndTimeouts

    clearWatchDir()

    wrongFilePattern = '*.dcm2'
    watcher = fileWatcher.FileWatcher()
    watcher.initFileNotifier(watchTmpPath, wrongFilePattern, 300000)

    copyThread = startCopyThread()
    try:
        # call waitForFile
        for i in range(10):
            dicomName = f'001_000013_00000{i}.dcm'
            tout = rndTimeouts[i] + 0.5
            result = watcher.waitForFile(dicomName, timeout=tout, timeCheckIncrement=0.5)
            print(f'Got {result}')
            assert result == os.path.join(watchTmpPath, dicomName)
            assert watcher.foundWithFileEvent == False
    finally:
        exitThread = True
        copyThread.join()


def test_waitForFile_wrongDir():
     # Init a file watcher on the wrong directory, 
     #  the filewatch should time out and fail
    global exitThread, watchTmpPath, rndTimeouts

    clearWatchDir()

    watcher = fileWatcher.FileWatcher()
    wrongPath = os.path.join(watchTmpPath, 'nodir')
    os.makedirs(wrongPath, exist_ok=True)
    watcher.initFileNotifier(wrongPath, '*.dcm', 300000)

    # Calling waitForFile on a path different from the initFileNotifier path should fail
    fullName = os.path.join(watchTmpPath, '001_000013_000001.dcm')
    with pytest.raises(StateError):
        result = watcher.waitForFile(fullName, timeout=2, timeCheckIncrement=0.5)

    numFiles = 2
    copyThread = startCopyThread(numFiles)
    try:
        # No files should be found since the watch path
        #  is a different directory from copy path
        for i in range(numFiles):
            dicomName = f'001_000013_00000{i}.dcm'
            tout = rndTimeouts[i] + 0.5
            result = watcher.waitForFile(dicomName, timeout=tout, timeCheckIncrement=0.5)
            print(f'Got {result}')
            assert result == None
            assert watcher.foundWithFileEvent == False
    finally:
        exitThread = True
        copyThread.join()