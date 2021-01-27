import pytest
import os
import time
import projects.sample.sample as sample
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface

testDir = os.path.dirname(__file__)
rootPath = os.path.dirname(testDir)
samplePath = os.path.join(rootPath,'projects/sample')
tmpDir = os.path.join(testDir, 'tmp/')

allowedDirs =  ['/tmp', samplePath]
allowedFileTypes = ['.dcm', '.txt']

class TestSampleProject:
    serversForTests = None
    pingCount = 0

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    def test_runWithDataLocal(self):
        print("\nSampleProject::test_runWithDataLocal")
        TestSampleProject.serversForTests.stopServers()
        TestSampleProject.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=False)
        client = ClientInterface()
        assert client.isDataRemote() == False
        argv = ['--noVerbose']
        ret = sample.main(argv)
        assert ret == 0

    def test_runWithDataRemote(self):
        print("\nSampleProject::test_runWithDataRemote")
        TestSampleProject.serversForTests.stopServers()
        TestSampleProject.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=True)
        client = ClientInterface()
        assert client.isDataRemote() == True
        argv = ['--noVerbose']
        ret = sample.main(argv)
        assert ret == 0

    def test_runWithInitWatch(self):
        print("\nSampleProject::test_runWithDataRemote")
        TestSampleProject.serversForTests.stopServers()
        TestSampleProject.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=True)
        client = ClientInterface()
        assert client.isDataRemote() == True
        argv = ['--useInitWatch', '--noVerbose']
        ret = sample.main(argv)
        assert ret == 0

    def test_runWithoutProjectInterface(self):
        print("\nSampleProject::test_runWithoutProjectInterface:")
        TestSampleProject.serversForTests.stopServers()
        time.sleep(0.1)
        argv = ['-y']
        ret = sample.main(argv)
        assert ret == 0
