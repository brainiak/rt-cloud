import os
import time
import platform
import threading
import multiprocessing
# sys.path.append(rootPath)
from rtCommon.structDict import StructDict
from rtCommon.scannerDataService import ScannerDataService
from rtCommon.projectServer import ProjectServer

testDir = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(testDir))
samplePath = os.path.join(rootPath,'projects/sample')

fileTypeList = ['.dcm', '.mat', '.bin', '.txt']


def runProjectServer(args, isStartedEvent):
    projectServer = ProjectServer(args)
    projThread = threading.Thread(name='mainThread', target=projectServer.start)
    projThread.start()
    while projectServer.started is False:
        time.sleep(.1)
    isStartedEvent.set()


def runDataServer(args, isStartedEvent):
    dataServer = ScannerDataService(args)
    dataThread = threading.Thread(
        name='dataThread',
        target=dataServer.wsRemoteService.runForever
    )
    dataThread.start()
    while dataServer.wsRemoteService.started is False:
        time.sleep(.1)
    isStartedEvent.set()


class ServersForTesting:
    def __init__(self):
        self.projectServer = None
        self.dataServer = None
        self.subjectServer = None
        self.projectProc = None
        self.dataProc = None
        self.subjectProc = None
        if platform.system() == "Darwin":
            try:
                multiprocessing.set_start_method('spawn')
            except Exception as err:
                print(f'multiprocess err: {err}')

    def startServers(self, allowedDirs, allowedFileTypes):
        global testDir, samplePath, fileTypeList
        # Start the projectServer running
        cfg = StructDict({'sessionId': "test",
                          'subjectName': "test_sample",
                          'subjectNum': 1,
                          'subjectDay': 1,
                          'sessionNum': 1})
        args = StructDict({'config': cfg,
                           'mainScript': 'projects/sample/sample.py',
                           'dataremote': True,
                           'port': 8921, 
                           'test': True})
        isRunningEvent = multiprocessing.Event()
        self.projectProc = multiprocessing.Process(target=runProjectServer, args=(args, isRunningEvent))
        self.projectProc.start()
        isRunningEvent.wait()

        # Start the dataService running
        args = StructDict({'server': 'localhost:8921',
                           'interval': 0.1,
                           'allowedDirs': allowedDirs,
                           'allowedFileTypes': allowedFileTypes,
                           'username': 'test',
                           'password': 'test',
                           'test': True,
                          })
        isRunningEvent = multiprocessing.Event()
        self.dataProc = multiprocessing.Process(target=runDataServer, args=(args, isRunningEvent))
        self.dataProc.start()
        isRunningEvent.wait()

        return True

    def stopServers(self):
        self.projectProc.kill()
        self.dataProc.kill()
