import pytest
import os
import time
from rtCommon.structDict import StructDict
from rtCommon.clientInterface import ClientInterface
from projects.openNeuroClient import openNeuroClient
from tests.backgroundTestServers import BackgroundTestServers
from tests.common import rtCloudPath, testPort, tmpDir

openNeuroProjectPath = os.path.join(rtCloudPath, 'projects', 'openNeuroClient')
openNeuroClientPath = os.path.join(openNeuroProjectPath, 'openNeuroClient.py')

allowedDirs =  [tmpDir, openNeuroProjectPath]
allowedFileTypes = ['.dcm', '.txt']

openNeuroCfg = StructDict({'sessionId': "openNeuroTest",
                           'dsAccessionNumber': 'ds002338',
                           'subjectName': "xp201",
                           'subjectDay': 1,
                           'runNum': [1],
                           'scanNum': [1]})


openNeuroArgs = StructDict({'config': openNeuroCfg,
                            'mainScript': openNeuroClientPath,
                            'port': testPort,
                            'test': True})

class TestOpenNeuroClient:
    serversForTests = None
    pingCount = 0

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    def test_runWithDataLocal(self):
        print("\nOpenNeuroClient::test_runWithDataLocal")
        TestOpenNeuroClient.serversForTests.stopServers()
        TestOpenNeuroClient.serversForTests.startServers(allowedDirs=allowedDirs,
                                                         allowedFileTypes=allowedFileTypes,
                                                         dataRemote=False,
                                                         projectArgs=openNeuroArgs)
        client = ClientInterface()
        assert client.isDataRemote() == False
        argv = ['--archive']
        ret = openNeuroClient.main(argv)
        assert ret == 0

    def test_runWithDataRemote(self):
        print("\nOpenNeuroClient::test_runWithDataRemote")
        TestOpenNeuroClient.serversForTests.stopServers()
        TestOpenNeuroClient.serversForTests.startServers(allowedDirs=allowedDirs,
                                                         allowedFileTypes=allowedFileTypes,
                                                         dataRemote=True,
                                                         projectArgs=openNeuroArgs)
        client = ClientInterface()
        assert client.isDataRemote() == True
        argv = ['--archive']
        ret = openNeuroClient.main(argv)
        assert ret == 0

    def test_runWithoutProjectInterface(self):
        print("\nOpenNeuroClient::test_runWithoutProjectInterface:")
        TestOpenNeuroClient.serversForTests.stopServers()
        argv = ['-y', '--archive']
        ret = openNeuroClient.main(argv)
        assert ret == 0
