# Purpose: get experiment ready

import os
import glob
import numpy as np
from subprocess import call
import time
import nilearn
from scipy import stats
import scipy.io as sio
import pickle
import nibabel as nib
import argparse
import random
import sys
from datetime import datetime
from dateutil import parser

# WHEN TESTING - COMMENT OUT
currPath = os.path.dirname(os.path.realpath(__file__))
rootPath = os.path.dirname(os.path.dirname(currPath))
sys.path.append(rootPath)
#WHEN TESTING: UNCOMMENT TO ADD PATH TO RT-CLOUD
#sys.path.append('/Users/amennen/github/rt-cloud/')
#sys.path.append('/jukebox/norman/amennen/github/brainiak/rt-cloud/')

import rtCommon.utils as utils
from rtCommon.fileClient import FileInterface
import rtCommon.projectUtils as projUtils
from rtCommon.structDict import StructDict
#from rtCommon.dicomNiftiHandler import getTransform
from rtCommon.imageHandling import getTransform
from projects.amygActivation.initialize import initialize
from projects.amygActivation.amygActivation import getRunFilename

# obtain the full path for the configuration toml file
defaultConfig = os.path.join(currPath, 'conf/amygActivation.toml')

def finalize(cfg, args):
	# first find the number of runs completed
	run_path = os.path.join(cfg.local.subject_full_day_path, 'run*')
	if args.filesremote:
		run_path = os.path.join(cfg.server.subject_full_day_path, 'run*')
	nRuns_completed = len(glob.glob(run_path))
	return nRuns_completed

def main(argv=None):
	"""
	This is the main function that is called when you run 'finialize.py'.

	Here, you will load the configuration settings specified in the toml configuration 
	file, initiate the class fileInterface, and set up some directories and other 
	important things through 'finalize()'
	"""

	# define the parameters that will be recognized later on to set up fileIterface
	argParser = argparse.ArgumentParser()
	argParser.add_argument('--config', '-c', default=defaultConfig, type=str,
						   help='experiment config file (.json or .toml)')
	# This parameter is used for projectInterface
	argParser.add_argument('--commpipe', '-q', default=None, type=str,
						   help='Named pipe to communicate with projectInterface')
	argParser.add_argument('--filesremote', '-x', default=False, action='store_true',
						   help='retrieve files from the remote server')
	argParser.add_argument('--addr', '-a', default='localhost', type=str, 
			   help='server ip address')
	argParser.add_argument('--runs', '-r', default='', type=str,
					   help='Comma separated list of run numbers')
	argParser.add_argument('--scans', '-s', default='', type=str,
					   help='Comma separated list of scan number')
	args = argParser.parse_args(argv)

	# load the experiment configuration file
	cfg = utils.loadConfigFile(args.config)
	cfg = initialize(cfg, args)
	print(args.config)
	nRunsCompleted = finalize(cfg,args)
	# copy subject folders from server to local
	# subject-specific folder
	# everything in temp/convertedNiftis
	if args.filesremote:

		# open up the communication pipe using 'projectInterface'
		projectComm = projUtils.initProjectComm(args.commpipe, args.filesremote)

		# initiate the 'fileInterface' class, which will allow you to read and write 
		#   files and many other things using functions found in 'fileClient.py'
		#   INPUT:
		#       [1] args.filesremote (to retrieve dicom files from the remote server)
		#       [2] projectComm (communication pipe that is set up above)
		fileInterface = FileInterface(filesremote=args.filesremote, commPipes=projectComm)

		# we don't need the tmp/convertedNiftis so first remove those
		tempNiftiDir = os.path.join(cfg.server.dataDir, 'tmp/convertedNiftis/')
		if os.path.exists(tempNiftiDir):
			projUtils.deleteFolder(tempNiftiDir)
			print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
			print('deleting temporary convertedNifti folder: ', tempNiftiDir)
			print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
		# next, go through each run and put each run data into local run folder
		for r in np.arange(nRunsCompleted):
			runNum = r + 1 # run numbers start at 1
			runId = 'run-{0:02d}'.format(runNum)
			runFolder = os.path.join(cfg.server.subject_full_day_path, runId, '*')
			listOfFiles = glob.glob(runFolder)
			runFolder_local = os.path.join(cfg.local.subject_full_day_path, runId)
			projUtils.downloadFilesFromList(fileInterface, listOfFiles, runFolder_local)
			print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
			print('downloading data to local computer: ', runFolder)
		# next delete the entire subject folder on the cloud
		# MAKE SURE THIS IS CORRECT FOR YOUR EXPERIMENT BEFORE YOU RUN
		subject_dir = os.path.join(cfg.server.dataDir, cfg.bids_id)
		print('FOLDER TO DELETE ON CLOUD SERVER: ', subject_dir)
		print('IF THIS IS CORRECT, GO BACK TO THE CONFIG FILE USED ON THE WEB SERBER COMPUTER AND CHANGE THE FLAG FROM false --> true IN [server] deleteAfter')
		if cfg.server.deleteAfter:
			print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
			print('DELETING SUBJECT FOLDER ON CLOUD SERVER: ', subject_dir)
			print('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
			if os.path.exists(subject_dir):
				projUtils.deleteFolder(subject_dir)

	return 0

if __name__ == "__main__":
	"""
	If 'finalize.py' is invoked as a program, then actually go through all of the 
	portions of this script. This statement is not satisfied if functions are called 
	from another script using "from finalize.py import FUNCTION"
	"""    
	main()
	sys.exit(0)
