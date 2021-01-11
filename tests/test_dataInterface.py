import pytest
import os
import copy
from rtCommon.clientInterface import ClientInterface
from rtCommon.dataInterface import DataInterface
from rtCommon.imageHandling import readDicomFromBuffer
from rtCommon.errors import ValidationError, RequestError
from tests.serversForTesting import ServersForTesting

# Note these tests will test the local version of DataInterface (not remote)

testDir = os.path.dirname(__file__)
tmpDir = os.path.join(testDir, 'tmp/')
rootDir = os.path.dirname(testDir)

sampleProjectDicomDir = os.path.join(rootDir, 
    "projects/sample/dicomDir/20190219.0219191_faceMatching.0219191_faceMatching/")

allowedDirs = ['/tmp', testDir, sampleProjectDicomDir]
allowedFileTypes = ['.bin', '.txt', '.dcm']

@pytest.fixture(scope="module")
def dicomTestFilename():  # type: ignore
    return os.path.join(testDir, 'test_input/001_000013_000005.dcm')


class TestDataInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = ServersForTesting()
        cls.serversForTests.startServers(allowedDirs, allowedFileTypes)

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    # Local dataInterface test
    def test_localDataInterface(self, dicomTestFilename):
        """Test DataInterface when instantiated in local mode"""
        dataInterface = DataInterface(dataremote=False,
                                      allowedDirs=allowedDirs,
                                      allowedFileTypes=allowedFileTypes)
        runDataInterfaceMethodTests(dataInterface, dicomTestFilename, isRemote=False)
        return

    # Remote dataInterface test
    def test_remoteDataInterface(self, dicomTestFilename):
        # Use a remote (RPC) client to the dataInterface
        clientInterface = ClientInterface()
        dataInterface = clientInterface.dataInterface
        runDataInterfaceMethodTests(dataInterface, dicomTestFilename, isRemote=True)


def runDataInterfaceMethodTests(dataInterface, dicomTestFilename, isRemote=False):
    with open(dicomTestFilename, 'rb') as fp:
        data1 = fp.read()

    # Test getFile
    print('test getFile')
    data2 = dataInterface.getFile(dicomTestFilename)
    assert data1 == data2, 'getFile data assertion'

    # Test getNewestFile
    print('test getNewestFile')
    filePattern = os.path.splitext(dicomTestFilename)[0] + '*'
    data3 = dataInterface.getNewestFile(filePattern)
    assert data1 == data3, 'getNewestFile data assertion'

    # Test watch file
    print('test watchFile')
    watchDir = os.path.join(testDir, 'test_input')
    dataInterface.initWatch(watchDir, filePattern, 0)
    data4 = dataInterface.watchFile(dicomTestFilename, timeout=5)
    assert data1 == data4, 'watchFile data assertion'

    # Test put text file
    print('test putTextFile')
    text = 'hello world'
    textFilename = os.path.join(tmpDir, 'test1.txt')
    dataInterface.putFile(textFilename, text)
    with open(textFilename, 'r') as fp:
        text1 = fp.read()
    assert text1 == text, 'putTextFile assertion'

    # Test put binary file
    print('test putBinaryFile')
    data = b'\xAB\xCD\xFE\xED\x01\x23\x45\x67'
    binFilename = os.path.join(tmpDir, 'test1.bin')
    dataInterface.putFile(binFilename, data)
    # read back data and compare to original
    with open(binFilename, 'rb') as fp:
        data1 = fp.read()
    assert data1 == data, 'putBinaryFile assertion'

    # Test list files
    filePattern = os.path.join(tmpDir, 'test1*')
    fileList = dataInterface.listFiles(filePattern)
    assert len(fileList) == 2

    # Test allowedFileTypes
    _allowedTypes = dataInterface.getAllowedFileTypes()
    # in the remote case the returned value is an rpyc netref
    #   so we need to make a local copy to do the comparison
    _allowedTypes = copy.copy(_allowedTypes)
    assert _allowedTypes == allowedFileTypes

    # Test initScannerStream and getImageData
    streamId = dataInterface.initScannerStream(sampleProjectDicomDir,
                                               "001_000013_{TR:06d}.dcm",
                                               300*1024)
    for i in range(10):
        streamImage = dataInterface.getImageData(streamId)
        directPath = os.path.join(sampleProjectDicomDir, "001_000013_{TR:06d}.dcm".format(TR=i))
        directImageData = dataInterface.getFile(directPath)
        directImage = readDicomFromBuffer(directImageData)
        print(f"Stream sequential check: image {i}")
        assert streamImage == directImage

    for i in [5,2,7]:
        streamImage = dataInterface.getImageData(streamId, i)
        directPath = os.path.join(sampleProjectDicomDir, "001_000013_{TR:06d}.dcm".format(TR=i))
        directImageData = dataInterface.getFile(directPath)
        directImage = readDicomFromBuffer(directImageData)
        print(f"Stream seek check: image {i}")
        assert streamImage == directImage

    if isRemote is False:
        # Test _checkAllowedFileTypes
        print("Test files validations")
        assert dataInterface._checkAllowedDirs('/tmp') == True
        assert dataInterface._checkAllowedDirs('/tmp/t1') == True
        assert dataInterface._checkAllowedDirs(testDir) == True
        assert dataInterface._checkAllowedDirs(testDir + '//t2/') == True
        assert dataInterface._checkAllowedDirs(sampleProjectDicomDir) == True
        assert dataInterface._checkAllowedDirs(sampleProjectDicomDir + '//t2') == True
        with pytest.raises(ValidationError):
            dataInterface._checkAllowedDirs('/data/')

        assert dataInterface._checkAllowedFileTypes('test.dcm') == True
        assert dataInterface._checkAllowedFileTypes('test.bin') == True
        assert dataInterface._checkAllowedFileTypes('test.txt') == True
        with pytest.raises(ValidationError):
            dataInterface._checkAllowedFileTypes('test.nope') == False

        # Test _filterFileList
        inputList = ['test.txt', 'test.nope', 'file.bin', 'data.db']
        expectedList = ['test.txt', 'file.bin']
        outList = dataInterface._filterFileList(inputList)
        assert outList == expectedList

    return
