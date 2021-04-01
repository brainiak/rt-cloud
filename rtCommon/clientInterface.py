"""
This module will be imported by the experiment script (i.e. client) running in the cloud and
provide the interfaces for all functionality provided to the client by the rt-cloud
projectServer.

The client script instantiates a clientInterface object. It will automatically connect
to the projectServer running on the localhost (i.e. same host as the client). If a
connection is established the interfaces listed below will be stubs that forward requests
to remote servers that will handle the requsts. If the connection fails (i.e. there is no
projectServer running), then local versions of the services will be instantiated, for example
to access local files instead of remote files. The user will be prompted if local versions
will be used.

Client Service Interfaces provided (i.e. for the classification script client):
    dataInterface - to read and write files from the remote server
    subjectInterface - to send subject feedback and receive responses
    webInterface - to set browser messages, update plots, send/receive configs
"""
import rpyc
from rtCommon.dataInterface import DataInterface
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.webDisplayInterface import WebDisplayInterface
from rtCommon.bidsInterface import BidsInterface
from rtCommon.exampleInterface import ExampleInterface
from rtCommon.errors import RequestError


class ClientInterface:
    """
    This class provides the API that an experiment script can use to communicate with the
    project server. It provides both a DataInterface for reading or writing files, and a
    SubjectInterface for sending/receiving feedback and response to the subject in the MRI scanner.
    """
    def __init__(self, rpyc_timeout=60, yesToPrompts=False):
        """
        Establishes an RPC connection to a localhost projectServer on a predefined port.
        The projectServer must be running on the same computer as the script using this interface.
        """
        try:
            safe_attrs = rpyc.core.protocol.DEFAULT_CONFIG.get('safe_attrs')
            safe_attrs.add('__format__')
            rpcConn = rpyc.connect('localhost', 12345,
                                   config={
                                            "allow_public_attrs": True,
                                            "safe_attrs": safe_attrs,
                                            "allow_pickle" : True,
                                            "sync_request_timeout": rpyc_timeout,
                                            # "allow_getattr": True,
                                            # "allow_setattr": True,
                                            # "allow_delattr": True,
                                            # "allow_all_attrs": True,
                                           })
            # Need to provide an override class of DataInstance to return data from getImage
            self.dataInterface = WrapRpycObject(rpcConn.root.DataInterface)
            self.subjInterface = WrapRpycObject(rpcConn.root.SubjectInterface)
            self.bidsInterface = WrapRpycObject(rpcConn.root.BidsInterface)
            self.exampleInterface = WrapRpycObject(rpcConn.root.ExampleInterface)
            # WebDisplay is always run within the projectServer (i.e. not a remote service)
            self.webInterface = rpcConn.root.WebDisplayInterface
            self.rpcConn = rpcConn
        except ConnectionRefusedError as err:
            if yesToPrompts:
                print('Unable to connect to projectServer, continuing using localfiles')
                reply = 'y'
            else:
                reply = input('Unable to connect to projectServer, continue using localfiles? ' + '(y/n): ')
            reply.lower().strip()
            if reply[0] == 'y':
                # These will be run in the same process as the experiment script
                self.dataInterface = DataInterface(dataRemote=False, allowedDirs=['*'], allowedFileTypes=['*'])
                self.subjInterface = SubjectInterface(subjectRemote=False)
                self.bidsInterface = BidsInterface(dataRemote=False, allowedDirs = ['*'])
                self.exampleInterface = ExampleInterface(dataRemote=False)
                # Without a webServer (projectServer) the webInterface won't be able to do
                #   anything. Create a stub instance here with ioLoopInst=None so that calls
                #   to it won't thow exceptions.
                self.webInterface = WebDisplayInterface(ioLoopInst=None)
            else:
                raise err

    def isDataRemote(self):
        """
        Will return false if either no project server is running, or if a projectServer
        is running with data being served locally by the projectServer (remember that the
        projectServer and classification client script always run on the same computer).
        """
        if self.rpcConn is not None:
            return self.rpcConn.root.isDataRemote()
        else:
            return False

    def isSubjectRemote(self):
        """
        Same semantics as isDataRemote above.
        """
        if self.rpcConn is not None:
            return self.rpcConn.root.isSubjectRemote()
        else:
            return False

class WrapRpycObject(object):
    """
    Rpyc commands return a rpyc.core.netref object to as a reference to the remote object.
    This class wraps all calls to the remote in order to dereference the rpyc.core.netref
    and return the actual object using rpyc.classic.obtain(ref)
    """
    def __init__(self, remoteInterface):
        self.remote = remoteInterface

    def __getattribute__(self, name):
        remote = object.__getattribute__(self, 'remote')
        attr = getattr(remote, name)
        if hasattr(attr, '__call__'):
            def newfunc(*args, **kwargs):
                ref = attr(*args, **kwargs)
                result = rpyc.classic.obtain(ref)
                return result
            return newfunc
        else:
            return attr


    # TODO - make a more efficient getFile and putFile
    # def getFile():
    #  calls getFileMulti() repeatedly until all parts have been received and returns the data.
    #  note that for most files (<10M) there will only be one part, the reply will contain part x of y.
    #
    # def putFile():
    #  if the file is >10M will call the remote putFileMulti() repeatedly with each part. The remote
    #  will cache the parts until the last is received and assemble them.


# Example of generic override of getattribute to modify call behavior
# class Foo(object):
#     def __getattribute__(self,name):
#         attr = object.__getattribute__(self, name)
#         if hasattr(attr, '__call__'):
#             def newfunc(*args, **kwargs):
#                 print('before calling %s' %attr.__name__)
#                 result = attr(*args, **kwargs)
#                 print('done calling %s' %attr.__name__)
#                 return result
#             return newfunc
#         else:
#             return attr