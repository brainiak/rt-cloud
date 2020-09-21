# main script to run the processing of the experiment

import os
import glob
import numpy as np
import json	
from datetime import datetime
from dateutil import parser
from subprocess import call
import time
import nilearn
from nilearn.masking import apply_mask
from scipy import stats
import scipy.io as sio
import pickle
import nibabel as nib
import argparse
import sys
import logging
import shutil


#WHEN TESTING
#sys.path.append('/Users/amennen/github/rt-cloud/')
# UNCOMMENT WHEN NO LONGER TESTING
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
import rtCommon.utils as utils
#from rtCommon.readDicom import readDicomFromBuffer, readRetryDicomFromFileInterface
from rtCommon.imageHandling import readDicomFromBuffer, readRetryDicomFromFileInterface
from rtCommon.fileClient import FileInterface
import rtCommon.projectUtils as projUtils
from rtCommon.structDict import StructDict
#import rtCommon.dicomNiftiHandler as dnh
import rtCommon.imageHandling as ihd
from initialize import initialize
logLevel = logging.INFO

defaultConfig = os.path.join(currPath, 'conf/amygActivation.toml')


def getRegressorName(runNum):
    """"Return station classification filename"""
    # this is the actual run number, 1-based
    filename = "regressor_run-{0:02d}.mat".format(runNum)
    return filename

def makeRunReg(cfg, args, fileInterface, runNum, runFolder, saveMat=1):
    """ make regression for neurofeedback to use """
    # runIndex is 0-based, we'll save as the actual run name
    # get # TRs duration from config file
    runId = 'run-{0:02d}'.format(runNum)
    nReps = int(cfg.nReps)
    nTR_block = int(cfg.nTR_block)
    total_n_blocks = nReps*3 + 1
    total_n_TRs = total_n_blocks * nTR_block
    regressor = np.zeros((total_n_TRs,))
    # REST = 0
    # NEUROFEEDBACK = 1
    # MATH = 2
    val_dict = {}
    val_dict['REST'] = int(cfg.REST)
    val_dict['HAPPY'] = int(cfg.HAPPY)
    val_dict['MATH'] = int(cfg.MATH)
    for r in np.arange(nReps):
        first_start = r*(nTR_block*3)
        first_end = first_start + nTR_block
        regressor[first_start:first_end] = val_dict[cfg.order_block[0]]  
        regressor[first_end:first_end+nTR_block] =  val_dict[cfg.order_block[1]]  
        regressor[first_end+nTR_block:first_end+(2*nTR_block)] =  val_dict[cfg.order_block[2]]  
    # save regressor as .mat to load with display
    if saveMat:
        filename = getRegressorName(runNum)
        full_name = "{0}/{1}".format(runFolder,filename)
        regData = StructDict()
        regData.regressor = regressor
        sio.savemat(full_name, regData, appendmat=False)
        if args.filesremote:
            # save this back to local machine
            # make it into a list to use in the function
            fileList = [full_name]
            local_run_folder = os.path.join(cfg.local.subject_full_day_path, runId)
            projUtils.downloadFilesFromList(fileInterface,fileList,local_run_folder)
    # TO DO: put command here to download data to local!
    return regressor

def findConditionTR(regressor, condition):
    """ Return TRs of the given condition """
    allTRs = np.argwhere(regressor == condition)[:,0]
    return allTRs

def convertToNifti(cfg, args, TRnum, scanNum, dicomData):
    #anonymizedDicom = anonymizeDicom(dicomData) # should be anonymized already
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(TRnum).zfill(3)
    expected_dicom_name = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    if args.filesremote:
        tempNiftiDir = os.path.join(cfg.server.dataDir, 'tmp/convertedNiftis/')
    else:
        tempNiftiDir = os.path.join(cfg.local.dataDir, 'tmp/convertedNiftis')
    nameToSaveNifti = expected_dicom_name.split('.')[0] + '.nii.gz'
    fullNiftiFilename = os.path.join(tempNiftiDir, nameToSaveNifti)
    if not os.path.isfile(fullNiftiFilename): # only convert if haven't done so yet (check if doesn't exist)
        base_ROI_name = cfg.MASK[0].split('.')[0]
        reference = '{0}/{1}_space-native.nii.gz'.format(cfg.subject_reg_dir, base_ROI_name)
        fullNiftiFilename = ihd.saveAsNiftiImage(dicomData, fullNiftiFilename, cfg, reference)
    else:
        print('SKIPPING CONVERSION FOR EXISTING NIFTI {}'.format(fullNiftiFilename))
    return fullNiftiFilename

