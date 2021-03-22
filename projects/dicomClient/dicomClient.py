# import important modules
import os
import sys
import argparse
import toml

currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)

from rtCommon.bidsCommon import getDicomMetadata
from rtCommon.bidsIncremental import BidsIncremental
from rtCommon.imageHandling import readDicomFromFile, convertDicomImgToNifti
from rtCommon.dataInterface import DataInterface
import rtCommon.utils as utils
from rtCommon.bidsArchive import BidsArchive

# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface


#test_sampleProjectDicomPath = os.path.join(currPath, 'dicomDir/20190219.0219191_amygActivation.0219191_amygActivation')
defaultConfig = os.path.join(currPath, 'conf/dicomClient.toml')
dcmPath = os.path.join(currPath, 'dicomDir/20190219.0219191_amygActivation.0219191_amygActivation')

def doRuns(cfg, bidsInterface, subjInterface, webInterface):
    # archive from local incremental
    archivePath_l = os.path.join(currPath, "BidsArchive_local")
    if os.path.exists(archivePath_l):
        utils.deleteFolder(archivePath_l)
    archive_local = BidsArchive(archivePath_l)
    # archive from stream incremental
    archivePath_s = os.path.join(currPath, "BidsArchive_stream")
    if os.path.exists(archivePath_s):
        utils.deleteFolder(archivePath_s)
    archive_stream = BidsArchive(archivePath_s)

    print(f'### {dcmPath}')
    #dataInterface = DataInterface(dataRemote=False, allowedDirs=['*'], allowedFileTypes=['*'])
    #entities = {'subject': '01', 'task': 'test', 'run': 1, 'suffix': 'bold', 'datatype': 'func'}
    entities = {k: cfg[k] for k in ('subject', 'task', 'suffix', 'run', 'datatype')}
    subject = int(entities['subject'])
    print(entities)
    #format = '{03d}_000009_{TR:06d}.dcm'.format(subject)
    streamId = bidsInterface.initDicomBidsStream(dcmPath, "001_000009_{TR:06d}.dcm", 200 * 1024)
    print(streamId)

    for idx in range(1,379):
        # get the incremental from the stream
        streamIncremental = bidsInterface.getIncremental(streamId, volIdx=idx)
        # read the incremental locally for test comparison
        dicomPath = os.path.join(dcmPath, "001_000009_{TR:06d}.dcm".format(TR=idx))
        dicomImg = readDicomFromFile(dicomPath)
        dicomMetadata = getDicomMetadata(dicomImg)
        dicomMetadata.update(entities)
        niftiImg = convertDicomImgToNifti(dicomImg)
        localIncremental = BidsIncremental(niftiImg, dicomMetadata)
        archive_local.appendIncremental(localIncremental)
        archive_stream.appendIncremental(streamIncremental)
        print(f"Dicom stream check: image {idx}")
        assert streamIncremental == localIncremental


def main(argv=None):
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default=None, type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--yesToPrompts', '-y', default=False, action='store_true',
                           help='automatically answer tyes to any prompts')
    args = argParser.parse_args(argv)

    # Initialize the RPC connection to the projectInterface
    # This will give us a dataInterface for retrieving files and
    # a subjectInterface for giving feedback
    clientInterfaces = ClientInterface(yesToPrompts=args.yesToPrompts)
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    # load the experiment configuration file
    cfg = toml.load(args.config)
    doRuns(cfg, bidsInterface, subjInterface, webInterface)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
