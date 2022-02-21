"""-----------------------------------------------------------------------------

sample.py (Last Updated: 01/26/2021)

The purpose of this script is to actually to run a sample project using a 
bidsIncremental stream which originates as DICOMS (collect from a scanner).

Specifically, it will initiate a call to bidsInterface that retrieves dicom
files formatted as bidsIncrementals, do some sort of analysis based on the
Nifti data received, and then output the answer.

The purpose of this *particular* script is to demonstrated how you can use the
various scripts, functions, etc. we have developed for your use! The functions
we will reference are in 'rt-cloud/rtCommon/'.

Finally, this script is called from the projectInterface which has a web interface
and accepts commands to 'start' or 'stop' a run. When the 'start' button is
pressed it will run this scirpt passing in whatever conifgurations have been
set in the web page as a configuration file. Note that projectInterface is
started from the script 'run-projectInterface.sh'.

-----------------------------------------------------------------------------"""

verbose = False

if verbose:
    # print a short introduction on the internet window
    print(""
        "-----------------------------------------------------------------------------\n"
        "The purpose of this sample project is to demonstrate different ways you can\n"
        "implement functions, structures, etc. that we have developed for your use.\n"
        "You will find some comments printed on this html browser. However, if you want\n"
        "more information about how things work please take a look at dicomBidsStream.py’.\n"
        "Good luck!\n"
        "-----------------------------------------------------------------------------")

# import important modules
from html import entities
import os
import sys
import time
import argparse
import warnings
import numpy as np
import scipy.io as sio


if verbose:
    print(''
        '|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||')

# obtain full path for current directory: '.../rt-cloud/projects/sample'
currPath = os.path.dirname(os.path.realpath(__file__))
# obtain full path for root directory: '.../rt-cloud'
rootPath = os.path.dirname(os.path.dirname(currPath))

# add the path for the root directory to your python path so that you can import
#   project modules from rt-cloud
sys.path.append(rootPath)
# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile, stringPartialFormat, calcAvgRoundTripTime
from rtCommon.clientInterface import ClientInterface
from rtCommon.imageHandling import bidsIncrementalTimeToNextTr

# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/dicomBidsStream.toml')


