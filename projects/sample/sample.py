"""-----------------------------------------------------------------------------

sample.py (Last Updated: 11/19/2019)

The purpose of this type script is to actually run the sample project. 
Specifically, it will initiate a file watcher that searches for incoming dicom 
files, do some sort of analysis based on the dicom file that's been received, 
and then output the answer.

The purpose of this *particular* script is to demonstrated how you can use the 
various scripts, functions, etc. we have developed for your use! The functions
we will reference live in 'rt-cloud/rtCommon/'.

Finally, this script is called from 'projectMain.py', which is called from 
'run-projectInterface.sh'.

-----------------------------------------------------------------------------"""

# print a short introduction on the internet window
print(""
    "-----------------------------------------------------------------------------\n"
    "The purpose of this sample project is to demonstrate different ways you can\n"
    "implement functions, structures, etc. that we have developed for your use.\n"
    "You will find some comments printed on this html file. However, if you want\n"
    "more information about how things work please talk a look at ‘sample.py’.\n"
    "Good luck!\n"
    "-----------------------------------------------------------------------------")

# import important modules
import os
import sys
import time
import logging
import argparse
import numpy as np
import nibabel as nib
from nibabel.nicom import dicomreaders

# obtain full path for current directory: '.../rt-cloud/projects/sample'
currPath = os.path.dirname(os.path.realpath(__file__))
# obtain full path for root directory: '.../rt-cloud'
rootPath = os.path.dirname(os.path.dirname(currPath))

# add the path for the root directory to your python path so that you can import
#   project modules from rt-cloud
sys.path.append(rootPath)
# import project modules from rt-cloud
from rtCommon.utils import loadConfigFile
from rtCommon.fileClient import FileInterface
import rtCommon.projectUtils as projUtils
from rtCommon.readDicom import readRetryDicomFromFileInterface

# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/sample.toml')


def getDicomFileName(cfg, scanNum, fileNum):
    """
    This function produces the filename of the dicom of interest, which is useful
    considering how complicated these filenames can be!
    INPUT:  
        [1] cfg (config parameters)
        [2] scanNum (scan number)
        [3] fileNum (TR number, which will reference the correct file)
    OUTPUT: 
        [1] fullFileName (the filename of the dicom that should be grabbed)
    """

    if scanNum < 0:
        raise ValidationError("ScanNumber not supplied of invalid {}".format(scanNum))
    
    # converting important info to strings
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(fileNum).zfill(3)
    
    # the naming pattern is provided in the toml file
    if cfg.dicomNamePattern is None:
        raise InvocationError("Missing config settings dicomNamePattern")
    fileName = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    fullFileName = os.path.join(cfg.dicomDir, fileName)
    
    return fullFileName

