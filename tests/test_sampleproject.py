import pytest
import os
import projects.sample.sample as sample
from tests.serversForTesting import ServersForTesting

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
        cls.serversForTests = ServersForTesting()
        cls.serversForTests.startServers(allowedDirs, allowedFileTypes)

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    def test_runFromCommandLine(self):
        argv = []
        ret = sample.main(argv)
        assert ret == 0

