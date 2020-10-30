import rpyc
from rtCommon.fileInterface import FileInterface
from rtCommon.subjectInterface import SubjectInterface


class ClientRPC:
    def __init__(self):
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