def doRuns(cfg, fileInterface, projectComm):
    """
    This function is called by 'main()' below. Here, we use the 'fileInterface'
    to read in dicoms (presumably from the scanner, but here it's from a folder
    with previously collected dicom files), doing some sort of analysis in the
    cloud, and then sending the info to the web browser.

    INPUT:
        [1] cfg (configuration file with important variables)
        [2] fileInterface (this will allow you to call useful functions)
        [3] projectComm (communication pipe to talk with projectInterface)
    OUTPUT:
        None.

    This is the main function that is called when you run 'sample.py'.
    Here, you will set up an important argument parser (mostly provided by 
    the toml configuration file), initiate the class fileInterface, and then
    call the function 'doRuns' to actually start doing the experiment.
    """

    # variables we'll use throughout
    scanNum = cfg.scanNum[0]
    runNum = cfg.runNum[0]

    # before we get ahead of ourselves, we need to make sure that the necessary file
    #   types are allowed (meaning, we are able to read them in)... in this example,
    #   at the very least we need to have access to dicom and txt file types.
    # use the function 'allowedFileTypes' in 'fileClient.py' to check this!
    #   INPUT: None
    #   OUTPUT:
    #       [1] allowedFileTypes (list of allowed file types)
    
    allowedFileTypes = fileInterface.allowedFileTypes()
    print(""
    "Before continuing, we need to make sure that dicoms are allowed. To verify\n"
    "this, use the 'allowedFileTypes'.\n"
    "Allowed file types: %s" %allowedFileTypes)

    # obtain the path for the directory where the subject's dicoms live
    subj_imgDir = "{}.{}.{}".format(cfg.datestr, cfg.subjectName, cfg.subjectName)
    cfg.dicomDir = os.path.join(cfg.imgDir, subj_imgDir)
    print("Location of the subject's dicoms: \n%s\n" %cfg.dicomDir,
    "-----------------------------------------------------------------------------")

    # initialize a watch for the entire dicom folder (it doesn't look for a 
    #   specific dicom) using the function 'initWatch' in 'fileClient.py'
    #   INPUT:
    #       [1] cfg.dicomDir (where the subject's dicom files live)
    #       [2] cfg.dicomNamePattern (the naming pattern of dicom files)
    #       [3] cfg.minExpectedDicomSize (a check on size to make sure we don't
    #               accidentally grab a dicom before it's fully acquired)
    print("• initalize a watch for the dicoms using 'initWatch'")
    fileInterface.initWatch(cfg.dicomDir, cfg.dicomNamePattern, 
        cfg.minExpectedDicomSize)

    # we will use the function 'sendResultToWeb' in 'projectUtils.py' whenever we
    #   want to send values to the web browser so that they can be plotted in the
    #   --Data Plots-- tab
    #   INPUT:
    #       [1] projectComm (the communication pipe)
    #       [2] runNum (not to be confused with the scan number)
    #       [3] this_TR (timepoint of interest)
    #       [4] value (value you want to send over to the web browser)
    #       ** the inputs MUST be integers; it won't work if they're numpy datatypes
    #
    # here, we are clearing an already existing plot
    print("• clear any pre-existing plot using 'sendResultToWeb'")
    projUtils.sendResultToWeb(projectComm, runNum, None, None)

    print(""
    "-----------------------------------------------------------------------------\n"
    "In this sample project, we will retrieve the dicom file for a given TR and\n"
    "then convert the dicom file to a nifti object. **IMPORTANT: In this sample\n"
    "we won't care about the exact location of voxel data (we're only going to\n"
    "indiscriminately get the average activation value for all voxels). This\n"
    "actually isn't something you want to actually do but we'll go through the\n"
    "to get the data in the appropriate nifti format in the 'advanced sample\n"
    "project.** We are doing things in this way because it is the simplest way\n"
    "we can highlight the functionality of rt-cloud, which is the purpose of\n"
    "this sample project."
    ".............................................................................\n"
    "NOTE: We will use the function 'readRetryDicomFromFileInterface' to retrieve\n"
    "specific dicom files from the subject's dicom folder. This function calls\n"
    "'fileInterface.watchFile' to look for the next dicom from the scanner.\n"
    "Since we're using previously collected dicom data, this is functionality is\n"
    "not particularly relevant for this sample project but it is very important\n"
    "when running real-time experiments.\n"
    "-----------------------------------------------------------------------------\n")

    track_TRs = 0
    ex1_num_TRs = 6 # number of TRs to use for example 1
    all_avg_activations = np.zeros((20,1)) # this is hardcoded for 20 dicoms total
    for this_TR in np.arange(1,ex1_num_TRs):
        # declare variables that are needed to use 'readRetryDicomFromFileInterface'
        timeout_file = 5 # small number because of demo, can increase for real-time
        fileName = getDicomFileName(cfg, scanNum, this_TR) # use 'getDicomFileName'

        # use 'readRetryDicomFromFileInterface' in 'readDicom.py' to wait for dicom
        #   files to come in (by using 'watchFile' in 'fileClient.py') and then
        #   reading the dicom file once it receives it detected having received it
        #   INPUT:
        #       [1] fileInterface (important class that helps us do lots of stuff)
        #       [2] filename (for the dicom file we're watching for and want to load)
        #       [3] timeout (time spent waiting for a file before timing out)
        #   OUTPUT:
        #       [1] dicomData (with class 'pydicom.dataset.FileDataset')
        print("• use 'readRetryDicomFromFileInterface' to read dicom file for",
            "TR %d " %this_TR)
        dicomData = readRetryDicomFromFileInterface(fileInterface, fileName, 
            timeout_file)

        # use 'dicomreaders.mosaic_to_nii' to convert the dicom data into a nifti
        #   object. additional steps need to be taken to get the nifti object in 
        #   the correct orientation, but we will ignore those steps here. refer to
        #   the 'advanced sample project' for more info about that
        print("| convert dicom data into a nifti object")
        niftiObject = dicomreaders.mosaic_to_nii(dicomData)
        
        # take the average of all the activation values
        avg_niftiData = np.mean(niftiObject.get_data())
        avg_niftiData = np.round(avg_niftiData,decimals=2)
        print("| average activation value for TR %d is %d" %(this_TR,avg_niftiData))

        # use 'sendResultToWeb' from 'projectUtils.py' to send the result to the
        #   web browser to be plotted in the --Data Plots-- tab.
        print("| send result to the web, plotted in the 'Data Plots' tab")
        projUtils.sendResultToWeb(projectComm, runNum, int(this_TR), int(avg_niftiData))

        # keeping track of the TRs we've already sampled
        all_avg_activations[this_TR] = avg_niftiData
        track_TRs += 1

        # create the full path filename of where we want to save vector of activations
        if this_TR < 10:
            output_binaryFilename = os.path.join(currPath,
                'tmp/avg_activations_0%d.mat' %this_TR)
        else:
            output_binaryFilename = os.path.join(currPath,
                'tmp/avg_activations_%d.mat' %this_TR)

        # save the activation values vector into a binary file, such as a numpy file,
        #   using 'putBinaryFile' in 'fileClient.py'
        #   INPUT:
        #       [1] filename (full path!)
        #       [2] data (you want to write into the filename)
        print("| save vector of activation values as a binary file in 'tmp' folder")
        fileInterface.putBinaryFile(output_binaryFilename,all_avg_activations)

    # above, we saved the activation values vector after every TR... we can verify
    #   this by taking a look at all of the files in the tmp folder using the
    #   the function 'listFiles' in 'fileClient.py'
    #   INPUT:
    #       [1] file pattern (which includes relative path)
    checking_filePattern = os.path.join(currPath,'tmp/avg_activations_*.mat')
    checking_fileList = fileInterface.listFiles(checking_filePattern)
    
    # print the list of activation files
    print(""
        "-----------------------------------------------------------------------------\n"
        "List of average activation files:")
    for i in np.arange(1,ex1_num_TRs)-1:
        print('• %s'%checking_fileList[i])

    print(""
        ".......................................................................\n"
        "As we can see, this is all redundant so we only want to save the LAST\n"
        "binary file for our purposes. Doing this, however, means that we save\n"
        "the activation values as the experiment progresses so that we have the\n"
        "values even if the experiment suddenly stops partway through.\n"
        ".......................................................................")

    print("Save the final vector of activations as a binary file in 'tmp' folder\n"
        "-----------------------------------------------------------------------------")

    # get the newest activation file
    newest_activationFile = fileInterface.getNewestFile(os.path.join(currPath,
        'tmp/avg_activations_*.mat'))
    finalOutput_binaryFilename = os.path.join(currPath,'tmp/avg_activations_ALLDATA.mat')
    fileInterface.putBinaryFile(finalOutput_binaryFilename,newest_activationFile)

    # you can use the module 'logger' to keep track of events during the experiment
    # however, let's say that you don't want to use this module but want to know that
    #   the experiment ended... you can do this by sending a text file to the 'tmp
    #   folder using the function 'putTextFile'
    #   INPUT:
    #       [1] filename (full path!)
    #       [2] data (you want to write into the filename)
    output_textFilename = os.path.join(currPath,'tmp/experiment_notes.txt')
    fileInterface.putTextFile(output_textFilename,'experiment ended!')
    print("Save message as a text file in 'tmp' folder\n"
        "-----------------------------------------------------------------------------")

    return


