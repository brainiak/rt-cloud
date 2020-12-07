import pytest
import os
from rtCommon.dataInterface import DataInterface

# Note these tests will test the local version of DataInterface (not remote)

testDir = os.path.dirname(__file__)
tmpDir = os.path.join(testDir, 'tmp/')


@pytest.fixture(scope="module")
def dicomTestFilename():  # type: ignore
    return os.path.join(testDir, 'test_input/001_000005_000100.dcm')


class TestDataInterface:
    fileWatcher = None

    def setup_class(cls):
        TestDataInterface.fileWatcher = DataInterface()

    def teardown_class(cls):
        print('teardown')
        TestDataInterface.fileWatcher = None

    def test_funcs(cls, dicomTestFilename):
        with open(dicomTestFilename, 'rb') as fp:
            data1 = fp.read()

        # Test getFile
        print('test getFile')
        data2 = TestDataInterface.fileWatcher.getFile(dicomTestFilename)
        assert data1 == data2, 'getFile data assertion'

        # Test getNewestFile
        print('test getNewestFile')
        filePattern = os.path.splitext(dicomTestFilename)[0] + '*'
        data3 = TestDataInterface.fileWatcher.getNewestFile(filePattern)
        assert data1 == data3, 'getNewestFile data assertion'

        # Test watch file
        print('test watchFile')
        watchDir = os.path.join(testDir, 'test_input')
        TestDataInterface.fileWatcher._initWatch(watchDir, filePattern, 0)
        data4 = TestDataInterface.fileWatcher._watchFile(dicomTestFilename, timeout=5)
        assert data1 == data4, 'watchFile data assertion'

        # Test put text file
        print('test putTextFile')
        text = 'hello world'
        textFilename = os.path.join(tmpDir, 'test1.txt')
        TestDataInterface.fileWatcher.putFile(textFilename, text)
        with open(textFilename, 'r') as fp:
            text1 = fp.read()
        assert text1 == text, 'putTextFile assertion'

        # Test put binary file
        print('test putBinaryFile')
        data = b'\xAB\xCD\xFE\xED\x01\x23\x45\x67'
        binFilename = os.path.join(tmpDir, 'test1.bin')
        TestDataInterface.fileWatcher.putFile(binFilename, data)
        # read back data and compare to original
        with open(binFilename, 'rb') as fp:
            data1 = fp.read()
        assert data1 == data, 'putBinaryFile assertion'

        # Test list files
        filePattern = os.path.join(tmpDir, 'test1*')
        fileList = TestDataInterface.fileWatcher.listFiles(filePattern)
        assert len(fileList) == 2

        # Test allowedFileTypes
        allowedTypes = TestDataInterface.fileWatcher.getAllowedFileTypes()
        assert allowedTypes == ['*']
        return
