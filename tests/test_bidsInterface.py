import os
import time
import math
import pytest
import rtCommon.utils as utils
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.imageHandling import convertDicomImgToNifti, readDicomFromFile
from rtCommon.imageHandling import anonymizeDicom, attributesToAnonymize
from rtCommon.clientInterface import ClientInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.bidsCommon import getDicomMetadata, BidsAttributesToAnonymize
from rtCommon.openNeuro import OpenNeuroCache
from rtCommon.errors import MissingMetadataError
from tests.backgroundTestServers import BackgroundTestServers
from tests.common import rtCloudPath, tmpDir

test_sampleProjectDicomPath = os.path.join(rtCloudPath, 'projects', 'sample',
    'dicomDir', '20190219.0219191_faceMatching.0219191_faceMatching')

allowedDirs = [test_sampleProjectDicomPath, tmpDir]

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
        TestBidsInterface.serversForTests.startServers(dataRemote=False, allowedDirs=allowedDirs)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        dicomStreamTest(bidsInterface)
        openNeuroStreamTest(bidsInterface)

    # Remote bidsInterface test
    def test_remoteBidsInterface(self):
        """Test BidsInterface when instantiated in local mode"""
        # Use a remote (RPC) client to the bidsInterface
        TestBidsInterface.serversForTests.stopServers()
        TestBidsInterface.serversForTests.startServers(dataRemote=True, allowedDirs=allowedDirs)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        dicomStreamTest(bidsInterface)
        openNeuroStreamTest(bidsInterface)

    # bidsInterface created locally by the client (no projectServer)
    def test_clientLocalBidsInterface(self):
        TestBidsInterface.serversForTests.stopServers()
        # Allowed dirs for local case set to the same as in the backgroundTestServers
        bidsInterface = BidsInterface(dataRemote=False, allowedDirs=allowedDirs)
        dicomStreamTest(bidsInterface)
        # run again without dicom anonymization
        dicomStreamTest(bidsInterface, anonymize=False)
        openNeuroStreamTest(bidsInterface)


def isAnonymized(metadata):
    sensitiveAttrCount = 0
    for attr in BidsAttributesToAnonymize:
        val = metadata.get(attr, None)
        if val is not None and val != "":
            sensitiveAttrCount += 1
    if sensitiveAttrCount == 0:
        return True
    elif sensitiveAttrCount == len(BidsAttributesToAnonymize):
        return False
    else:
        raise MissingMetadataError('isAnonymized: Some fields missing')

def readLocalDicomIncremental(volIdx, anonymize=True, **entities):
    # read the incremental locally for test comparison
    dicomPath = os.path.join(test_sampleProjectDicomPath, "001_000013_{TR:06d}.dcm".format(TR=volIdx))
    dicomImg = readDicomFromFile(dicomPath)
    if anonymize is True:
        dicomImg = anonymizeDicom(dicomImg)
    dicomMetadata = getDicomMetadata(dicomImg)
    dicomMetadata.update(entities)
    niftiImg = convertDicomImgToNifti(dicomImg)
    localIncremental = BidsIncremental(niftiImg, dicomMetadata)
    return localIncremental


