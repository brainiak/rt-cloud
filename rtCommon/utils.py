"""
Utils - various utilites for rtfMRI
"""

import os
import io
import re
import json
import toml
import time
import glob
import shutil
import subprocess
import pathlib
import logging
import numpy as np  # type: ignore
import scipy.io as sio  # type: ignore
from .structDict import MatlabStructDict, isStructuredArray, recurseCreateStructDict
from .errors import InvocationError


class TooManySubStructsError(ValueError):
    pass


def parseMatlabStruct(top_struct) -> MatlabStructDict:
    '''Load matlab data file and convert it to a MatlabStructDict object for
       easier python access. Expect only one substructure array, and use that
       one as the name variable in MatlabStructDict.
       Return the MatlabStructDict object
        '''
    substruct_names = [key for key in top_struct.keys() if isStructuredArray(top_struct[key])]
    # if len(substruct_names) > 1:
    #     # Currently we only support one sub structured array
    #     raise TooManySubStructsError(
    #         "Too many substructs: {}".format(substruct_names))
    substruct_name = substruct_names[0] if len(substruct_names) > 0 else None
    matstruct = MatlabStructDict(top_struct, substruct_name)
    return matstruct


def loadMatFile(filename: str) -> MatlabStructDict:
    if not os.path.isfile(filename):
        raise FileNotFoundError("File \'{}\' not found".format(filename))
    top_struct = sio.loadmat(filename)
    return parseMatlabStruct(top_struct)


def loadMatFileFromBuffer(data) -> MatlabStructDict:
    dataBytesIO = io.BytesIO(data)
    top_struct = sio.loadmat(dataBytesIO)
    return parseMatlabStruct(top_struct)


def find(A: np.ndarray) -> np.ndarray:
    '''Find nonzero elements of A in flat "C" row-major indexing order
       but sorted as in "F" column indexing order'''
    # find indices of non-zero elements in roi
    inds = np.nonzero(A)
    dims = A.shape
    # First convert to Matlab column-order raveled indicies in order to sort
    #   the indicies to match the order the data appears in the p.raw matrix
    indsMatRavel = np.ravel_multi_index(inds, dims, order='F')
    indsMatRavel.sort()
    # convert back to python raveled indices
    indsMat = np.unravel_index(indsMatRavel, dims, order='F')
    resInds = np.ravel_multi_index(indsMat, dims, order='C')
    return resInds


def loadConfigFile(filename):
    file_suffix = pathlib.Path(filename).suffix
    if file_suffix == '.json':
        # load json
        with open(filename) as fp:
            cfg_dict = json.load(fp)
        # to write out config
        # with open('t1.json', 'w+') as fd:
        #   json.dump(cfg, fd, indent=2)
    elif file_suffix == '.toml':
        # load toml
        cfg_dict = toml.load(filename)
        # to write out config
        # with open('t1.toml', 'w+') as fd:
        #  toml.dump(cfg, fd)
    else:
        raise InvocationError("experiment file requires to be .json or .toml")
    cfg_struct = recurseCreateStructDict(cfg_dict)
    return cfg_struct


def findNewestFile(filepath, filepattern):
    '''Find newest file matching pattern according to filesystem creation time.
       Return the filename
    '''
    full_path_pattern = ''
    if os.path.basename(filepattern) == filepath:
        # filepattern has the full path in it already
        full_path_pattern = filepattern
    elif os.path.basename(filepattern) == '':
        # filepattern doesn't have the file path in it yet
        # concatenate file path to filepattern
        full_path_pattern = os.path.join(filepath, filepattern)
    else:
        # base of filepattern and filepath don't seem to match, raise error?
        # for now concatenate them also
        full_path_pattern = os.path.join(filepath, filepattern)

    try:
        return max(glob.iglob(full_path_pattern), key=os.path.getctime)
    except ValueError:
        return None


def flatten_1Ds(M):
    if 1 in M.shape:
        newShape = [x for x in M.shape if x > 1]
        M = M.reshape(newShape)
    return M


def dateStr30(timeval):
    return time.strftime("%Y%m%dT%H%M%S", timeval)


