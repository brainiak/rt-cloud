"""This module provides the RPC server that provides communication services to the experiment script."""
import rpyc
from rpyc.utils.server import ThreadedServer
from rpyc.utils.helpers import classpartial
from rtCommon.dataInterface import DataInterface
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.webDisplayInterface import WebDisplayInterface
from rtCommon.errors import StateError, RequestError


class ProjectRPCService(rpyc.Service):
    """
    Provides Remote Procedure Call service for the experimenter's script. This service runs
    in the projectServer to receive and handle RPC requests from the experimenter script.
    It exports a DataInterface and SubjectInterface.
    """
    exposed_DataInterface = None
    exposed_SubjectInterface = None
    exposed_BidsInterface = None
    exposed_WebDisplayInterface = None

    def __init__(self, dataRemote=False, subjectRemote=False, webUI=None):
        self.dataRemote = dataRemote
        self.subjectRemote = subjectRemote
        allowedDirs = None
        allowedFileTypes = None
        if dataRemote is False:
            # Allow all file types and directories for local filesystem access
            allowedDirs=['*']
            allowedFileTypes=['*']

        ProjectRPCService.exposed_DataInterface = DataInterface(dataRemote=dataRemote,
                                                                allowedDirs=allowedDirs,
                                                                allowedFileTypes=allowedFileTypes)
        ProjectRPCService.exposed_BidsInterface = BidsInterface(dataRemote=dataRemote)
        ProjectRPCService.exposed_SubjectInterface = SubjectInterface(subjectRemote=subjectRemote)
        ProjectRPCService.exposed_WebDisplayInterface = webUI

    def exposed_isDataRemote(self):
        return self.dataRemote

    def exposed_isSubjectRemote(self):
        return self.subjectRemote

    @staticmethod
    def registerDataCommFunction(commFunction):
        if (ProjectRPCService.exposed_DataInterface is None and
            ProjectRPCService.exposed_BidsInterface is None):
            raise StateError("ServerRPC no dataInterface instatiated yet")
        if ProjectRPCService.exposed_DataInterface is not None:
            ProjectRPCService.exposed_DataInterface.registerCommFunction(commFunction)
        if ProjectRPCService.exposed_BidsInterface is not None:
            ProjectRPCService.exposed_BidsInterface.registerCommFunction(commFunction)

    @staticmethod
    def registerSubjectCommFunction(commFunction):
        if ProjectRPCService.exposed_SubjectInterface is None:
            raise StateError("exposed_SubjectInterface not instatiated yet")
        ProjectRPCService.exposed_SubjectInterface.registerCommFunction(commFunction)

    def on_connect(self, conn):
        pass

    def on_disconnect(self, conn):
        pass


def startRPCThread(rpcService, hostname=None, port=12345):
    """
    This function starts the Project RPC server for communication between the projectServer
        and the experiment script. 
        IT DOES NOT RETURN.
    """
    safe_attrs = rpyc.core.protocol.DEFAULT_CONFIG.get('safe_attrs')
    safe_attrs.add('__format__')
    # If init ThreadedServer with a class (or classpartial with args to fill in) then each 
    #  client will get it's own instance. If an instance is passed in then all clients
    #  will share that instance.
    # For non-shared case
    # serviceWithArgs = classpartial(ProjectRPCService, dataRemote=dataRemote)
    # rpcService = ProjectRPCService(dataRemote, dataCommFunc)

    threadId = ThreadedServer(rpcService, hostname=hostname, port=port,
                              protocol_config={
                                  "allow_public_attrs": True,
                                  "safe_attrs": safe_attrs,
                                  "allow_pickle" : True,
                                  # "allow_getattr": True,
                                  # "allow_setattr": True,
                                  # "allow_delattr": True,
                                  # "allow_all_attrs": True,
                                  })
    threadId.start()
    return rpcService


# # Generic start RPC Thread routine
# def startRPCThread(service, hostname=None, port=23456):
#     threadId = ThreadedServer(service, hostname=hostname, port=port,
#                               protocol_config={'allow_public_attrs': True,})
#     threadId.start()


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
# uploadFolderToCloud(dataInterface, srcDir, outputDir)
# uploadFilesToCloud(dataInterface, srcFilePattern, outputDir)
# uploadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=None)
# downloadFolderFromCloud(dataInterface, srcDir, outputDir, deleteAfter=False)
# downloadFilesFromCloud(dataInterface, srcFilePattern, outputDir, deleteAfter=False)
# downloadFilesFromList(dataInterface, fileList, outputDir, srcDirPrefix=None)
# deleteFilesFromList(fileList)

# sendClassificationResult(runId, trId, value)
