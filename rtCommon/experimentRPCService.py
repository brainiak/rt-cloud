"""This module provides the RPC server that provides communication services to the experiment script."""
import rpyc
from rpyc.utils.server import ThreadedServer
from rpyc.utils.helpers import classpartial
from rtCommon.fileInterface import FileInterface
from rtCommon.subjectInterface import SubjectInterface


class ExperimentRPCService(rpyc.Service):
    """
    Provides Remote Procedure Call service for the experimenter's script. This service runs
    in the projectServer to receive and handle RPC requests from the experimenter script.
    It exports a FileInterface and SubjectInterface.
    """
    exposed_FileInterface = None
    exposed_SubjectInterface = None

    def __init__(self, filesRemote = False):
        ExperimentRPCService.exposed_FileInterface = FileInterface(filesRemote)
        ExperimentRPCService.exposed_SubjectInterface = SubjectInterface()

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass


def startExperimentRPCThread(filesRemote=False, hostname=None, port=12345):
    """
    This function starts the Experiment RPC server for communication between the projectServer
        and the experiment script. It does not return.
    """
    safe_attrs = rpyc.core.protocol.DEFAULT_CONFIG.get('safe_attrs')
    safe_attrs.add('__format__')
    serviceWithArgs = classpartial(ExperimentRPCService, filesRemote=filesRemote)
    threadId = ThreadedServer(serviceWithArgs, hostname=hostname, port=port,
                              protocol_config={
                                  "allow_public_attrs": True,
                                  "safe_attrs": safe_attrs,
                                  # "allow_all_attrs": True,
                                  # "allow_getattr": True,
                                  # "allow_setattr": True,
                                  # "allow_pickle" : True,
                                  })
    threadId.start()


# Generic start RPC Thread routine
def startRPCThread(service, hostname=None, port=23456):
    threadId = ThreadedServer(service, hostname=hostname, port=port,
                              protocol_config={'allow_public_attrs': True,})
    threadId.start()



# Current remote request types that need to be supported
# getFile(filename, compress=False)
# getNewestFile(filename, compress=False)
# listFiles(filePattern)
# allowedFileTypes()
# initWatch(dir, filePattern, minFileSize, demoStep=0)
# watchFile(filename, timeout=5, compress=False)
# readRetryDicom(filename, timeout)
# putTextFile(filename, str)
# putBinary(filename)
# uploadFolderToCloud(fileInterface, srcDir, outputDir)
# uploadFilesToCloud(fileInterface, srcFilePattern, outputDir)
# uploadFilesFromList(fileInterface, fileList, outputDir, srcDirPrefix=None)
# downloadFolderFromCloud(fileInterface, srcDir, outputDir, deleteAfter=False)
# downloadFilesFromCloud(fileInterface, srcFilePattern, outputDir, deleteAfter=False)
# downloadFilesFromList(fileInterface, fileList, outputDir, srcDirPrefix=None)
# deleteFilesFromList(fileList)

# sendClassificationResult(runId, trId, value)