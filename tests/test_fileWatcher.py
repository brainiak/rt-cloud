import os
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
exitThread = False


def copyFilesThread():
    global exitThread, watchTmpPath, rndTimeouts
    for i in range(10):
        if exitThread:
            return
        # sleepTime = random.random() * 2  # random number from 0 to 2 seconds
        time.sleep(rndTimeouts[i])
        dicomName = os.path.join(test_sampleProjectDicomPath, f'001_000013_00000{i}.dcm')
        print(f'copying {dicomName}')
        os.system(f'cp {dicomName} {watchTmpPath}')

def test_waitForFile():
    global exitThread, watchTmpPath, rndTimeouts
    # start a filewatcher on a tmp directory
    if os.path.exists(watchTmpPath):
        os.system(f'rm {watchTmpPath}/*.dcm')
    else:
        os.makedirs(watchTmpPath, exist_ok=True)
    watcher = fileWatcher.FileWatcher()
    watcher.initFileNotifier(watchTmpPath, '*.dcm', 300000)

    # start a thread that will copy a image over every 1 second
    copyThread = threading.Thread(name='copyThread', target=copyFilesThread)
    copyThread.setDaemon(True)
    copyThread.start()

    try:
        # call waitForFile
        for i in range(10):
            dicomName = f'001_000013_00000{i}.dcm'
            tout = rndTimeouts[i] + 0.1
            result = watcher.waitForFile(dicomName, timeout=tout, timeCheckIncrement=0.5)
            assert result == os.path.join(watchTmpPath, dicomName)
    finally:
        exitThread = True
        copyThread.join()
