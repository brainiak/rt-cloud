import rpyc
from rtCommon.dataInterface import DataInterface
from rtCommon.subjectInterface import SubjectInterface
from rtCommon.webDisplayInterface import WebDisplayInterface
from rtCommon.bidsInterface import BidsInterface


class ClientInterface:
    """
    This class provides the API that an experiment script can use to communicate with the 
    project server. It provides both a DataInterface for reading or writing files, and a 
    SubjectInterface for sending/receiving feedback and response to the subject in the MRI scanner.
    """
    def __init__(self):
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
                                            # "allow_getattr": True,
                                            # "allow_setattr": True,
                                            # "allow_delattr": True,
                                            # "allow_all_attrs": True,
                                           })
            # Need to provide an override class of DataInstance to return data from getImage
            self.dataInterface = DataInterfaceOverrides(rpcConn.root.DataInterface)
            self.subjInterface = rpcConn.root.SubjectInterface
            self.bidsInterface = rpcConn.root.BidsInterface
            # WebDisplay is always run within the projectServer (i.e. not a remote service)
            self.webInterface = rpcConn.root.WebDisplayInterface
            self.rpcConn = rpcConn
        except ConnectionRefusedError as err:
            reply = input('Unable to connect to projectServer, continue using localfiles? ' + '(y/n): ')
            reply.lower().strip()
            if reply[0] == 'y':
                # These will be run in the same process as the experiment script
                self.dataInterface = DataInterface(dataremote=False)
                self.subjInterface = SubjectInterface(dataremote=False)
                self.bidsInterface = BidsInterface(dataremote=False)
                # TODO: this can't run locally? There is no remote option for webDisplayService because it always runs local within the projectServer
                self.webInterface = WebDisplayInterface(ioLoopInst=None)
            else:
                raise err

    def isDataRemote(self):
        if self.rpcConn is not None:
            return self.rpcConn.root.isDataRemote()
        else:
            return False


class DataInterfaceOverrides(object):
    '''Override the getImageData function of DataInterface 
       to return the actual data rather than an RPC reference
    '''

    def __init__(self, remoteDataInterface):
        self.remote = remoteDataInterface

    def __getattribute__(self, name):
        """
        If this override class implements a function, then return it.
        Otherwise return the remoteInstance verion of the function.
        Note: __getattribute__ is called for every reference whereas
            __getattr__ is only called for missing references
        """
        try:
            attr = object.__getattribute__(self, name)
        except AttributeError:
            return getattr(self.remote, name)
        return attr

    # Override getImageData to return by value rather than by reference
    def getImageData(self, streamId: int, imageIndex: int=None, timeout: int=5):
        ref = self.remote.getImageData(streamId, imageIndex, timeout)
        val = rpyc.classic.obtain(ref)
        return val


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