def registerMNIToNewNifti(cfg, args, full_nifti_name):
    # this will take given masks in MNI space and register to that days ex func scan

    base_nifti_name = full_nifti_name.split('/')[-1].split('.')[0]

    # (1) run mcflirt with motion correction to align ex func --> new func
    command = 'mcflirt -in {1} -reffile {0} -out {2}/ref_2_{3} -mats'.format(full_nifti_name, cfg.ref_BOLD, cfg.subject_reg_dir, base_nifti_name)
    #print('(1) ' + command)
    A = time.time()
    call(command, shell=True)
    B = time.time()
    print(B-A)

    # (2) run c3daffine tool to convert .mat to .txt
    command = 'c3d_affine_tool -ref {1} -src {0} {2}/ref_2_{3}.mat/MAT_0000 -fsl2ras -oitk {4}/ref_2_{5}.txt'.format(cfg.ref_BOLD, full_nifti_name, cfg.subject_reg_dir, base_nifti_name, cfg.subject_reg_dir, base_nifti_name)
    #print('(2) ' + command)
    A = time.time()
    call(command, shell=True)
    B = time.time()
    print(B-A)

    # (3) combine everything with ANTs call
    # input: ROI
    # reference: today's example func
    # transform MNI to T1
    # transform T1 to BOLD
    # transform BOLD to BOLD
    for m in np.arange(cfg.n_masks):
        # rerun for each mask
        if args.filesremote:
            full_ROI_path = os.path.join(cfg.server.maskDir, cfg.MASK[m])
        else:
            full_ROI_path = os.path.join(cfg.local.maskDir, cfg.MASK[m])
        base_ROI_name = cfg.MASK[m].split('.')[0]
        base_ROI_name_native = '{0}_space-native.nii.gz'.format(base_ROI_name)
        output_nifti_name = os.path.join(cfg.subject_reg_dir, base_ROI_name_native)

        command = 'antsApplyTransforms --default-value 0 --float 1 --interpolation NearestNeighbor -d 3 -e 3 --input {0} --reference-image {1} --output {2}/{3}_space-native.nii.gz  --transform {7} --transform {6} --transform {4}/ref_2_{5}.txt -v 1'.format(full_ROI_path, full_nifti_name, cfg.subject_reg_dir, base_ROI_name, cfg.subject_reg_dir, base_nifti_name, cfg.T1_to_BOLD, cfg.MNI_to_T1)
        #print('(3) ' + command)
        A = time.time()
        call(command, shell=True)
        B = time.time()
        print(B-A)

    return output_nifti_name 

def registerNewNiftiToMNI(cfg, full_nifti_name):
    # should operate over each TR
    # needs full path of nifti file to register
    base_nifti_name = full_nifti_name.split('/')[-1].split('.')[0]
    base_nifti_name_MNI = '{0}_space-MNI.nii.gz'.format(base_nifti_name)
    output_nifti_name = os.path.join(cfg.subject_reg_dir, base_nifti_name_MNI)

    if not os.path.isfile(output_nifti_name): # only run this code if the file doesn't exist already
        # (1) run mcflirt with motion correction to align to bold reference
        command = 'mcflirt -in {0} -reffile {1} -out {2}/{3}_MC -mats'.format(full_nifti_name, cfg.ref_BOLD, cfg.subject_reg_dir, base_nifti_name)
        #print('(1) ' + command)
        A = time.time()
        call(command, shell=True)
        B = time.time()
        print(B-A)

        # (2) run c3daffine tool to convert .mat to .txt
        command = 'c3d_affine_tool -ref {0} -src {1} {2}/{3}_MC.mat/MAT_0000 -fsl2ras -oitk {4}/{5}_2ref.txt'.format(cfg.ref_BOLD, full_nifti_name, cfg.subject_reg_dir, base_nifti_name, cfg.subject_reg_dir, base_nifti_name)
        #print('(2) ' + command)
        A = time.time()
        call(command, shell=True)
        B = time.time()
        print(B-A)

        # (3) combine everything with ANTs call
        command = 'antsApplyTransforms --default-value 0 --float 1 --interpolation LanczosWindowedSinc -d 3 -e 3 --input {0} --reference-image {1} --output {2}/{3}_space-MNI.nii.gz --transform {4}/{5}_2ref.txt --transform {6} --transform {7} -v 1'.format(full_nifti_name, cfg.MNI_ref_filename, cfg.subject_reg_dir, base_nifti_name, cfg.subject_reg_dir, base_nifti_name, cfg.BOLD_to_T1, cfg.T1_to_MNI)
        #print('(3) ' + command)
        A = time.time()
        call(command, shell=True)
        B = time.time()
        print(B-A)
    else:
        print('SKIPPING REGISTRATION FOR EXISTING NIFTI {}'.format(output_nifti_name))

    return output_nifti_name 

