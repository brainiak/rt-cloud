# common.py
# Constants and functions shared by tests

import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

""" Imaging inputs """
test_inputDirName = 'test_input'
test_dicomFile = '001_000013_000005.dcm'
test_dicomTruncFile = 'trunc_001_000013_000005.dcm'
test_nifti1_3DFile = 'test_input_3d_func_ses-01_task-story_run-01_bold.nii'
test_nifti2_3DFile = \
    'test_input_3d_nifti2_func_ses-01_task-story_run-01_bold.nii'
test_nifti1_4DFile = 'test_input_4d_func_ses-01_task-story_run-01_bold.nii'
test_nifti2_4DFile = \
    'test_input_4d_nifti2_func_ses-01_task-story_run-01_bold.nii'

# absolute paths derived from above names
testPath = os.path.dirname(__file__)
rtCloudPath = os.path.dirname(testPath)
test_inputDirPath = os.path.join(testPath, test_inputDirName)
test_dicomPath = os.path.join(test_inputDirPath, test_dicomFile)
test_dicomTruncPath = os.path.join(test_inputDirPath, test_dicomTruncFile)
test_3DNifti1Path = os.path.join(test_inputDirPath, test_nifti1_3DFile)
test_3DNifti2Path = os.path.join(test_inputDirPath, test_nifti2_3DFile)
test_4DNifti1Path = os.path.join(test_inputDirPath, test_nifti1_4DFile)
test_4DNifti2Path = os.path.join(test_inputDirPath, test_nifti2_4DFile)

# test constants
testPort = 8921
tmpDir = tempfile.gettempdir()

def isValidBidsArchive(archivePath: str, logFullOutput: bool = False) -> bool:
    result = subprocess.run(['which', 'bids-validator'], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    if result.returncode != 0:
        raise FileNotFoundError("Failed to find path to bids-validator binary. "
                                "Ensure bids-validator is installed globally. "
                                "(run 'npm install -g bids-validator')")

    binary_path = result.stdout.decode('utf-8').strip()

    cmd = [str(binary_path),  '--json', archivePath]
    result = subprocess.run(cmd, stdout=subprocess.PIPE)

    dictResult = json.loads(result.stdout)
    if logFullOutput:
        logger.debug("bids-validator full output:\n\n%s",
                     json.dumps(dictResult, indent=4))

    errors = dictResult['issues']['errors']
    warnings = dictResult['issues']['warnings']

    def makeIssueNameToFileMapping(issueDict: dict):
        # Make mapping from issue name to filenames involved in that issue
        #
        # Underlying JSON schema is a list of dictionaries, each holding info
        # about one key. Each dictionary in the list has a 'files' attribute
        # which holds a list of the offending files, each file represented by a
        # dictionary.  Thus, one must access a subproperty ('name') of that
        # dictionary to actually get the offending filename.
        issueKeysToFiles = {}

        for issue in issueDict:
            issueFiles = issue['files']
            # For the short README error, the file list is empty; other errors
            # may also have an empty file list, so check to make sure the file
            # is non-None before trying to get its name
            offendingFileNames = [f['file']['name'] for f in issueFiles if
                                  f['file'] is not None]
            issueKey = '{key} (Reason: {reason})'.format(key=issue['key'],
                                                         reason=issue['reason'])
            issueKeysToFiles[issueKey] = offendingFileNames

        return issueKeysToFiles

    # Check for errors -- fail if have any
    if len(errors) > 0:
        errorKeysToFiles = makeIssueNameToFileMapping(errors)
        logger.error("bids-validator returned %d errors:\n%s",
                     len(errors), json.dumps(errorKeysToFiles, indent=4,
                                             sort_keys=True))
        return False

    # Check for warnings -- log if have any
    if len(warnings) > 0:
        warningKeysToFiles = makeIssueNameToFileMapping(warnings)
        logger.warning("bids-validator returned 0 errors, %d warnings:\n%s",
                       len(warnings), json.dumps(warningKeysToFiles, indent=4,
                                                 sort_keys=True))

    return True