def dicomStreamTest(bidsInterface, anonymize=True):
    # initialize the stream
    entities = {'subject': '01', 'task': 'test', 'run': 1, 'suffix': 'bold', 'datatype': 'func'}

    # Try to init a stream to a non-allowed path
    if bidsInterface.isRunningRemote():
        with pytest.raises(Exception) as err:
            streamId = bidsInterface.initDicomBidsStream('/path/not/allowed',
                                                        "001_000013_{TR:06d}.dcm",
                                                        300*1024, anonymize=anonymize,
                                                        **entities)
        assert "not within list of allowed directories" in str(err.value)

    # Now init the real stream to an allowed path
    print(f'### {test_sampleProjectDicomPath}')
    streamId = bidsInterface.initDicomBidsStream(test_sampleProjectDicomPath,
                                                 "001_000013_{TR:06d}.dcm",
                                                 300*1024, anonymize=anonymize,
                                                 **entities)

    # Test that not specifying volIdx to getIncremental starts from the beginning in order
    for idx in [*range(3)]:
        # get the incremental from the stream
        streamIncremental = bidsInterface.getIncremental(streamId)
        assert isAnonymized(streamIncremental.getImageMetadata()) == anonymize
        localIncremental = readLocalDicomIncremental(idx, anonymize=anonymize, **entities)
        print(f"Dicom stream check: image {idx}")
        assert streamIncremental == localIncremental

    # Next provide a specific volume
    volIdx = 7
    streamIncremental = bidsInterface.getIncremental(streamId, volIdx=volIdx)
    localIncremental = readLocalDicomIncremental(volIdx, anonymize=anonymize, **entities)
    print(f"Dicom stream check: image {idx}")
    assert streamIncremental == localIncremental

    # Resume without specifying volumes
    for idx in [*range(8, 10)]:
        # get the incremental from the stream
        streamIncremental = bidsInterface.getIncremental(streamId)
        localIncremental = readLocalDicomIncremental(idx, anonymize=anonymize, **entities)
        print(f"Dicom stream check: image {idx}")
        assert streamIncremental == localIncremental

    # check clock skew function
    rtt = utils.calcAvgRoundTripTime(bidsInterface.ping)
    now = time.time()
    skew = bidsInterface.getClockSkew(now, rtt)
    if bidsInterface.isRunningRemote():
        # Check that skew equals 1.23 seconds because the scannerDataService
        #   clockSkew is set to 1.23 seconds when it is started in
        #   backgroundTestServers.py if dataRemote is True
        assert math.isclose(skew, 1.23, abs_tol=0.05) is True
    else:
        assert math.isclose(skew, 0, abs_tol=0.05) is True


def openNeuroStreamTest(bidsInterface):
    dsAccessionNumber = 'ds002338'
    dsSubject = 'xp201'
    localEntities = {'subject': dsSubject, 'run': '01', 'suffix': 'bold', 'datatype': 'func'}
    remoteEntities = {'subject': dsSubject, 'run': '01', 'suffix': 'bold'}
    extraKwargs = {}
    if bidsInterface.isRunningRemote():
        # Set longer timeout for potentially downloading data
        extraKwargs = {"rpc_timeout": 60}
    streamId = bidsInterface.initOpenNeuroStream(dsAccessionNumber, **remoteEntities,
                                                 **extraKwargs)
    openNeuroCache = OpenNeuroCache()
    datasetDir = openNeuroCache.downloadData(dsAccessionNumber, **localEntities)
    localBidsArchive = BidsArchive(datasetDir)

    for idx in range(3):
        streamIncremental = bidsInterface.getIncremental(streamId)
        localIncremental = localBidsArchive._getIncremental(idx, **localEntities)
        print(f"OpenNeuro stream check: image {idx}")
        assert streamIncremental == localIncremental

    for idx in [5, 2, 7]:
        streamIncremental = bidsInterface.getIncremental(streamId, volIdx=idx)
        localIncremental = localBidsArchive._getIncremental(idx, **localEntities)
        print(f"OpenNeuro stream check: image {idx}")
        assert streamIncremental == localIncremental

    # Resume without specifying volumes
    for idx in [*range(8, 10)]:
        streamIncremental = bidsInterface.getIncremental(streamId)
        localIncremental = localBidsArchive._getIncremental(idx, **localEntities)
        print(f"OpenNeuro stream check: image {idx}")
        assert streamIncremental == localIncremental

    numVols = bidsInterface.getNumVolumes(streamId)
    assert numVols > 0 and numVols < 1000

    # Check with local bidsRun
    localBidsRun = localBidsArchive.getBidsRun(**localEntities)
    assert numVols == localBidsRun.numIncrementals()
    assert numVols > 10
    for idx in [*range(6, 10)]:
        streamIncremental = bidsInterface.getIncremental(streamId, volIdx=idx)
        localIncremental = localBidsRun.getIncremental(idx)
        print(f"OpenNeuro bidsRun check: image {idx}")
        assert streamIncremental == localIncremental