def getDicomFileName(cfg, scanNum, fileNum):
    if scanNum < 0:
        raise ValidationError("ScanNumber not supplied of invalid {}".format(scanNum))
    scanNumStr = str(scanNum).zfill(2)
    fileNumStr = str(fileNum).zfill(3)
    if cfg.dicomNamePattern is None:
        raise InvocationError("Missing config settings dicomNamePattern")
    fileName = cfg.dicomNamePattern.format(scanNumStr, fileNumStr)
    fullFileName = os.path.join(cfg.dicomDir, fileName)
    return fullFileName

def getOutputFilename(runId, TRindex):
	""""Return station classification filename"""
	filename = "percentChange_run-{0:02d}_TR-{1:03d}.txt".format(runId, TRindex)
	return filename

def getRunFilename(sessionId, runId):
	"""Return run filename given session and run"""
	filename = "patternsData_run-{0:02d}_id-{1}_py.mat".format(runId, sessionId)
	return filename

def retrieveLocalFileAndSaveToCloud(localFilePath, pathToSaveOnCloud, fileInterface):
	data = fileInterface.getFile(localFilePath)
	utils.writeFile(pathToSaveOnCloud,data)

def findBadVoxels(cfg, dataMatrix, previous_badVoxels=None):
    # remove bad voxels
    # bad voxel criteria: (1) if raw signal < 100 OR std is < 1E-3 ( I think we're going to set it equal to 0 anyway)
    # remove story TRs
    # remove story average
    std = np.std(dataMatrix, axis=1, ddof=1)
    non_changing_voxels = np.argwhere(std < 1E-3)
    low_value_voxels = np.argwhere(np.min(dataMatrix, axis=1) < 100)
    badVoxels = np.unique(np.concatenate((non_changing_voxels, low_value_voxels)))
    # now combine with previously made badvoxels
    if previous_badVoxels is not None:
        updated_badVoxels = np.unique(np.concatenate((previous_badVoxels, badVoxels)))
    else:
        updated_badVoxels = badVoxels
    return updated_badVoxels


def makeRunHeader(cfg, args, runIndex): 
    # Output header 
    now = datetime.now() 
    print('**************************************************************************************************')
    print('* amygActivation v.1.0') 
    print('* Date/Time: ' + now.isoformat()) 
    print('* Subject Number: ' + str(cfg.subjectNum)) 
    print('* Subject Name: ' + str(cfg.subjectName)) 
    print('* Run Number: ' + str(cfg.runNum[runIndex])) 
    print('* Scan Number: ' + str(cfg.scanNum[runIndex])) 
    print('* Real-Time Data: ' + str(cfg.rtData))     
    print('* Filesremote: ' + str(args.filesremote)) 
    print('* Dicom directory: ' + str(cfg.dicomDir)) 
    print('**************************************************************************************************')
    # prepare for TR sequence 
    print('{:10s}{:10s}{:10s}{:10s}'.format('run', 'filenum', 'TRindex', 'percent_change')) 
    runId = 'run-{0:02d}'.format(cfg.runNum[runIndex])
    return  runId

def makeTRHeader(cfg, runIndex, TRFilenum, TRindex, percent_change):
    print('{:<10.0f}{:<10d}{:<10d}{:<10.3f}'.format(
        cfg.runNum[runIndex], TRFilenum, TRindex, percent_change))
    return

def createRunFolder(cfg, args, runNum):
    runId = 'run-{0:02d}'.format(runNum)
    if args.filesremote:
        runFolder = os.path.join(cfg.server.subject_full_day_path, runId)
    else:
        runFolder = os.path.join(cfg.local.subject_full_day_path, runId)
    if not os.path.exists(runFolder):
        os.makedirs(runFolder)
    return runFolder

