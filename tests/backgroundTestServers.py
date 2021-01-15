import os
import time
import platform
import threading
import multiprocessing
# sys.path.append(rootPath)
from rtCommon.structDict import StructDict
from rtCommon.scannerDataService import ScannerDataService
from rtCommon.subjectService import SubjectService
from rtCommon.projectServer import ProjectServer

testDir = os.path.dirname(__file__)
tmpDir = os.path.join(testDir, 'tmp/')

defaultAllowedDirs = [testDir, tmpDir]
defaultAllowedFileTypes = ['*.dcm', '*.txt', '*.bin']


def runProjectServer(args, isStartedEvent):
    projectServer = ProjectServer(args)
    projThread = threading.Thread(name='mainThread', target=projectServer.start)
    projThread.start()
    while projectServer.started is False:
        time.sleep(.1)
    isStartedEvent.set()


def runDataService(args, isStartedEvent):
    dataServer = ScannerDataService(args)
    dataThread = threading.Thread(
        name='dataThread',
        target=dataServer.wsRemoteService.runForever
    )
    dataThread.start()
    while dataServer.wsRemoteService.started is False:
        time.sleep(.1)
    isStartedEvent.set()


def runSubjectService(args, isStartedEvent):
    subjectService = SubjectService(args)
    subjThread = threading.Thread(
        name='subjThread',
        target=subjectService.wsRemoteService.runForever
    )
    subjThread.start()
    while subjectService.wsRemoteService.started is False:
        time.sleep(.1)
    isStartedEvent.set()


class BackgroundTestServers:
    def __init__(self):
        self.projectProc = None
        self.dataProc = None
        self.subjectProc = None
        if platform.system() == "Darwin":
            try:
                multiprocessing.set_start_method('spawn')
            except Exception as err:
                print(f'multiprocess err: {err}')

    def startServers(self,
                     allowedDirs=defaultAllowedDirs,
                     allowedFileTypes=defaultAllowedFileTypes,
                     dataRemote=True, subjectRemote=True):
        # Start the projectServer running
        cfg = StructDict({'sessionId': "test",
                          'subjectName': "test_sample",
                          'subjectNum': 1,
                          'subjectDay': 1,
                          'sessionNum': 1})
        args = StructDict({'config': cfg,
                           'mainScript': 'projects/sample/sample.py',
                           'dataRemote': dataRemote,
                           'subjectRemote': subjectRemote,
                           'port': 8921, 
                           'test': True})
        isRunningEvent = multiprocessing.Event()
        self.projectProc = multiprocessing.Process(target=runProjectServer, args=(args, isRunningEvent))
        self.projectProc.start()
        isRunningEvent.wait()

        if dataRemote is True:
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
            self.dataProc = multiprocessing.Process(target=runDataService, args=(args, isRunningEvent))
            self.dataProc.start()
            isRunningEvent.wait()
        else:
            self.dataProc = None

        if subjectRemote is True:
            # Start the subjectService running
            args = StructDict({'server': 'localhost:8921',
                               'interval': 0.1,
                               'username': 'test',
                               'password': 'test',
                               'test': True,
                               })
            isRunningEvent = multiprocessing.Event()
            self.subjectProc = multiprocessing.Process(target=runSubjectService, args=(args, isRunningEvent))
            self.subjectProc.start()
            isRunningEvent.wait()
            # time.sleep(5)
        else:
            self.subjectProc = None

        return True

    def stopServers(self):
        if self.projectProc is not None:
            self.projectProc.kill()
            self.projectProc = None
        if self.dataProc is not None:
            self.dataProc.kill()
            self.dataProc = None
        if self.subjectProc is not None:
            self.subjectProc.kill()
            self.subjectProc = None
