import os
import sys
import threading
import time
# sys.path.append(rootPath)
from rtCommon.structDict import StructDict
from rtCommon.scannerDataService import ScannerDataService
from rtCommon.projectServer import ProjectServer

testDir = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(testDir))
samplePath = os.path.join(rootPath,'projects/sample')

fileTypeList = ['.dcm', '.mat', '.bin', '.txt']

class ServersForTesting:
    def __init__(self):
        self.projectServer = None
        self.dataServer = None
        self.subjectServer = None
        self.projectThread = None
        self.dataThread = None
        self.subjectThread = None

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
        self.projectServer = ProjectServer(args)
        self.projectThread = threading.Thread(name='mainThread', target=self.projectServer.start)
        self.projectThread.setDaemon(True)
        self.projectThread.start()
        time.sleep(.1)

        # Start the dataService running
        args = StructDict({'server': 'localhost:8921',
                           'interval': 0.1,
                           'allowedDirs': allowedDirs,
                           'allowedFileTypes': allowedFileTypes,
                           'username': 'test',
                           'password': 'test',
                           'test': True,
                          })
        self.dataServer = ScannerDataService(args)
        # Start dataSerivce running in a thread
        self.dataThread = threading.Thread(
            name='dataThread',
            target=self.dataServer.wsRemoteService.runForever
        )
        self.dataThread.setDaemon(True)
        self.dataThread.start()
        time.sleep(.1)

        while self.projectServer.started is False:
            time.sleep(.1)
        return True

    def stopServers(self):
        # TODO: implement stopServers
        pass