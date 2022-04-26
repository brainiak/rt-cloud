# import important modules
import os
import shutil
import subprocess
import sys
import numpy
import uuid
import argparse
import tempfile
from tqdm import tqdm

currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)

# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface
from rtCommon.bidsArchive import BidsArchive
from rtCommon.bidsRun import BidsRun

# path for default configuration toml file
defaultConfig = os.path.join(currPath, 'conf', 'openNeuroClient.toml')
tmpDir = tempfile.gettempdir()


def doRuns(cfg, clientInterfaces):
    """
    Process a run of a bids dataset. The subject and run configuration
    values will be supplied by the cfg parameter.
    Args:
        cfg: configurations parsed from the project toml config file
        bidsInterface: client interface to bids data
        webInterface: client interface to user web page
    Returns: no return value
    """
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    subject = cfg.subjectName
    run = cfg.runNum[0]
    entities = {'subject': subject, 'run': run, 'suffix': 'bold', 'datatype': 'func'}
    webInterface.clearRunPlot(int(run))
    if cfg.writeBidsArchive is True:
        # Create a new bids archive from the incrementals
        bidsArchivePath = os.path.join(tmpDir, 'bids_archive_' + uuid.uuid4().hex)
        print(f'BIDS Archive will be written to {bidsArchivePath}')
        newArchive = BidsArchive(bidsArchivePath)
        newRun = BidsRun(**entities)
    extraKwargs = {}
    if clientInterfaces.isUsingProjectServer():
        # Set long timeout to download and cache openneuro dataset
        extraKwargs = {"rpc_timeout": 300}

    # STEPHEN NEW CODE
    # Download a dataset
    # copied from Stephen's fork, branch thesis-eval

    # Section: Download and unzip a set of datasets from OpenNeuro
    DATASET_DIR = 'datasets'
    DATASET_DIR_FMT = os.path.join(DATASET_DIR, '{}-download')
    TARGET_DIR = 'tmp_out'
    tmpdir = tempfile.gettempdir()
    print("Temp dir for dataset download:", tmpdir)
    archives = []

    def download_and_unzip_datasets(dataset_numbers):
        for dataset_num in dataset_numbers:
            dataset_path = DATASET_DIR_FMT.format(dataset_num)

            if os.path.exists(dataset_path):
                print("Already have dataset", str(dataset_num))
                archives.append(BidsArchive(dataset_path))
                continue

            command = ('aws s3 sync --no-sign-request '
                       's3://openneuro.org/{num} {path}/'
                       .format(num=dataset_num, path=dataset_path))
            command = command.split(' ')
            print("Downloading", dataset_num)
            assert subprocess.call(command, stdout=subprocess.DEVNULL) == 0, \
                "S3 download failed"

            print("Gunzipping", dataset_num)
            command = ['gunzip', '-r', dataset_path]
            assert subprocess.call(command) == 0, "Gunzip failed"

            print("Finished downloading and gunzipping dataset", dataset_num)
            archives.append(BidsArchive(dataset_path))

    DATASET_NUMBERS = ['ds002551', 'ds003440', 'ds000138', 'ds002750', 'ds002733']
    # DATASET_NUMBERS = ['ds003440', 'ds000138', 'ds002750', 'ds002733']
    download_and_unzip_datasets(DATASET_NUMBERS)

    # Section: Iterate through the archives, stream all the incrementals from
    # the data server
    for idx, archive in enumerate(archives):
        newArchivePath = archive.rootPath + '-2'
        shutil.rmtree(newArchivePath, ignore_errors=True)
        os.makedirs(newArchivePath, exist_ok=True)
        newArchive = BidsArchive(newArchivePath)

        subjects = archive.getSubjects()

        # Some lists may be empty, so make them have at least 'None' in them
        # so
        # they still can be iterated over and the inner run loop can be
        # executed
        """
        for maybe_empty_list in [runs, sessions]:
            if len(maybe_empty_list) == 0:
                maybe_empty_list.append(None)
        """

        for subject in subjects:
            entities = {'subject': subject}
            sessions = archive.get_sessions(subject=subject)

            # Need non-zero length list, even if no sessions, so that the loop
            # for 'sessions' still executes (same for later tasks/runs)
            if len(sessions) == 0:
                sessions = [None]

            for session in sessions:
                if session is not None:
                    entities['session'] = session
                tasks = archive.get_tasks(**entities)
                if len(tasks) == 0:
                    tasks = [None]

                for task in tasks:
                    if task is not None:
                        entities['task'] = task
                    runs = archive.get_runs(subject=subject, session=session,
                                            task=task)
                    if len(runs) == 0:
                        runs = [None]

                    for run in runs:
                        if run is not None:
                            entities['run'] = run
                        entities['datatype'] = 'func'

                        # filter out the None entities, though there shouldn't
                        # be any with the new logic
                        entities = {e: entities[e] for e in entities if
                                    entities[e] is not None}
                        newRun = BidsRun()

                        datasetNumber = DATASET_NUMBERS[idx]
                        print("Entities:", entities)
                        print("Dataset Number:", datasetNumber)
                        streamId = bidsInterface.initOpenNeuroStream(datasetNumber, **entities)
                        plotRun = None
                        for incIdx in range(bidsInterface.getNumVolumes(streamId)):
                            if incIdx % 20 == 0:
                                print("Processed {} incrementals (view 'Data "
                                      "Plots' tab for activation data)".format(incIdx))
                            # Get the BIDS Incremental, do the mean of the image data
                            incremental = bidsInterface.getIncremental(streamId, incIdx)
                            imageData = incremental.getImageData()
                            avg_niftiData = numpy.mean(imageData)
                            newRun.appendIncremental(incremental)
                            # print("| average activation value for TR %d is %f"
                            #     %(incIdx, avg_niftiData), end='\x1b[1k\r')
                            if run is None and plotRun:
                                print('Run was empty, using run=1 for this run')
                                plotRun = 1
                            else:
                                plotRun = run
                            webInterface.plotDataPoint(plotRun, incIdx, float(avg_niftiData))

                        # Append the BIDS Run to the new archive
                        print("Appending run to archive")
                        newArchive.appendBidsRun(newRun)

                        # Further verification possibilities (TODO):
                        # 1) All runs/subjects/sessions/tasks the same across
                        # archives
                        # 2) Image data the same for given
                        # subject/task/run/session combo
                        # 3) Dataset description/readme/events files are the
                        # same
                        # 4) Sidecar metadata is the same

    """
    # Initialize the bids stream
    print(f'Preparing dataset {cfg.dsAccessionNumber} for replay ...')
    streamId = bidsInterface.initOpenNeuroStream(cfg.dsAccessionNumber, **entities, **extraKwargs)
    numVols = bidsInterface.getNumVolumes(streamId)
    for idx in range(numVols):
        bidsIncremental = bidsInterface.getIncremental(streamId, idx)
        if cfg.writeBidsArchive is True:
            newRun.appendIncremental(bidsIncremental)
        imageData = bidsIncremental.getImageData()
        avg_niftiData = numpy.mean(imageData)
        print("| average activation value for TR %d is %f" %(idx, avg_niftiData))
        webInterface.plotDataPoint(int(run), idx, float(avg_niftiData))
    if cfg.writeBidsArchive is True:
        newArchive.appendBidsRun(newRun)
    """

def main(argv=None):
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default=None, type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--yesToPrompts', '-y', default=False, action='store_true',
                           help='automatically answer tyes to any prompts')
    argParser.add_argument('--archive', '-a', default=False, action='store_true',
                           help='Create a Bids Archive from the incoming Bids Incrementals.')
    args = argParser.parse_args(argv)

    # load the experiment configuration file
    cfg = loadConfigFile(args.config)

    # override config file run and scan values if specified
    if args.runs is not None:
        print("runs: ", args.runs)
        cfg.runNum = [int(x) for x in args.runs.split(',')]

    # if args.archive is True:
    cfg.writeBidsArchive = True

    # Initialize the RPC connection to the projectInterface
    # This will give us a dataInterface for retrieving files and
    # a subjectInterface for giving feedback
    clientInterfaces = ClientInterface(yesToPrompts=args.yesToPrompts, rpyc_timeout=5)
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    doRuns(cfg, clientInterfaces)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)