def doRuns(cfg, clientInterfaces):
    """
    This function is called by 'main()' below. Here, we use the 'bidsInterface'
    to read in dicoms formatted as bidsIncrementals (presumably from the scanner,
    but here it's from a folder with previously collected dicom files), doing some
    sort of analysis in the cloud, and then sending the info to the web browser.

    INPUT:
        [1] cfg - configuration file with important variables)
        [2] clientInterfaces - this contains the other communication interfaces needed
    OUTPUT:
        None.
    """
    global verbose
    dataInterface = clientInterfaces.dataInterface
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    subjInterface.setMessage("Preparing Run ...")

    # get round trip time to dataInterface computer
    rttSec = calcAvgRoundTripTime(dataInterface.ping)
    # get clockSkew between this computer and the dataInterface computer
    clockSkew = dataInterface.getClockSkew(time.time(), rttSec)

    # variables we'll use throughout
    scanNum = cfg.scanNum[0]
    runNum = cfg.runNum[0]

    print(f"Doing run {runNum}, scan {scanNum}")

    """
    Before we get ahead of ourselves, we need to make sure that the necessary file
        types are allowed (meaning, we are able to read them in)... in this example,
        at the very least we need to have access to dicom and txt file types.
    use the function 'allowedFileTypes' in 'fileClient.py' to check this!
    If allowedTypes doesn't include the file types we need to use then the
        file service (scannerDataService) running at the control room computer will
        need to be restarted with the correct list of allowed types provided.

    INPUT: None
    OUTPUT:
          [1] allowedFileTypes (list of allowed file types)
    """
    allowedFileTypes = dataInterface.getAllowedFileTypes()
    if verbose:
        print(""
        "-----------------------------------------------------------------------------\n"
        "Before continuing, we need to make sure that dicoms are allowed. To verify\n"
        "this, use the 'allowedFileTypes'.\n"
        "Allowed file types: %s" %allowedFileTypes)

    # obtain the path for the directory where the subject's dicoms live
    subj_imgDir = "{}.{}.{}".format(cfg.datestr, cfg.subjectName, cfg.subjectName)
    cfg.dicomDir = os.path.join(cfg.imgDir, subj_imgDir)
    if verbose:
        print("Location of the subject's dicoms: \n" + cfg.dicomDir + "\n"
        "-----------------------------------------------------------------------------")

    #  If a dicomNamePattern is supplied in the config file, such as
    #  "001_{SCAN:06d}_{TR:06d}.dcm", then call stringPartialFormat() to
    #  set the SCAN number for the series of Dicoms we will be streaming.
    dicomScanNamePattern = stringPartialFormat(cfg.dicomNamePattern, 'SCAN', scanNum)

    """
    Initialize a watch for the entire dicom folder using the function 'initDicomBidsStream'
    of the bidsInterface.
    INPUT:
        [1] cfg.dicomDir (where the subject's dicom files live)
        [2] cfg.dicomNamePattern (the naming pattern of dicom files)
        [3] cfg.minExpectedDicomSize (a check on size to make sure we don't
                accidentally grab a dicom before it's fully acquired)
    """
    if verbose:
        print("• initalize a watch for the dicoms using 'initWatch'")
    entities = {'subject': cfg.subjectName, 'task': 'test', 'run': runNum}
    streamId = bidsInterface.initDicomBidsStream(cfg.dicomDir, dicomScanNamePattern, 
                                                 cfg.minExpectedDicomSize, **entities)

    """
    We will use the function plotDataPoint in webInterface whenever we
      want to send values to the web browser so that they can be plotted in the
      --Data Plots-- tab.
    However at the start of a run we will want to clear the plot, and we can use
    clearRunPlot(runId), or clearAllPlots() also in the webInterface object.
    """
    if verbose:
        print("• clear any pre-existing plot for this run using 'clearRunPlot(runNum)'")
    webInterface.clearRunPlot(runNum)

    if verbose:
        print(""
        "-----------------------------------------------------------------------------\n"
        "In this sample project, we will retrieve the dicom file for a given TR as\n"
        "a bidsIncremental which is already in Nifti format.\n"
        "-----------------------------------------------------------------------------\n")

    num_total_TRs = 10  # number of TRs to use for example 1
    all_avg_activations = np.zeros((num_total_TRs, 1))
    for this_TR in np.arange(num_total_TRs):
        # declare variables that are needed to use in get data requests
        dcmTimeout = cfg.trInterval  # usually the image timeout equals the TR interval
        if this_TR == 0:
            # for first TR set a longer wait time for the Dicom to arrive
            dcmTimeout =  30

        # Get the next bidsIncremental. This is a Nifti format of the Dicom data
        #  with other metadata related to BIDs format.
        bidsIncremental = bidsInterface.getIncremental(streamId, timeout=dcmTimeout)
        # getIncremental will raise an exception if the data isn't found
        # so at this point in the script the bidsIncremental is not None

        niftiData = bidsIncremental.getImageData()

        # take the average of all the activation values
        avg_niftiData = np.mean(niftiData)
        # avg_niftiData = np.round(avg_niftiData,decimals=2)
        print("| average activation value for TR %d is %f" %(this_TR, avg_niftiData))

        max_niftiData = np.amax(niftiData)
        if verbose:
            print("| max activation value for TR %d is %d" %(this_TR, max_niftiData))

        # Now we will send the result to be used to provide feedback for the subject.
        # Using subjInterface.setResult() will send the classification result to a
        # remote subjectService that can use the value to update the display on
        # the presentation computer.
        if verbose:
            print("| send result to the presentation computer for provide subject feedback")
        # convert to value between 0 and 1
        minAvg = 305
        maxAvg = 315
        feedback = (avg_niftiData - minAvg) / (maxAvg - minAvg)
        # Get the seconds remaining before next TR starts, this can be passed to
        #  the setResult function to delay stimulus until that time
        try:
            secUntilNextTr = bidsIncrementalTimeToNextTr(bidsIncremental, clockSkew)
            print(f"## Secs to next TR {secUntilNextTr}")
        except Exception as err:
            # Since we are running pre-collected data and we only compare time of
            #  day not date, an error can occur if the runTime is earlier in the
            #  day than the collection time.
            # print(f'bidsIncrementalTimeToNextTr error: {err}')
            pass

        # We will set a static delay since the images where pre-collected.
        # In an actual run we could use the secUntilNextTr as the delay field.
        setFeedbackDelay = 500 # milliseconds
        subjInterface.setResult(runNum, int(this_TR), float(feedback), setFeedbackDelay)

        # Finally we will use use webInterface.plotDataPoint() to send the result
        # to the web browser to be plotted in the --Data Plots-- tab.
        # Each run will have its own data plot, the x-axis will the the TR vol
        # number and the y-axis will be the classification value (float).
        # IMPORTANT ** the inputs MUST be python integers or python floats;
        #   it won't work if it's a numpy int or numpy float **
        if verbose:
            print("| send result to the web, plotted in the 'Data Plots' tab")
        webInterface.plotDataPoint(runNum, int(this_TR), float(avg_niftiData))

        # save the activations value info into a vector that can be saved later
        all_avg_activations[this_TR] = avg_niftiData

    # create the full path filename of where we want to save the activation values vector.
    #   we're going to save things as .txt and .mat files
    output_textFilename = '/tmp/cloud_directory/tmp/avg_activations.txt'
    output_matFilename = os.path.join('/tmp/cloud_directory/tmp/avg_activations.mat')

    subjInterface.setMessage("End Run")
    responses = subjInterface.getAllResponses()
    keypresses = [response.get('key_pressed') for response in responses]
    stimDurations = [response.get('stimulus_duration') for response in responses]
    if verbose:
        print(f'Keypresses: {keypresses}')
        print(f'Durations: {stimDurations}')

    # use 'putFile' from the dataInterface to save the .txt file
    #   INPUT:
    #       [1] filename (full path!)
    #       [2] data (that you want to write into the file)
    if verbose:
        print(""
        "-----------------------------------------------------------------------------\n"
        "• save activation value as a text file to tmp folder")
    dataInterface.putFile(output_textFilename, str(all_avg_activations))

    # use sio.save mat from scipy to save the matlab file
    if verbose:
        print("• save activation value as a matlab file to tmp folder")
    sio.savemat(output_matFilename, {'value':all_avg_activations})

    if verbose:
        print(""
        "-----------------------------------------------------------------------------\n"
        "REAL-TIME EXPERIMENT COMPLETE!")

    return


