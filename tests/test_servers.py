import pytest
import os
import threading
import time
import glob
import json
import shutil
import logging
from base64 import b64decode
import projects.sample.sample as sample
import rtCommon.wsRequestStructs as req
import rtCommon.utils as utils
import rtCommon.projectUtils as projUtils
from rtCommon.fileInterface import FileInterface
from rtCommon.fileServer import WsFileWatcher
from rtCommon.webServer import Web, handleDataRequest, CommonOutputDir
from rtCommon.structDict import StructDict
from rtCommon.errors import RequestError
from rtCommon.imageHandling import readDicomFromFile, anonymizeDicom, writeDicomToBuffer
from rtCommon.webSocketHandlers import sendWebSocketMessage
from rtCommon.projectServer import ProjectServer


testDir = os.path.dirname(__file__)
rootPath = os.path.dirname(testDir)
samplePath = os.path.join(rootPath,'projects/sample')
tmpDir = os.path.join(testDir, 'tmp/')
fileTypeList = ['.dcm', '.mat', '.bin', '.txt']


@pytest.fixture(scope="module")
def dicomTestFilename():  # type: ignore
    return os.path.join(testDir, 'test_input/001_000013_000005.dcm')


@pytest.fixture(scope="module")
def bigTestfile():  # type: ignore
    filename = os.path.join(testDir, 'test_input/bigfile.bin')
    if not os.path.exists(filename):
        with open(filename, 'wb') as fout:
            for i in range(101):
                fout.write(os.urandom(1024*1024))
    return filename


