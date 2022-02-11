import pytest
import os
import time
import projects.dicomBidsStream.dicomBidsStream as dicomBidsStream
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface
from tests.common import rtCloudPath

# We use Dicoms from the sample project as input
test_sampleProjectPath = os.path.join(rtCloudPath, 'projects', 'sample')
test_sampleProjectDicomPath = os.path.join(test_sampleProjectPath,
    'dicomDir', '20190219.0219191_faceMatching.0219191_faceMatching')

# leaving '/tmp' as an allowed directory because the sample.py project currently uses '/tmp'
allowedDirs =  ['/tmp', test_sampleProjectPath]
allowedFileTypes = ['.dcm', '.txt']

class TestDicomBidsStreamProject:
    serversForTests = None
    pingCount = 0

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    def test_runWithDataLocal(self):
        print("\nDicomBidsStreamProject::test_runWithDataLocal")
        TestDicomBidsStreamProject.serversForTests.stopServers()
        TestDicomBidsStreamProject.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=False)
        client = ClientInterface()
        assert client.isDataRemote() == False
        argv = ['--noVerbose']
        ret = dicomBidsStream.main(argv)
        assert ret == 0

    def test_runWithDataRemote(self):
        print("\nDicomBidsStreamProject::test_runWithDataRemote")
        TestDicomBidsStreamProject.serversForTests.stopServers()
        TestDicomBidsStreamProject.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=True)
        client = ClientInterface()
        assert client.isDataRemote() == True
        argv = ['--noVerbose']
        ret = dicomBidsStream.main(argv)
        assert ret == 0

    def test_runWithoutProjectInterface(self):
        print("\nDicomBidsStreamProject::test_runWithoutProjectInterface:")
        TestDicomBidsStreamProject.serversForTests.stopServers()
        time.sleep(0.1)
        argv = ['-y']
        ret = dicomBidsStream.main(argv)
        assert ret == 0
