import threading
from rtCommon.expRPCServer import startExpModelRPCThread
from rtCommon.projectInterface import Web


def startMainServer(params, args):
    rpcThread = threading.Thread(name='rpcThread',
                                 target=startExpModelRPCThread,
                                 kwargs={'filesRemote': args.filesremote,
                                         'hostname': 'localhost',
                                         'port': 12345})
    rpcThread.setDaemon(True)
    rpcThread.start()

    if not hasattr(args, 'test'):
        args.test = False

    web = Web()
    web.start(params, args.config, args.filesremote, testMode=args.test)
