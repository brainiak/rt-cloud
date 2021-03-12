import pytest
import os
import copy
import time
import shutil
from rtCommon.clientInterface import ClientInterface
from rtCommon.dataInterface import DataInterface, uploadFilesToCloud, downloadFilesFromCloud
from rtCommon.imageHandling import readDicomFromBuffer
from rtCommon.errors import ValidationError, RequestError
import rtCommon.utils as utils
from tests.backgroundTestServers import BackgroundTestServers
from tests.common import rtCloudPath, test_dicomPath, testPath, tmpDir

# Note these tests will test the local version of DataInterface (not remote)

sampleProjectDicomDir = os.path.join(rtCloudPath, 'projects', 'sample',
    'dicomDir', '20190219.0219191_faceMatching.0219191_faceMatching')

allowedDirs = [tmpDir, testPath, sampleProjectDicomDir, '/tmp']
allowedFileTypes = ['.bin', 'txt', '.dcm']

@pytest.fixture(scope="module")
def dicomTestFilename():  # type: ignore
    return test_dicomPath

@pytest.fixture(scope="module")
def bigTestFile():  # type: ignore
    filename = os.path.join(testPath, 'test_input', 'bigfile.bin')
    if not os.path.exists(filename):
        with open(filename, 'wb') as fout:
            for _ in range(101):
                fout.write(os.urandom(1024*1024))
    return filename


class TestDataInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()


    def teardown_class(cls):
        cls.serversForTests.stopServers()

    # Local dataInterface test
    def test_localDataInterface(self, dicomTestFilename, bigTestFile):
        """Test DataInterface when instantiated in local mode"""
        dataInterface = DataInterface(dataRemote=False,
                                      allowedDirs=allowedDirs,
                                      allowedFileTypes=allowedFileTypes)
        runDataInterfaceMethodTests(dataInterface, dicomTestFilename)
        runLocalFileValidationTests(dataInterface)
        runReadWriteFileTest(dataInterface, bigTestFile)
        return

    # Remote dataInterface test
    def test_rpyclocalDataInterface(self, dicomTestFilename, bigTestFile):
        # Use a remote (RPC) client to the dataInterface
        TestDataInterface.serversForTests.stopServers()
        TestDataInterface.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=False,
                                                       subjectRemote=False)
        clientInterface = ClientInterface()
        dataInterface = clientInterface.dataInterface
        assert clientInterface.isDataRemote() == False
        assert dataInterface.isRemote == False
        runDataInterfaceMethodTests(dataInterface, dicomTestFilename)
        runReadWriteFileTest(dataInterface, bigTestFile)
        return

    # Remote dataInterface test
    def test_remoteDataInterface(self, dicomTestFilename, bigTestFile):
        # Use a remote (RPC) client to the dataInterface
        TestDataInterface.serversForTests.stopServers()
        TestDataInterface.serversForTests.startServers(allowedDirs=allowedDirs,
                                                       allowedFileTypes=allowedFileTypes,
                                                       dataRemote=True,
                                                       subjectRemote=False)
        clientInterface = ClientInterface()
        dataInterface = clientInterface.dataInterface
        assert clientInterface.isDataRemote() == True
        assert dataInterface.isRemote == True
        runDataInterfaceMethodTests(dataInterface, dicomTestFilename)
        runRemoteFileValidationTests(dataInterface)
        runUploadDownloadTest(dataInterface)
        runReadWriteFileTest(dataInterface, bigTestFile)
        return


def runReadWriteFileTest(dataInterface, testFileName):
    with open(testFileName, 'rb') as fp:
        data = fp.read()

    # Test getFile
    print('test getFile')
    startTime = time.time()
    responseData = dataInterface.getFile(testFileName)
    print('GetFile {} time: {}'.format(testFileName, (time.time() - startTime)))
    assert responseData == data, 'getFile assertion'

    # Test put file
    outfileName = os.path.join(tmpDir, testFileName)
    extraArgs = {}
    if dataInterface.isRunningRemote():
        extraArgs = {'rpc_timeout': 60}
    startTime = time.time()
    dataInterface.putFile(outfileName, data, **extraArgs)
    print('PutFile {} time: {}'.format(outfileName, (time.time() - startTime)))
    # read back data and compare to original
    with open(outfileName, 'rb') as fp:
        data1 = fp.read()
    assert data1 == data, 'putFile assertion'