def createTmpFolder(cfg,args):
    if args.filesremote:
        tempNiftiDir = os.path.join(cfg.server.dataDir, 'tmp/convertedNiftis/')
    else:
        tempNiftiDir = os.path.join(cfg.local.dataDir, 'tmp/convertedNiftis/')
    if not os.path.exists(tempNiftiDir):
        os.makedirs(tempNiftiDir)
    print ('CREATING FOLDER %s' % tempNiftiDir)
    return

def deleteTmpFiles(cfg,args):
    if args.filesremote:
        tempNiftiDir = os.path.join(cfg.server.dataDir, 'tmp/convertedNiftis/')
    else:
        tempNiftiDir = os.path.join(cfg.local.dataDir, 'tmp/convertedNiftis')
    if os.path.exists(tempNiftiDir):
        shutil.rmtree(tempNiftiDir)
        print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        print('DELETING FOLDER AND ALL NIFTIS: tmp/convertedNiftis')
        print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
    return

def getAvgSignal(TRs_to_average, runData, TRindex, cfg):
    """Average previous data for each voxel"""
    average_signal = np.mean(runData.all_data[:, TRs_to_average], axis=1)
    if TRindex ==0 or len(runData.badVoxels) == 0:
        runData.badVoxels = findBadVoxels(cfg, runData.all_data[:, 0:TRindex+1])
    else:
        runData.badVoxels = findBadVoxels(cfg, runData.all_data[:, 0:TRindex+1], runData.badVoxels)
    if len(runData.badVoxels) > 0:
        average_signal[runData.badVoxels] = np.nan
    return average_signal, runData

def calculatePercentChange(average_data, current_data):
    """ Calculate precent signal change compared to most recent fixation block"""
    percent_change = (current_data - average_data)/average_data
    avg_percent_change = np.nanmean(percent_change)*100
    if avg_percent_change < 0:
        avg_percent_change = 0
    return avg_percent_change

def split_tol(test_list, tol): 
    res = [] 
    last = test_list[0] 
    for ele in test_list: 
        if ele-last > tol: 
            yield res 
            res = [] 
        res.append(ele) 
        last = ele 
    yield res 

# testing code--debug mode -- run in amygActivation directory
# from amygActivation import *
# defaultConfig = 'conf/sampleCfg.toml'
# args = StructDict({'config':defaultConfig, 'runs': '1', 'scans': '9', 'commpipe': None, 'filesremote': True})
# runIndex=0
# TRFilenum=9

