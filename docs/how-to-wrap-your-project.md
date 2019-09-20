## Making your project cloud enabled
Make a new directory under rt-cloud/projects for your project.
Use the sample project in rt-cloud/projects/sample as a template for making your python script cloud enabled. The sample.py script corresponds to the script for your experiment, and the projectMain.py script can be copied to your project directory and edit one line 'scriptToRun' to point to your script.

### Project Code
You'll need to copy several blocks of code to your project to get it cloud enabled. These are:

Accept at least the following command line parameters in your project python file:

    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                           help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default='', type=str,
                           help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                           help='Comma separated list of scan number')
    # This parameter is used by projectInterface
    argParser.add_argument('--commpipe', '-q', default=None, type=str,
                           help='Named pipe to communicate with projectInterface')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                           help='retrieve dicom files from the remote server')
    args = argParser.parse_args()

Set up communication with the projectInterface

    projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)

Open a FileInterface object for reading and writing files

    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

Then within your python script, use the FileInterface object to request remote files. For example to retrieve dicom images as they are created, init a watch on the appropriate directory and then watch for them.

    fileInterface.initWatch('/tmp/dicoms', 'samp*.dcm', minFileSize)
    rawData = fileInterface.watchFile('/tmp/samp3.dcm')

Or use the readRetryDicom helper function which returns the Dicom image data

    fileInterface.initWatch('/tmp/dicoms', 'samp*.dcm', minFileSize)
    dicomData = readRetryDicomFromFileInterface(fileInterface, 'samp3.dcm', timeout=10)

Write classification results back to the console computer using putTextFile

    fileInterface.putTextFile(fullpath_filename_to_save, text_to_save)

Read files from the console computer using getFile

    data = fileInterface.getFile(fullpath_filename)

Or read the newest file matching a file pattern such as 'samp*.dcm'

    data = fileInterface.getNewestFile(fullpath_filepattern)

Send data values to be graphed in the projectInterface web page

    projUtils.sendResultToWeb(projectComm, run, tr, val)

### Project Configuration
Use a TOML file for configuration settings. Use the loadConfigFile funtion to load your configurations into a structured object

    import rtCommon.utils as utils
    cfg = utils.loadConfigFile(args.config)

Access configurations within the config structure

    print(cfg.subjectName, cfg.subjectDay)

The following fields must be present in the config toml file for the projectInterface to work:
  - runNum = [1]    # an array with one or more run numbers e.g. [1, 2, 3]
  - scanNum = [11]  # an array with one or more scan numbers e.g.  [11, 13, 15]
  - subjectName = 'subject01'
  - subjectDay = 1

  Optional Parameters:
  - title = 'Project Title'
  - plotTitle = 'Plot Title'
  - plotXLabel = 'Sample #'
  - plotYLabel = 'Value'
  - plotXRangeLow = 0
  - plotXRangeHigh = 20
  - plotYRangeLow = -1
  - plotYRangeHigh = 1