class TestServers:
    mainThread = None
    fileThread = None
    pingCount = 0

    def setup_class(cls):
        utils.installLoggers(logging.DEBUG, logging.DEBUG, filename='logs/tests.log')
        # Start a projectServer thread running
        cfg = StructDict({'sessionId': "test",
                          'subjectName': "test_sample",
                          'subjectNum': 1,
                          'subjectDay': 1,
                          'sessionNum': 1})
        args = StructDict({'config': cfg,
                           'mainScript': 'projects/sample/sample.py',
                           'filesremote': True,
                           'port': 8921, 
                           'test': True})
        projectServer = ProjectServer(args)
        cls.mainThread = threading.Thread(name='mainThread', target=projectServer.start)
        cls.mainThread.setDaemon(True)
        cls.mainThread.start()
        time.sleep(.1)

        # Start a fileWatcher thread running
        cls.fileThread = threading.Thread(
            name='fileThread',
            target=WsFileWatcher.runFileWatcher,
            args=('localhost:8921',),
            kwargs={
                'retryInterval': 0.1,
                'allowedDirs': ['/tmp', testDir, samplePath],
                'allowedTypes': fileTypeList,
                'username': 'test',
                'password': 'test',
                'testMode': True
            }
        )
        cls.fileThread.setDaemon(True)
        cls.fileThread.start()
        time.sleep(1)

    def teardown_class(cls):
        WsFileWatcher.stop()
        Web.stop()
        time.sleep(1)
        pass

    def test_ping(self):
        print("test_ping")
        global pingCallbackEvent
        # Send a ping request from projectInterface to fileWatcher
        # assert Web.wsDataConn is not None
        cmd = {'cmd': 'ping'}
        response = Web.wsDataRequest(cmd, timeout=2)
        if response['status'] != 200:
            print("Ping error: {}".format(response))
        assert response['status'] == 200

    def test_validateRequestedFile(self):
        print("test_validateRequestedFile")
        res = WsFileWatcher.validateRequestedFile('/tmp/data', None, 'test')
        assert res is True

        res = WsFileWatcher.validateRequestedFile('/tmp/data', 'file.dcm', 'test')
        assert res is True

        res = WsFileWatcher.validateRequestedFile('/tmp/data', 'file.not', 'test')
        assert res is False

        res = WsFileWatcher.validateRequestedFile('/sys/data', 'file.dcm', 'test')
        assert res is False

        res = WsFileWatcher.validateRequestedFile(None, '/tmp/data/file.dcm', 'test')
        assert res is True

        res = WsFileWatcher.validateRequestedFile(None, '/sys/data/file.dcm', 'test')
        assert res is False

        res = WsFileWatcher.validateRequestedFile(None, '/tmp/file.bin', 'test')
        assert res is True

        res = WsFileWatcher.validateRequestedFile(None, '/tmp/file.txt', 'test')
        assert res is True

    def test_getFile(self, dicomTestFilename):
        print("test_getFile")
        global fileData
        # assert Web.wsDataConn is not None
        # Try to initialize file watcher with non-allowed directory
        cmd = req.initWatchReqStruct('/', '*', 0)
        response = Web.wsDataRequest(cmd)
        # we expect an error because '/' directory not allowed
        assert response['status'] == 400

        # Initialize with allowed directory
        cmd = req.initWatchReqStruct(testDir, '*.dcm', 0)
        response = Web.wsDataRequest(cmd)
        assert response['status'] == 200

        dcmImg = readDicomFromFile(dicomTestFilename)
        anonDcm = anonymizeDicom(dcmImg)
        data = writeDicomToBuffer(anonDcm)
        # with open(dicomTestFilename, 'rb') as fp:
        #     data = fp.read()

        cmd = req.watchFileReqStruct(dicomTestFilename)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        # import pdb; pdb.set_trace()
        assert responseData == data

        # Try compressed version
        cmd = req.watchFileReqStruct(dicomTestFilename, compress=True)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        assert responseData == data

        cmd = req.getFileReqStruct(dicomTestFilename)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        assert responseData == data

        # Try compressed version
        cmd = req.getFileReqStruct(dicomTestFilename, compress=True)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        assert responseData == data

        cmd = req.getNewestFileReqStruct(dicomTestFilename)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        assert responseData == data

        # Try to get a non-allowed file
        cmd = req.getFileReqStruct('/tmp/file.nope')
        try:
            responseData = handleDataRequest(cmd)
        except RequestError as err:
            # Expecting a status not 200 error to be raised
            assert 'status' in str(err)
        else:
            pytest.fail('Expecting RequestError')

        # try from a non-allowed directory
        cmd = req.getFileReqStruct('/nope/file.dcm')
        try:
            responseData = handleDataRequest(cmd)
        except RequestError as err:
            # Expecting a status not 200 error to be raised
            assert 'status' in str(err)
        else:
            pytest.fail('Expecting RequestError')

        # Test putTextFile
        testText = 'hello2'
        textFileName = os.path.join(tmpDir, 'test2.txt')
        cmd = req.putTextFileReqStruct(textFileName, testText)
        response = Web.wsDataRequest(cmd)
        assert response['status'] == 200

        # Test putBinaryData function
        testData = b'\xFE\xED\x01\x23'
        dataFileName = os.path.join(tmpDir, 'test2.bin')
        cmd = req.putBinaryFileReqStruct(dataFileName)
        for putFilePart in projUtils.generateDataParts(testData, cmd, compress=True):
            response = Web.wsDataRequest(putFilePart)
        assert response['status'] == 200
        # read back an compare to original
        cmd = req.getFileReqStruct(dataFileName)
        response = Web.wsDataRequest(cmd)
        responseData = b64decode(response['data'])
        assert responseData == testData

    def test_getBigFile(self, bigTestfile):
        # Read in original data
        with open(bigTestfile, 'rb') as fp:
            data = fp.read()

        # Read via fileClient
        startTime = time.time()
        cmd = req.getFileReqStruct(bigTestfile)
        try:
            responseData = handleDataRequest(cmd)
        except Exception as err:
            assert False, str(err)
        assert responseData == data
        print('Read Bigfile time: {}'.format(time.time() - startTime))

        # Write bigFile Synchronous
        startTime = time.time()
        cmd = req.putBinaryFileReqStruct(bigTestfile)
        for putFilePart in projUtils.generateDataParts(data, cmd, compress=False):
            response = Web.wsDataRequest(putFilePart)
            assert response['status'] == 200
        print('Write Bigfile sync time: {}'.format(time.time() - startTime))

        # Write bigFile Asynchronous
        startTime = time.time()
        cmd = req.putBinaryFileReqStruct(bigTestfile)
        callIds = []
        for putFilePart in projUtils.generateDataParts(data, cmd, compress=False):
            call_id, conn = Web.dataRequestHandler.prepare_request(putFilePart)
            Web.ioLoopInst.add_callback(sendWebSocketMessage, wsName='wsData', msg=json.dumps(putFilePart), conn=conn)
            callIds.append(call_id)
        for callId in callIds:
            response = Web.dataRequestHandler.get_response(callId)
            assert response['status'] == 200
        print('Write Bigfile async time: {}'.format(time.time() - startTime))

        # Read back written data
        writtenPath = os.path.join(CommonOutputDir, bigTestfile)
        with open(writtenPath, 'rb') as fp:
            writtenData = fp.read()
        assert writtenData == data

    def test_runFromCommandLine(self):
        argv = []  # ['--filesremote']
        ret = sample.main(argv)
        assert ret == 0

    def test_fileInterface(self, bigTestfile):
        fileInterface = FileInterface(filesremote=True)

        # Read in original data
        with open(bigTestfile, 'rb') as fp:
            data = fp.read()

        # Read via fileClient
        startTime = time.time()
        try:
            responseData = fileInterface.getFile(bigTestfile)
        except Exception as err:
            assert False, str(err)
        assert responseData == data
        print('Read Bigfile time: {}'.format(time.time() - startTime))

        # Write bigFile
        startTime = time.time()
        try:
            fileInterface.putBinaryFile(bigTestfile, data)
        except Exception as err:
            assert False, str(err)
        print('Write Bigfile time: {}'.format(time.time() - startTime))
        # Read back written data and compare to original
        writtenPath = os.path.join(CommonOutputDir, bigTestfile)
        with open(writtenPath, 'rb') as fp:
            writtenData = fp.read()
        assert writtenData == data

        # test get allowedFileTypes
        allowedTypes = fileInterface.allowedFileTypes()
        assert allowedTypes == fileTypeList

        # test list files
        filepattern = os.path.join(testDir, 'test_input', '*.dcm')
        try:
            filelist = fileInterface.listFiles(filepattern)
        except Exception as err:
            assert False, str(err)
        # get list locally
        filelist2 = [x for x in glob.iglob(filepattern)]
        filelist.sort()
        filelist2.sort()
        assert filelist == filelist2

        # test downloadFilesFromCloud and uploadFilesToCloud
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
        fileInterface.downloadFilesFromCloud('/tmp/d1/test*.txt', '/tmp/d2')
        fileInterface.downloadFilesFromCloud('/tmp/d1/test*.bin', '/tmp/d2')
        # 3. upload files to cloud
        fileInterface.uploadFilesToCloud('/tmp/d2/test*.txt', '/tmp/d3')
        fileInterface.uploadFilesToCloud('/tmp/d2/test*.bin', '/tmp/d3')
        # check that all files in d1 are same as files in d3
        d3text1 = utils.readFile('/tmp/d3/test1.txt', binary=False)
        d3text2 = utils.readFile('/tmp/d3/test2.txt', binary=False)
        d3bin1 = utils.readFile('/tmp/d3/test3.bin')
        d3bin2 = utils.readFile('/tmp/d3/test4.bin')
        assert d3text1 == text1
        assert d3text2 == text2
        assert d3bin1 == bindata1
        assert d3bin2 == bindata2

    def test_delete(self):
        fileList = ['/tmp/d1/test1.txt', '/tmp/d1/d2/test2.txt',
                    '/tmp/d1/d2/d3/test3.txt', '/tmp/d1/d2/d3/test4.txt']
        for file in fileList:
            utils.writeFile(file, 'hello', binary=False)

        # test delete files from list
        assert os.path.exists(fileList[-1])
        utils.deleteFilesFromList(fileList)
        assert not os.path.exists(fileList[-1])
        assert os.path.isdir('/tmp/d1/d2/d3')

        # test delete folder
        for file in fileList:
            utils.writeFile(file, 'hello', binary=False)
        utils.deleteFolder('/tmp/d1')
        assert not os.path.isdir('/tmp/d1')

        # test delete files recursively in folders, but leave folders in place
        for file in fileList:
            utils.writeFile(file, 'hello', binary=False)
        utils.deleteFolderFiles('/tmp/d1')
        assert os.path.isdir('/tmp/d1/d2/d3')
