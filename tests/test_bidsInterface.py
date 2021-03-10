import os
import pytest
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.imageHandling import convertDicomImgToNifti, readDicomFromFile
from rtCommon.clientInterface import ClientInterface
from rtCommon.bidsInterface import BidsInterface, tmpDownloadOpenNeuro
from rtCommon.bidsCommon import getDicomMetadata
from tests.backgroundTestServers import BackgroundTestServers
from tests.common import rtCloudPath

test_sampleProjectDicomPath = os.path.join(rtCloudPath,
    "projects/sample/dicomDir/20190219.0219191_faceMatching.0219191_faceMatching/")

class TestBidsInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    # Local bidsInterface test
    def test_localBidsInterface(self):
        """Test BidsInterface when instantiated in local mode"""
        TestBidsInterface.serversForTests.stopServers()
        TestBidsInterface.serversForTests.startServers(dataRemote=False)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        dicomStreamTest(bidsInterface)
        openNeuroStreamTest(bidsInterface)

    # Remote bidsInterface test
    def test_remoteBidsInterface(self):
        """Test BidsInterface when instantiated in local mode"""
        # Use a remote (RPC) client to the bidsInterface
        TestBidsInterface.serversForTests.stopServers()
        TestBidsInterface.serversForTests.startServers(dataRemote=True)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        dicomStreamTest(bidsInterface)
        openNeuroStreamTest(bidsInterface)

    # bidsInterface created locally by the client (no projectServer)
    def test_clientLocalBidsInterface(self):
        TestBidsInterface.serversForTests.stopServers()
        bidsInterface = BidsInterface(dataRemote=False)
        dicomStreamTest(bidsInterface)
        openNeuroStreamTest(bidsInterface)


def dicomStreamTest(bidsInterface):
    # initialize the stream
    entities = {'subject': '01', 'task': 'test', 'run': 1, 'suffix': 'bold', 'datatype': 'func'}
    print(f'### {test_sampleProjectDicomPath}')
    streamId = bidsInterface.initDicomBidsStream(test_sampleProjectDicomPath,
                                                 "001_000013_{TR:06d}.dcm", 300*1024, **entities)

    for idx in [*range(10), 5, 2, 7]:
        # get the incremental from the stream
        streamIncremental = bidsInterface.getIncremental(streamId, volIdx=idx)
        # read the incremental locally for test comparison
        dicomPath = os.path.join(test_sampleProjectDicomPath, "001_000013_{TR:06d}.dcm".format(TR=idx))
        dicomImg = readDicomFromFile(dicomPath)
        dicomMetadata = getDicomMetadata(dicomImg)
        dicomMetadata.update(entities)
        niftiImg = convertDicomImgToNifti(dicomImg)
        localIncremental = BidsIncremental(niftiImg, dicomMetadata)
        print(f"Dicom stream check: image {idx}")
        assert streamIncremental == localIncremental
    pass

def openNeuroStreamTest(bidsInterface):
    dsAccessionNumber = 'ds002338'
    dsSubject = 'xp201'
    datasetDir = tmpDownloadOpenNeuro(dsAccessionNumber, dsSubject, 1)
    localEntities = {'subject': dsSubject, 'run': 1, 'suffix': 'bold', 'datatype': 'func'}
    remoteEntities = {'subject': dsSubject, 'run': 1}
    localBidsArchive = BidsArchive(datasetDir)
    streamId = bidsInterface.initOpenNeuroStream(dsAccessionNumber, **remoteEntities)
    for idx in range(3):
        streamIncremental = bidsInterface.getIncremental(streamId)
        localIncremental = localBidsArchive.getIncremental(idx, **localEntities)
        print(f"OpenNeuro stream check: image {idx}")
        assert streamIncremental == localIncremental

    for idx in [5, 2, 7]:
        streamIncremental = bidsInterface.getIncremental(streamId, volIdx=idx)
        localIncremental = localBidsArchive.getIncremental(idx, **localEntities)
        print(f"OpenNeuro stream check: image {idx}")
        assert streamIncremental == localIncremental

    numVols = bidsInterface.getNumVolumes(streamId)
    assert numVols > 0 and numVols < 1000
    # TODO - how to get num volumes of a run from the localBidsArchive?
    # assert numVols == localArchiveNumVols