def main(argv=None):
    """
    This is the main function that is called when you run 'sample.py'.
    Here, you will set up an important argument parser (mostly provided by 
    the toml configuration file), initiate the class fileInterface, and then
    call the function 'doRuns' to actually start doing the experiment.
    """

    # define the parameters that will be recognized later on to set up fileIterface
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default='', type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                           help='Comma separated list of scan number')
    # This parameter is used for projectInterface
    argParser.add_argument('--commpipe', '-q', default=None, type=str,
                           help='Named pipe to communicate with projectInterface')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='retrieve dicom files from the remote server')
    args = argParser.parse_args(argv)

    # load the experiment configuration file
    cfg = loadConfigFile(args.config)

    # obtain paths for important directories (e.g. location of dicom files)
    cfg.imgDir = os.path.join(currPath, 'dicomDir')
    cfg.codeDir = currPath

    # open up the communication pipe using 'projectInterface'
    projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)
    
    # initiate the 'fileInterface' class, which will allow you to read and write 
    #   files and many other things using functions found in 'fileClient.py'
    #   INPUT:
    #       [1] args.filesremote (to retrieve dicom files from the remote server)
    #       [2] projectComm (communication pipe that is set up above)
    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

    # now that we have the necessary variables, call the function 'doRuns' in order 
    #   to actually start reading dicoms and doing your analyses of interest!
    #   INPUT:
    #       [1] cfg (configuration file with important variables)
    #       [2] fileInterface (this will allow you to call useful variables)
    #       [3] projectComm (communication pipe to talk with projectInterface)
    doRuns(cfg, fileInterface, projectComm)
    
    return 0

if __name__ == "__main__":
    """
    If 'sample.py' is called from the terminal or the equivalent, then actually go
    through all of the portions of this script. This statement is not satisfied if
    functions are called from another script using "from sample.py import FUNCTION"
    """
    main()
    sys.exit(0)