def runDataInterfaceMethodTests(dataInterface, dicomTestFilename):
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
    watchDir = os.path.join(testPath, 'test_input')
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

def runRemoteFileValidationTests(dataInterface):
    # Tests for remote dataInterface
    assert dataInterface.isRunningRemote() == True

    # Try get of non-allowed file type
    print('test get from non-allowed file type')
    with pytest.raises((ValidationError, RequestError, Exception)) as err:
        nodata = dataInterface.getFile(os.path.join(testPath, 'test_utils.py'))
        # assert nodata == None, 'get non-allowed file'
    # import pdb; pdb.set_trace()
    # print(f'## ERROR {err}')

    # Try get from non-allowed directory
    print('test get from non-allowed directory')
    with pytest.raises((ValidationError, RequestError, Exception)) as err:
        nodata = dataInterface.getFile(os.path.join(rtCloudPath, 'environment.yml'))
        assert nodata == None, 'get non-allowed dir'
    # print(f'## ERROR {err}')

    # Test watch non-allowed directory
    filePattern = '*.dcm'
    with pytest.raises((ValidationError, RequestError, Exception)) as err:
        watchDir = os.path.join(rtCloudPath, 'certs')
        dataInterface.initWatch(watchDir, filePattern, 0)
    # print(f'## ERROR {err}')

    # Test allowedFileTypes
    _allowedTypes = dataInterface.getAllowedFileTypes()
    # in the remote case the returned value is an rpyc netref
    #   so we need to make a local copy to do the comparison
    _allowedTypes = copy.copy(_allowedTypes)
    assert _allowedTypes == allowedFileTypes


def runLocalFileValidationTests(dataInterface):
    # Test _checkAllowedFileTypes
    print("Test files validations")
    assert dataInterface._checkAllowedDirs('/tmp') == True
    assert dataInterface._checkAllowedDirs('/tmp/t1') == True
    assert dataInterface._checkAllowedDirs(testPath) == True
    assert dataInterface._checkAllowedDirs(testPath + '//t2/') == True
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


def runUploadDownloadTest(dataInterface):
    # test downloadFilesFromCloud and uploadFilesToCloud
    assert dataInterface.isRunningRemote() is True
    # 0. remove any previous test directories
    shutil.rmtree('/tmp/d2', ignore_errors=True)
    shutil.rmtree('/tmp/d3', ignore_errors=True)
    # 1. create a tmp sub-dir with some files in it
    text1 = 'test file 1'
    text2 = 'test file 2'
    bindata1 = b'\xFE\xED\x01\x23'
    bindata2 = b'\xAA\xBB\xCC\xDD'
    utils.writeFile('/tmp/d1/test1.txt', text1, binary=False)
    utils.writeFile('/tmp/d1/test2.txt', text2, binary=False)
    utils.writeFile('/tmp/d1/test3.bin', bindata1)
    utils.writeFile('/tmp/d1/test4.bin', bindata2)
    # 2. download files from cloud
    downloadFilesFromCloud(dataInterface, '/tmp/d1/test*.txt', '/tmp/d2')
    downloadFilesFromCloud(dataInterface, '/tmp/d1/test*.bin', '/tmp/d2')
    # 3. upload files to cloud
    uploadFilesToCloud(dataInterface, '/tmp/d2/test*.txt', '/tmp/d3')
    uploadFilesToCloud(dataInterface, '/tmp/d2/test*.bin', '/tmp/d3')
    # check that all files in d1 are same as files in d3
    d3text1 = utils.readFile('/tmp/d3/test1.txt', binary=False)
    d3text2 = utils.readFile('/tmp/d3/test2.txt', binary=False)
    d3bin1 = utils.readFile('/tmp/d3/test3.bin')
    d3bin2 = utils.readFile('/tmp/d3/test4.bin')
    assert d3text1 == text1
    assert d3text2 == text2
    assert d3bin1 == bindata1
    assert d3bin2 == bindata2