import os
import time
import platform
import tempfile
import threading
import multiprocessing
# sys.path.append(rootPath)
from rtCommon.structDict import StructDict
from rtCommon.scannerDataService import ScannerDataService
from rtCommon.subjectService import SubjectService
from rtCommon.exampleService import ExampleService
from rtCommon.projectServer import ProjectServer
from tests.common import testPort, testPath, tmpDir


defaultAllowedDirs = [testPath, tmpDir]
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


def runExampleService(args, isStartedEvent):
    exampleServer = ExampleService(args)
    exampleThread = threading.Thread(
        name='exampleThread',
        target=exampleServer.wsRemoteService.runForever
    )
    exampleThread.start()
    while exampleServer.wsRemoteService.started is False:
        time.sleep(.1)
    isStartedEvent.set()


defaultCfg = StructDict({'sessionId': "test",
                         'subjectName': "test_sample",
                         'subjectNum': 1,
                         'subjectDay': 1,
                         'sessionNum': 1})

defaultProjectArgs = StructDict({'config': defaultCfg,
                                 'mainScript': 'projects/sample/sample.py',
                                 'port': testPort,
                                 'test': True})

class BackgroundTestServers:
    def __init__(self):
        self.projectProc = None
        self.dataProc = None
        self.subjectProc = None
        self.exampleProc = None
        if platform.system() == "Darwin":
            try:
                # Prior to Python 3.8, 'fork' was the default on MacOS,
                #  but it could lead to crashes of some subprocesses.
                multiprocessing.set_start_method('spawn')
            except Exception as err:
                print(f'multiprocess err: {err}')

    def startServers(self,
                     allowedDirs=defaultAllowedDirs,
                     allowedFileTypes=defaultAllowedFileTypes,
                     dataRemote=True, subjectRemote=True, exampleRemote=False,
                     projectArgs=defaultProjectArgs):
        if exampleRemote is True:
            # example remote uses the wsData websocket channel
            dataRemote = True

        projectArgs['dataRemote'] = dataRemote
        projectArgs['subjectRemote'] = subjectRemote

        # Start the projectServer running
        isRunningEvent = multiprocessing.Event()
        self.projectProc = multiprocessing.Process(target=runProjectServer, args=(projectArgs, isRunningEvent))
        self.projectProc.start()
        isRunningEvent.wait()

        if dataRemote is True:
            # Start the dataService running
            args = StructDict({'server': f'localhost:{testPort}',
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
            args = StructDict({'server': f'localhost:{testPort}',
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

        if exampleRemote is True:
            # Start the exampleService running
            args = StructDict({'server': f'localhost:{testPort}',
                               'interval': 0.1,
                               'username': 'test',
                               'password': 'test',
                               'test': True,
                               })
            isRunningEvent = multiprocessing.Event()
            self.exampleProc = multiprocessing.Process(target=runExampleService, args=(args, isRunningEvent))
            self.exampleProc.start()
            isRunningEvent.wait()
            # time.sleep(5)
        else:
            self.exampleProc = None

        return True

    def stopServers(self):
        if self.projectProc is not None:
            self.projectProc.kill()
            self.projectProc.join()
            self.projectProc = None
        if self.dataProc is not None:
            self.dataProc.kill()
            self.dataProc.join()
            self.dataProc = None
        if self.subjectProc is not None:
            self.subjectProc.kill()
            self.subjectProc.join()
            self.subjectProc = None
        if self.exampleProc is not None:
            self.exampleProc.kill()
            self.exampleProc.join()
            self.exampleProc = None
