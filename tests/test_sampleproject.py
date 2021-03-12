import pytest
import os
import time
import projects.sample.sample as sample
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface
from tests.common import rtCloudPath

test_sampleProjectPath = os.path.join(rtCloudPath, 'projects', 'sample')
test_sampleProjectDicomPath = os.path.join(test_sampleProjectPath,
    'dicomDir', '20190219.0219191_faceMatching.0219191_faceMatching')

# leaving '/tmp' as an allowed directory because the sample.py project currently uses '/tmp'
allowedDirs =  ['/tmp', test_sampleProjectPath]
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