def main(argv=None):
    global verbose
    """
    This is the main function that is called when you run 'dicomBidsStream.py'.

    Here, you will load the configuration settings specified in the toml configuration
    file, initiate the clientInterface for communication with the projectServer (via
    its sub-interfaces: dataInterface, subjInterface, and webInterface). And then call
    the function 'doRuns' to actually start doing the experiment.
    """

    # Some generally recommended arguments to parse for all experiment scripts
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default=None, type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default=None, type=str,
                           help='Comma separated list of scan number')
    argParser.add_argument('--yesToPrompts', '-y', default=False, action='store_true',
                           help='automatically answer tyes to any prompts')

    # Some additional parameters only used for this sample project
    argParser.add_argument('--noVerbose', '-nv', default=False, action='store_true',
                           help='print verbose output')

    args = argParser.parse_args(argv)

    verbose = not args.noVerbose

    # load the experiment configuration file
    cfg = loadConfigFile(args.config)

    # override config file run and scan values if specified
    if args.runs is not None:
        print("runs: ", args.runs)
        cfg.runNum = [int(x) for x in args.runs.split(',')]
    if args.scans is not None:
        print("scans: ", args.scans)
        cfg.scanNum = [int(x) for x in args.scans.split(',')]

    # Initialize the RPC connection to the projectInterface.
    # This will give us a dataInterface for retrieving files,
    # a subjectInterface for giving feedback, and a webInterface
    # for updating what is displayed on the experimenter's webpage.
    clientInterfaces = ClientInterface(yesToPrompts=args.yesToPrompts)


    # obtain paths for important directories (e.g. location of dicom files)
    if cfg.imgDir is None:
        # Use the sample dicom files from the sample project
        cfg.imgDir = os.path.join(rootPath, 'projects', 'sample', 'dicomDir')
    cfg.codeDir = currPath

    # now that we have the necessary variables, call the function 'doRuns' in order
    #   to actually start reading dicoms and doing your analyses of interest!
    #   INPUT:
    #       [1] cfg (configuration file with important variables)
    #       [2] dataInterface (this will allow a script from the cloud to access files
    #            from the stimulus computer that receives dicoms from the Siemens
    #            console computer)
    #       [3] subjInterface - this allows sending feedback (e.g. classification results)
    #            to a subjectService running on the presentation computer to provide
    #            feedback to the subject (and optionally get their response).
    #       [4] webInterface - this allows updating information on the experimenter webpage.
    #            For example to plot data points, or update status messages.
    doRuns(cfg, clientInterfaces)
    return 0


if __name__ == "__main__":
    """
    If 'sample.py' is invoked as a program, then actually go through all of the portions
    of this script. This statement is not satisfied if functions are called from another
    script using "from sample.py import FUNCTION"
    """
    main()
    sys.exit(0)