def copyFileWildcard(src, dst):
    count = 0
    for filename in glob.glob(src):
        count += 1
        shutil.copy(filename, dst)
    if count == 0:
        raise FileNotFoundError("No files matching pattern {}".format(src))
    return


def fileCount(dir, pattern):
    count = sum(1 for _ in glob.iglob(os.path.join(dir, pattern)))
    return count


def writeFile(filename, data, binary=True):
    mode = 'wb'
    if binary is False:
        mode = 'w'
    dirName = os.path.dirname(filename)
    if not os.path.exists(dirName):
        os.makedirs(dirName)
    with open(filename, mode) as fh:
        bytesWritten = fh.write(data)
        if bytesWritten != len(data):
            raise InterruptedError("Write file %s wrote %d of %d bytes" % (filename, bytesWritten, len(data)))


def readFile(filename, binary=True):
    mode = 'rb'
    if binary is False:
        mode = 'r'
    with open(filename, mode) as fp:
        data = fp.read()
    return data


def runCmdCheckOutput(cmd, outputRegex):
    match = False
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for bline in iter(proc.stdout.readline, b''):
        line = bline.decode('utf-8').rstrip()
        print(line)
        # check if line has the search string in it
        if re.search(outputRegex, line, re.IGNORECASE):
            match = True
    return match


def demoDelay(demoStep, prevEventTime):
    '''Given demoStep in seconds, calculate how long to sleep until the next
       clock cycle will be reached that is an even value of demoStep.
       Then sleep that amount of time.
       If prevEventTime is specified and we are more than 1 demo step since the
       prevEvent then don't sleep.
    '''
    now = time.time()
    if (now > prevEventTime + demoStep) or (demoStep == 0):
        return now
    # Calculate and sleep until next even demoStep
    # Convert to miliseconds
    step_ms = demoStep * 1000
    now_ms = now * 1000
    sleep_ms = step_ms - (now_ms % step_ms)
    sleep_sec = sleep_ms / 1000
    nextEventTime = now + sleep_sec
    time.sleep(sleep_sec)
    return nextEventTime


class DebugLevels:
    L1  = 19 # least verbose
    L2  = 18
    L3  = 17
    L4  = 16
    L5  = 15
    L6  = 14
    L7  = 13
    L8  = 12
    L9  = 11
    L10 = 10 # most verbose


def installLoggers(consoleLevel, fileLevel, filename=None):
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    logger = logging.getLogger()
    hasFileHandler = False
    hasConsoleHandler = False
    if filename is not None:
        dir = os.path.dirname(filename)
        if dir not in (None, ''):
            if not os.path.exists(dir):
                os.makedirs(dir)

    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler):
            # print("Has FileHandler")
            hasFileHandler = True
            handler.setLevel(fileLevel)
        if isinstance(handler, logging.StreamHandler):
            # print("Has StreamHandler")
            hasConsoleHandler = True
            handler.setLevel(consoleLevel)
    if not hasConsoleHandler:
        # print("Create StreamHandler")
        consoleLogger = logging.StreamHandler()
        consoleLogger.setLevel(consoleLevel)
        logger.addHandler(consoleLogger)
    if not hasFileHandler and filename is not None:
        # print("Create FileHandler")
        fileLogger = logging.FileHandler(filename)
        fileLogger.setLevel(fileLevel)
        fileLogger.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(message)s'))
        logger.addHandler(fileLogger)


# define as global variable
gitCodeId = None


def getGitCodeId():
    global gitCodeId
    if gitCodeId is None:
        branchB = subprocess.check_output(['bash', '-c', 'git symbolic-ref --short -q HEAD'])
        branchName = branchB.decode("utf-8").rstrip()
        commitB = subprocess.check_output(['bash', '-c', 'git rev-parse --short HEAD'])
        commitId = commitB.decode("utf-8").rstrip()
        gitCodeId = branchName + ":" + commitId
    return gitCodeId


'''
import inspect  # type: ignore
def xassert(bool_val, message):
    print("in assert")
    if bool_val is False:
        frame = inspect.currentframe()
        xstr = "File: {}, Line: {} AssertionFailed: {}"\
            .format(os.path.basename(frame.f_code.co_filename),
                    frame.f_lineno, message)
        assert False, xstr
'''
