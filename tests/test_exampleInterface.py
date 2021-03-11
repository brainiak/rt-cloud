from rtCommon.exampleInterface import ExampleInterface
import pytest
import numpy
from tests.backgroundTestServers import BackgroundTestServers
from rtCommon.clientInterface import ClientInterface
from rtCommon.projectUtils import npToPy


class TestExampleInterface:
    serversForTests = None

    def setup_class(cls):
        cls.serversForTests = BackgroundTestServers()

    def teardown_class(cls):
        cls.serversForTests.stopServers()

    # Local exampleInterface test
    def test_localExampleInterface(self):
        """Test ExampleInterface when instantiated in local mode"""
        TestExampleInterface.serversForTests.stopServers()
        TestExampleInterface.serversForTests.startServers(exampleRemote=False,
                                                          dataRemote=False, subjectRemote=False)
        clientInterface = ClientInterface()
        exampleInterface = clientInterface.exampleInterface
        runExampleInterfaceTest(exampleInterface)

    # Remote exampleInterface test
    def test_remoteExampleInterface(self):
        """Test ExampleInterface when instantiated in local mode"""
        # Use a remote (RPC) client to the exampleInterface
        TestExampleInterface.serversForTests.stopServers()
        TestExampleInterface.serversForTests.startServers(exampleRemote=True,
                                                          dataRemote=True, subjectRemote=False)
        clientInterface = ClientInterface()
        exampleInterface = clientInterface.exampleInterface
        runExampleInterfaceTest(exampleInterface)

    # exampleInterface created locally by the client (no projectServer)
    def test_clientLocalExampleInterface(self):
        TestExampleInterface.serversForTests.stopServers()
        exampleInterface = ExampleInterface(dataRemote=False)
        runExampleInterfaceTest(exampleInterface)


def runExampleInterfaceTest(exampleInterface):
    required_metadata = {'subject': '04', 'task': 'story', 'suffix': 'bold', 'datatype': 'func', 'run': 1}
    other_metadata = {'a1': [1, 'two', 3.0],
                      'a2': {'np': numpy.float32(3), 'pyint': 4, 'str': 'five'},
                      'a3': [6.0, 'seven', numpy.int(8)]}
    args = (4, 'hello', required_metadata)
    kwargs = {'mdata': other_metadata, 'test1': 9.0, 'test2': numpy.float32(9), 'test3': 'yes'}
    res = exampleInterface.testMethod(*args, **kwargs)
    print(f'testMethod returned {res}')
    args_py = npToPy(args)
    kwargs_py = npToPy(kwargs)
    assert tuple(res[0]) == args_py
    assert res[1] == kwargs_py
