"""-----------------------------------------------------------------------------

sample.py (Last Updated: 01/26/2021)

The purpose of this script is to actually to run the sample project.
Specifically, it will initiate a call to file watcher that searches for incoming
dicom files, do some sort of analysis based on the dicom file that's been received,
and then output the answer.

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
useInitWatch = True

if verbose:
    # print a short introduction on the internet window
    print(""
        "-----------------------------------------------------------------------------\n"
        "The purpose of this sample project is to demonstrate different ways you can\n"
        "implement functions, structures, etc. that we have developed for your use.\n"
        "You will find some comments printed on this html browser. However, if you want\n"
        "more information about how things work please take a look at ‘sample.py’.\n"
        "Good luck!\n"
        "-----------------------------------------------------------------------------")

# import important modules
import os
import sys
import argparse
import warnings
import numpy as np
import nibabel as nib
import scipy.io as sio

if verbose:
    print(''
        '|||||||||||||||||||||||||||| IGNORE THIS WARNING ||||||||||||||||||||||||||||')
with warnings.catch_warnings():
    if not verbose:
        warnings.filterwarnings("ignore", category=UserWarning)
    from nibabel.nicom import dicomreaders

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
from rtCommon.utils import loadConfigFile, stringPartialFormat
from rtCommon.clientInterface import ClientInterface
from rtCommon.imageHandling import readRetryDicomFromDataInterface, convertDicomImgToNifti

# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def doRuns(cfg, dataInterface, subjInterface, webInterface):
    """
    This function is called by 'main()' below. Here, we use the 'dataInterface'
    to read in dicoms (presumably from the scanner, but here it's from a folder
    with previously collected dicom files), doing some sort of analysis in the
    cloud, and then sending the info to the web browser.

    INPUT:
        [1] cfg - configuration file with important variables)
        [2] dataInterface - this will allow this script runnin in the cloud to access
                files from the stimulus computer, which receives dicom files directly
                from the MRI Scanner console
        [3] subjInterface - this allows sending feedback (e.g. classification results)
                to a subjectService running on the presentation computer to provide
                feedback to the subject (and optionally get their response).
        [4] webInterface - this allows updating information on the experimenter webpage.
                For example to plot data points, or update status messages.
    OUTPUT:
        None.
    """

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
    if cfg.isSynthetic:
        cfg.dicomDir = cfg.imgDir
    else:
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
    There are several ways to receive Dicom data from the control room computer:
    1. Using `initWatch()` and 'watchFile()` commands of dataInterface or the
        helper function `readRetryDicomFromDataInterface()` which calls watchFile()
        internally.
    2. Using the streaming functions with `initScannerStream()` and `getImageData(stream)`
        which are also part of the dataInterface.
    """
    if useInitWatch is True:
        """
        Initialize a watch for the entire dicom folder using the function 'initWatch'
        of the dataInterface. (Later we will use watchFile() to look for a specific dicom)
        INPUT:
            [1] cfg.dicomDir (where the subject's dicom files live)
            [2] cfg.dicomNamePattern (the naming pattern of dicom files)
            [3] cfg.minExpectedDicomSize (a check on size to make sure we don't
                    accidentally grab a dicom before it's fully acquired)
        """
        if verbose:
            print("• initalize a watch for the dicoms using 'initWatch'")
        dataInterface.initWatch(cfg.dicomDir, dicomScanNamePattern, cfg.minExpectedDicomSize)

    else:  # use Stream functions
        """
        Initialize a Dicom stream by indicating the directory and dicom file pattern that
        will be streamed.

        INPUTs to initScannerStream():
            [1] cfg.dicomDir (where the subject's dicom files live)
            [2] dicomScanNamePattern (the naming pattern of dicom files)
            [3] cfg.minExpectedDicomSize (a check on size to make sure we don't
                    accidentally grab a dicom before it's fully acquired)
        """
        streamId = dataInterface.initScannerStream(cfg.dicomDir,
                                                dicomScanNamePattern,
                                                cfg.minExpectedDicomSize)


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
        "In this sample project, we will retrieve the dicom file for a given TR and\n"
        "then convert the dicom file to a nifti object. **IMPORTANT: In this sample\n"
        "we won't care about the exact location of voxel data (we're only going to\n"
        "indiscriminately get the average activation value for all voxels). This\n"
        "actually isn't something you want to actually do but we'll go through the\n"
        "to get the data in the appropriate nifti format in the advanced sample\n"
        "project (amygActivation).** We are doing things in this way because it is the simplest way\n"
        "we can highlight the functionality of rt-cloud, which is the purpose of\n"
        "this sample project.\n"
        ".............................................................................\n"
        "NOTE: We will use the function readRetryDicomFromDataInterface() to retrieve\n"
        "specific dicom files from the subject's dicom folder. This function calls\n"
        "'dataInterface.watchFile' to look for the next dicom from the scanner.\n"
        "Since we're using previously collected dicom data, this functionality is\n"
        "not particularly relevant for this sample project but it is very important\n"
        "when running real-time experiments.\n"
        "-----------------------------------------------------------------------------\n")

    num_total_TRs = 10  # number of TRs to use for example 1
    if cfg.isSynthetic:
        num_total_TRs = cfg.numSynthetic
    all_avg_activations = np.zeros((num_total_TRs, 1))
    for this_TR in np.arange(num_total_TRs):
        # declare variables that are needed to use in get data requests
        timeout_file = 5 # small number because of demo, can increase for real-time
        dicomFilename = dicomScanNamePattern.format(TR=this_TR)

        if useInitWatch is True:
            """
            Use 'readRetryDicomFromDataInterface' in 'imageHandling.py' to wait for dicom
                files to be written by the scanner (uses 'watchFile' internally) and then
                reading the dicom file once it is available.
            INPUT:
                [1] dataInterface (allows a cloud script to access files from the
                    control room computer)
                [2] filename (the dicom file we're watching for and want to load)
                [3] timeout (time spent waiting for a file before timing out)
            OUTPUT:
                [1] dicomData (with class 'pydicom.dataset.FileDataset')
            """
            print(f'Processing TR {this_TR}')
            if verbose:
                print("• use 'readRetryDicomFromDataInterface' to read dicom file for",
                    "TR %d, %s" %(this_TR, dicomFilename))
            dicomData = readRetryDicomFromDataInterface(dataInterface, dicomFilename,
                timeout_file)

        else:  # use Stream functions
            """
            Use dataInterface.getImageData(streamId) to query a stream, waiting for a
                dicom file to be written by the scanner and then reading the dicom file
                once it is available.
            INPUT:
                [1] dataInterface (allows a cloud script to access files from the
                    control room computer)
                [2] streamId - from initScannerStream() called above
                [3] TR number - the image volume number to retrieve
                [3] timeout (time spent waiting for a file before timing out)
            OUTPUT:
                [1] dicomData (with class 'pydicom.dataset.FileDataset')
            """
            print(f'Processing TR {this_TR}')
            if verbose:
                print("• use dataInterface.getImageData() to read dicom file for"
                    "TR %d, %s" %(this_TR, dicomFilename))
            dicomData = dataInterface.getImageData(streamId, int(this_TR), timeout_file)

        if dicomData is None:
            print('Error: getImageData returned None')
            return

        dicomData.convert_pixel_data()

        if cfg.isSynthetic:
            niftiObject = convertDicomImgToNifti(dicomData)
        else:
            # use 'dicomreaders.mosaic_to_nii' to convert the dicom data into a nifti
            #   object. additional steps need to be taken to get the nifti object in
            #   the correct orientation, but we will ignore those steps here. refer to
            #   the advanced sample project (amygActivation) for more info about that
            if verbose:
                print("| convert dicom data into a nifti object")
            niftiObject = dicomreaders.mosaic_to_nii(dicomData)

        # take the average of all the activation values
        avg_niftiData = np.mean(niftiObject.get_fdata())
        # avg_niftiData = np.round(avg_niftiData,decimals=2)
        print("| average activation value for TR %d is %f" %(this_TR, avg_niftiData))

        max_niftiData = np.amax(niftiObject.get_fdata())
        if verbose:
            print("| max activation value for TR %d is %d" %(this_TR, max_niftiData))

        """
        INPUT:
            [1] projectComm (the communication pipe)
            [2] runNum (not to be confused with the scan number)
            [3] this_TR (timepoint of interest)
            [4] value (value you want to send over to the web browser)
            ** the inputs MUST be python integers; it won't work if it's a numpy int

        here, we are clearing an already existing plot
        """

        # Now we will send the result to be used to provide feedback for the subject.
        # Using subjInterface.setResult() will send the classification result to a
        # remote subjectService that can use the value to update the display on
        # the presentation computer.
        if verbose:
            print("| send result to the presentation computer for provide subject feedback")
        subjInterface.setResult(runNum, int(this_TR), float(avg_niftiData))

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
    global verbose, useInitWatch
    """
    This is the main function that is called when you run 'sample.py'.

    Here, you will load the configuration settings specified in the toml configuration
    file, initiate the clientInterface for communication with the projectServer (via
    its sub-interfaces: dataInterface, subjInterface, and webInterface). Ant then call
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
    argParser.add_argument('--useInitWatch', '-w', default=False, action='store_true',
                           help='use initWatch() functions instead of stream functions')
    argParser.add_argument('--noVerbose', '-nv', default=False, action='store_true',
                           help='print verbose output')

    args = argParser.parse_args(argv)

    useInitWatch = args.useInitWatch
    verbose = not args.noVerbose

    # load the experiment configuration file
    cfg = loadConfigFile(args.config)

    # override config file run and scan values if specified
    if args.runs is not None:
        print("runs: ", args.runs)
        cfg.runNum = [int(x) for x in args.runs.split(',')]
    if args.scans is not None:
        print("scans: ", args.scans)
        cfg.ScanNum = [int(x) for x in args.scans.split(',')]

    # Initialize the RPC connection to the projectInterface.
    # This will give us a dataInterface for retrieving files,
    # a subjectInterface for giving feedback, and a webInterface
    # for updating what is displayed on the experimenter's webpage.
    clientInterfaces = ClientInterface(yesToPrompts=args.yesToPrompts)
    dataInterface = clientInterfaces.dataInterface
    bidsInterface = clientInterfaces.bidsInterface
    subjInterface = clientInterfaces.subjInterface
    webInterface  = clientInterfaces.webInterface

    # obtain paths for important directories (e.g. location of dicom files)
    if cfg.imgDir is None:
        cfg.imgDir = os.path.join(currPath, 'dicomDir')
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
    doRuns(cfg, dataInterface, subjInterface, webInterface)
    return 0


if __name__ == "__main__":
    """
    If 'sample.py' is invoked as a program, then actually go through all of the portions
    of this script. This statement is not satisfied if functions are called from another
    script using "from sample.py import FUNCTION"
    """
    main()
    sys.exit(0)
