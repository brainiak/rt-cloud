import rpyc
from rtCommon.fileInterface import FileInterface
from rtCommon.subjectInterface import SubjectInterface


class ClientRPC:
    """
    This class provides the API that an experiment script can use to communicate with the 
    project server. It provides both a FileInterface for reading or writing files, and a 
    SubjectInterface for sending/receiving feedback and response to the subject in the MRI scanner.
    """
    def __init__(self):
        """
        Establishes an RPC connection to a localhost projectServer on a predefined port. 
        The projectServer must be running on the same computer as the script using this interface.
        """
        try:
            rpcConn = rpyc.connect('localhost', 12345, 
                                   config={"allow_public_attrs": True,})
            self.fileInterface = rpcConn.root.FileInterface
            self.subjInterface = rpcConn.root.SubjectInterface
            self.rpcConn = rpcConn
        except ConnectionRefusedError as err:
            reply = input('Unable to connect to projectServer, continue using localfiles? ' + '(y/n): ')
            reply.lower().strip()
            if reply[0] == 'y':
                self.fileInterface = FileInterface(filesremote=False)
                self.subjInterface = SubjectInterface(detached=True)
            else:
                raise err