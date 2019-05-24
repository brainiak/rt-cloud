import pytest
import os
from rtCommon.fileClient import FileInterface


testDir = os.path.dirname(__file__)


@pytest.fixture(scope="module")
def dicomTestFilename():  # type: ignore
    return os.path.join(testDir, 'test_input/001_000005_000100.dcm')


class TestFileInterface:
    fileWatcher = None

    def setup_class(cls):
        TestFileInterface.fileWatcher = FileInterface()

    def teardown_class(cls):
        print('teardown')
        TestFileInterface.fileWatcher = None

    def test_funcs(cls, dicomTestFilename):
        with open(dicomTestFilename, 'rb') as fp:
            data1 = fp.read()

        # Test getFile
        print('test getFile')
        data2 = TestFileInterface.fileWatcher.getFile(dicomTestFilename)
        assert data1 == data2, 'getFile data assertion'

        # Test getNewestFile
        print('test getNewestFile')
        filePattern = os.path.splitext(dicomTestFilename)[0] + '*'
        data3 = TestFileInterface.fileWatcher.getNewestFile(filePattern)
        assert data1 == data3, 'getNewestFile data assertion'

        # Test watch file
        print('test watchFile')
        watchDir = os.path.join(testDir, 'test_input')
        TestFileInterface.fileWatcher.initWatch(watchDir, filePattern, 0)
        data4 = TestFileInterface.fileWatcher.watchFile(dicomTestFilename, timeout=5)
        assert data1 == data4, 'watchFile data assertion'

        # Test put text file
        print('test putTextFile')
        text = 'hello world'
        textFilename = '~/tmp/test1.txt'
        TestFileInterface.fileWatcher.putTextFile(textFilename, text)
        with open(textFilename, 'r') as fp:
            text1 = fp.read()
        assert text1 == text, 'putTextFile assertion'

        return
