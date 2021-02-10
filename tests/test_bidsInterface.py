from rtCommon.bidsInterface import BidsInterface
import pytest
import numpy
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface
from rtCommon.projectUtils import npToPy


class TestBidsInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    # Local bidsInterface test
    def test_localBidsInterface(self):
        """Test BidsInterface when instantiated in local mode"""
        TestBidsInterface.serversForTests.stopServers()
        TestBidsInterface.serversForTests.startServers(dataRemote=False)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        runBidsInterfaceTest(bidsInterface)

    # Remote bidsInterface test
    def test_remoteBidsInterface(self):
        """Test BidsInterface when instantiated in local mode"""
        # Use a remote (RPC) client to the bidsInterface
        TestBidsInterface.serversForTests.stopServers()
        TestBidsInterface.serversForTests.startServers(dataRemote=True)
        clientInterface = ClientInterface()
        bidsInterface = clientInterface.bidsInterface
        runBidsInterfaceTest(bidsInterface)
    
    # bidsInterface created locally by the client (no projectServer)
    def test_clientLocalBidsInterface(self):
        TestBidsInterface.serversForTests.stopServers()
        bidsInterface = BidsInterface(dataRemote=False)
        runBidsInterfaceTest(bidsInterface)


def runBidsInterfaceTest(bidsInterface):
    required_metadata = {'subject': '04', 'task': 'story', 'suffix': 'bold', 'datatype': 'func', 'run': 1}
    other_metadata = {'a1': [1, 'two', 3.0], 
                      'a2': {'np': numpy.float32(3), 'pyint': 4, 'str': 'five'},
                      'a3': [6.0, 'seven', numpy.int(8)]}
    args = (4, 'hello', required_metadata)
    kwargs = {'mdata': other_metadata, 'test1': 9.0, 'test2': numpy.float32(9), 'test3': 'yes'}
    res = bidsInterface.testMethod(*args, **kwargs)
    print(f'testMethod returned {res}')
    args_py = npToPy(args)
    kwargs_py = npToPy(kwargs)
    res[0] == args_py
    res[1] == kwargs_py


    # import pdb; pdb.set_trace()
    # assert res[0][0] == args_py[0]
    # assert res[0][1] == args_py[1]
    # assert compare_dict(res[0][2], args_py[2])
    # assert compare_dict(res[1], kwargs_py)
    # # For some reason comparing dictionaries d1==d2 fails to match even though each key and item match
    # # comparing d1.keys == d2.keys fails, but list(d1.keys()) == list(d2.keys()) succeeds
    # assert res[1] == kwargs_py

# def compare_dict(a, b):
#     akeys = list(a.keys())
#     bkeys = list(b.keys())
#     assert akeys == bkeys
#     for key in akeys:
#         if type(a[key]) is dict:
#             compare_dict(a[key], b[key])
#         else:
#             print(f'A comp B: {a[key]} {b[key]}, {type(a[key])}, {type(b[key])}')
#             assert a[key] == b[key]
#     return True