def main():
    logger = logging.getLogger()
    logger.setLevel(logLevel)
    logging.info('amygActivation: first log message!')
    argParser = argparse.ArgumentParser()
    argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
                       help='experiment config file (.json or .toml)')
    argParser.add_argument('--runs', '-r', default='', type=str,
                       help='Comma separated list of run numbers')
    argParser.add_argument('--scans', '-s', default='', type=str,
                       help='Comma separated list of scan number')
    # creates pipe communication link to send/request responses through web pipe
    argParser.add_argument('--commpipe', '-q', default=None, type=str,
                       help='Named pipe to communicate with projectInterface')
    argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
                       help='dicom files retrieved from remote server')
    argParser.add_argument('--deleteTmpNifti', '-d', default='1', type=str,
                       help='Set to 0 if rerunning during a single scanning after error')

    args = argParser.parse_args()
    print(args)
    cfg = utils.loadConfigFile(args.config)
    cfg = initialize(cfg, args)

    
    # DELETE ALL FILES IF FLAGGED (DEFAULT) # 
    if args.deleteTmpNifti == '1':
        deleteTmpFiles(cfg,args)
    else:
        print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        print('NOT DELETING NIFTIS IN tmp/convertedNiftis')
        print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')

    createTmpFolder(cfg,args)
    # comm pipe
    projComm = projUtils.initProjectComm(args.commpipe, args.filesremote)
    fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projComm)
    # intialize watching in particular directory
    fileInterface.initWatch(cfg.dicomDir, cfg.dicomNamePattern, cfg.minExpectedDicomSize) 

    #### MAIN PROCESSING ###
    nRuns = len(cfg.runNum)
    for runIndex in np.arange(nRuns):
        # Steps that we have to do:
        # 1. load run regressor X - ** make run regressor that has TRs - 
        # 2. find the happy face trials (happy) X
        # 3. find the rest TRs right before each one  X
        # At every TR --> register to MNI, mask, etc
        # 4. zscore previous rest data (convert + register like before)
        # 5. calculate percent signal change over ROI
        # 6. save as a text file (Every TR-- display can smooth it)
        
        runNum = cfg.runNum[runIndex]# this will be 1-based now!! it will be the actual run number in case it's out of order
        runId = makeRunHeader(cfg, args, runIndex)
        run = cfg.runNum[runIndex]
        # create run folder
        runFolder = createRunFolder(cfg, args, runNum)
        scanNum = cfg.scanNum[runIndex]
        regressor = makeRunReg(cfg, args, fileInterface, runNum, runFolder, saveMat=1)

        happy_TRs = findConditionTR(regressor,int(cfg.HAPPY))
        happy_TRs_shifted = happy_TRs  + cfg.nTR_shift
        happy_TRs_shifted_filenum = happy_TRs_shifted + cfg.nTR_skip # to account for first 10 files that we're skipping
        happy_blocks = list(split_tol(happy_TRs_shifted,1)) 
        TR_per_block = cfg.nTR_block

        fixation_TRs = findConditionTR(regressor,int(cfg.REST)) 
        fixation_TRs_shifted = fixation_TRs + cfg.nTR_shift
        fixation_blocks = list(split_tol(fixation_TRs_shifted,1)) 

        runData = StructDict()
        runData.all_data = np.zeros((cfg.nVox[cfg.useMask], cfg.nTR_run - cfg.nTR_skip))
        runData.percent_change = np.zeros((cfg.nTR_run - cfg.nTR_skip,))
        runData.percent_change[:] = np.nan
        runData.badVoxels = np.array([])
        
        TRindex = 0
        for TRFilenum in np.arange(cfg.nTR_skip+1, cfg.nTR_run+1): # iterate through all TRs
            if TRFilenum == cfg.nTR_skip+1: # wait until run starts
                timeout_file = 180
            else:
                timeout_file = 5
            A = time.time()
            dicomData = readRetryDicomFromFileInterface(fileInterface, getDicomFileName(cfg, scanNum, TRFilenum), timeout=timeout_file)
            full_nifti_name = convertToNifti(cfg, args, TRFilenum, scanNum, dicomData)
            print(full_nifti_name)
            print(cfg.MASK_transformed[cfg.useMask])
            maskedData = apply_mask(full_nifti_name, cfg.MASK_transformed[cfg.useMask])
            runData.all_data[:, TRindex] = maskedData
            B = time.time()
            print('read to mask time: {:5f}'.format(B-A))

            if TRindex in happy_TRs_shifted: # we're at a happy block
                # now take previous fixation block for z scoring 
                this_block = [b for b in np.arange(4) if TRindex in happy_blocks[b]][0]
                fixation_this_block = fixation_blocks[this_block]
                avg_activity, runData = getAvgSignal(fixation_this_block, runData, TRindex, cfg)
                runData.percent_change[TRindex] = calculatePercentChange(avg_activity, runData.all_data[:, TRindex])
                
                text_to_save = '{0:05f}'.format(runData.percent_change[TRindex])
                file_name_to_save = getOutputFilename(run, TRFilenum) # save as the actual file number, not index
                # now we want to always send this back to the local computer running the display
                full_file_name_to_save =  os.path.join(cfg.local.subject_full_day_path, runId, file_name_to_save)
                # Send classification result back to the console computer
                fileInterface.putTextFile(full_file_name_to_save, text_to_save)
                if args.commpipe:    
                    # JUST TO PLOT ON WEB SERVER
                    projUtils.sendResultToWeb(projComm, run, int(TRFilenum), runData.percent_change[TRindex])
            TRheader = makeTRHeader(cfg, runIndex, TRFilenum, TRindex, runData.percent_change[TRindex])
            TRindex += 1


        # SAVE OVER RUN 
        runData.scanNum = scanNum # save scanning number
        runData.subjectName = cfg.subjectName
        runData.dicomDir = cfg.dicomDir
        run_filename = getRunFilename(cfg.sessionId, run)
        full_run_filename_to_save = os.path.join(runFolder, run_filename)
        sio.savemat(full_run_filename_to_save, runData, appendmat=False)
    
    sys.exit(0)

if __name__ == "__main__":
    # execute only if run as a script
    main()
