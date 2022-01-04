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

    def test_ds000005(self):
        # Tests subject name starts with a zero, so must be kept as a string not int
        print("\nOpenNeuroClient::test_ds000005")
        cfg = StructDict({'sessionId': "openNeuroTest",
                          'dsAccessionNumber': 'ds000005',
                          'subjectName': "07",
                          'subjectDay': 1,
                          'runNum': ['01'],
                          'scanNum': [1]})
        args = StructDict({'config': cfg,
                           'mainScript': openNeuroClientPath,
                           'port': testPort,
                           'test': True})
        TestOpenNeuroClient.serversForTests.stopServers()
        TestOpenNeuroClient.serversForTests.startServers(allowedDirs=allowedDirs,
                                                         allowedFileTypes=allowedFileTypes,
                                                         dataRemote=False,
                                                         projectArgs=args)
        client = ClientInterface()
        assert client.isDataRemote() == False
        argv = ['--archive']
        ret = openNeuroClient.main(argv)
        assert ret == 0

    def test_ds003772(self):
        # Tests run name has no leading zero
        print("\nOpenNeuroClient::test_ds003772")
        cfg = StructDict({'sessionId': "openNeuroTest",
                          'dsAccessionNumber': 'ds003772',
                          'subjectName': "bb914",
                          'subjectDay': 1,
                          'runNum': [1],
                          'scanNum': [1]})
        args = StructDict({'config': cfg,
                           'mainScript': openNeuroClientPath,
                           'port': testPort,
                           'test': True})
        TestOpenNeuroClient.serversForTests.stopServers()
        TestOpenNeuroClient.serversForTests.startServers(allowedDirs=allowedDirs,
                                                         allowedFileTypes=allowedFileTypes,
                                                         dataRemote=False,
                                                         projectArgs=args)
        client = ClientInterface()
        assert client.isDataRemote() == False
        argv = ['--archive']
        ret = openNeuroClient.main(argv)
        assert ret == 0
