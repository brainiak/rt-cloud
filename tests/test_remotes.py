import pytest
from rtCommon.remoteable import Remoteable, RemoteableExtensible, RemoteHandler


class TestRemoteable:
    def setup_class(cls):
        pass

    def teardown_class(cls):
        pass

    def test_remoteable(self):
        # Create the instance running at remote server (note that data will be local to that instance)
        sampleServerInstance = SampleClassRemoteable(isRemote=False)

        # Create a mock RPC instance that will mimic the communication to service
        mockRPC = MockRPCHandler(sampleServerInstance)

        # Create a client instance (note it's requests will need to be sent to the remote)
        sampleClientInstance = SampleClassRemoteable(isRemote=True)

        # The mockRPC will act as the communication channel between the client and server.
        sampleClientInstance.registerCommFunction(mockRPC.sendRequest)

        # Test all the functions
        assert sampleServerInstance.noargs() == sampleClientInstance.noargs()
        assert sampleServerInstance.posargs(1, 2) == sampleClientInstance.posargs(1, 2)
        assert sampleServerInstance.kwargs(a=3, b=4) == sampleClientInstance.kwargs(a=3, b=4)
        assert sampleServerInstance.poskwargs(1, 2, c=3, d=4) == sampleClientInstance.poskwargs(1, 2, c=3, d=4)
        assert sampleServerInstance.val1 == sampleClientInstance.val1
        assert sampleServerInstance.val2 == sampleClientInstance.val2
        pass

    def test_remoteableExtensible(self):
        # Create the instance running at remote server (note that data will be local to that instance)
        sampleServerInstance = SampleClassRemoteExtensible(isRemote=False)

        # Create a mock RPC instance that will mimic the communication to service
        mockRPC = MockRPCHandler(sampleServerInstance)

        # Create a client instance (note it's requests will need to be sent to the remote)
        sampleClientInstance = SampleClassRemoteExtensible(isRemote=True)

        # The mockRPC will act as the communication channel between the client and server.
        sampleClientInstance.registerCommFunction(mockRPC.sendRequest)

        # Test all the functions
        assert sampleServerInstance.noargs() == sampleClientInstance.noargs()
        assert sampleServerInstance.posargs(1, 2) == sampleClientInstance.posargs(1, 2)
        assert sampleServerInstance.kwargs(a=3, b=4) == sampleClientInstance.kwargs(a=3, b=4)
        assert sampleServerInstance.poskwargs(1, 2, c=3, d=4) == sampleClientInstance.poskwargs(1, 2, c=3, d=4)
        assert sampleServerInstance.val1 == sampleClientInstance.val1
        assert sampleServerInstance.val2 == sampleClientInstance.val2
        pass

    def test_remoteableHandler(self):
        rh = RemoteHandler()
        # The remote server instantiates a local instance
        testObj = SampleClassRemoteable(isRemote=False)
        # Also create a list object
        aList = list()

        rh.registerClassInstance(list, aList)
        rh.registerClassInstance(SampleClassRemoteable, testObj)

        rh.runRemoteCall({'class': 'list', 'attribute': 'append', 'args': ('one',)})
        rh.runRemoteCall({'class': 'list', 'attribute': 'append', 'args': ('two',), 'kwargs': None})
        assert aList == ['one', 'two']

        res = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'noargs'}) 
        assert res == testObj.noargs()

        res = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'noargs', 'args': None, 'kwargs': None})
        assert res == testObj.noargs()

        res = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'posargs', 'args': (1, 2,), 'kwargs': None})
        assert res == testObj.posargs(1, 2)

        res = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'kwargs', 'args': None, 'kwargs': {'a':1, 'b':2,}})
        assert res == testObj.kwargs(a=1, b=2)

        val1 = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'val1'})
        assert val1 == testObj.val1

        val2 = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'val2'})
        assert val2 == testObj.val2

        val2 = rh.runRemoteCall({'class': testObj.__class__.__name__, 'attribute': 'val2', 'args': None, 'kwargs': None})
        assert val2 == testObj.val2
        pass


### Sample classes for running tests ###
class MockRPCHandler:
    """Pass in the serviceInstance running at the remote site since we are mocking that
       there is actually and network connection between the two sites.
    """
    def __init__(self, serviceInstance):
        # The remoteHandler will also be our communication go-between for the remote case
        self.remoteHandler = RemoteHandler()
        serviceClass = type(serviceInstance)
        self.remoteHandler.registerClassInstance(serviceClass, serviceInstance)

    def sendRequest(self, cmd, timeout=5):
        return self.remoteHandler.runRemoteCall(cmd)


class SampleClassRemoteable(Remoteable):
    val1 = 'class field val1'
    def __init__(self, isRemote=False):
        super().__init__(isRemote)
        self.val2 = 'instance field val2'

    def noargs(self):
        print('noargs called')
        return {'func': 'noargs'}

    def posargs(self, a, b):
        print(f'posargs {a} {b}')
        return {'func': 'posargs', 'a': a, 'b': b}

    def kwargs(self, a=1, b=2):
        print(f'kwargs {a} {b}')
        return {'func': 'kwargs', 'a': a, 'b': b}

    def poskwargs(self, a, b, c=1, d=2):
        print(f'poskwargs {a} {b} {c} {d}')
        return {'func': 'poskwargs', 'a': a, 'b': b, 'c': c, 'd': d}


class SampleClassRemoteExtensible(RemoteableExtensible):
    val1 = 'class field val1'
    def __init__(self, isRemote=False):
        super().__init__(isRemote=isRemote)
        self.val2 = 'instance field val2'

    def noargs(self):
        print('noargs called')
        return {'func': 'noargs'}

    def posargs(self, a, b):
        print(f'posargs {a} {b}')
        return {'func': 'posargs', 'a': a, 'b': b}

    def kwargs(self, a=1, b=2):
        print(f'kwargs {a} {b}')
        return {'func': 'kwargs', 'a': a, 'b': b}

    def poskwargs(self, a, b, c=1, d=2):
        print(f'poskwargs {a} {b} {c} {d}')
        return {'func': 'poskwargs', 'a': a, 'b': b, 'c': c, 'd': d}



# TODO - delete these
# class Orange(Remoteable):
#     def peel(self, a):
#         print('Peel Orange')
#         return True

# class Cherry(Remoteable):
#     def juice(self, a, b=6):
#         print('Juice Cherries')
#         return a+b

# o = Orange(isRemote=True)
# c = Cherry(isRemote=True)

# o.peel(1)
# c.juice(2, b=3)

# # Test with RemoteableB
# class Orange(RemoteableExtensible):
#     def peel(self, a):
#         print('Peel Orange')
#         return True
    
#     def remotePeel(self, b):
#         print(f'remote peel {b}')

# class Cherry(RemoteableExtensible):
#     def juice(self, a, b=6):
#         print('Juice Cherries')
#         return a+b

# o = Orange(isRemote=True)
# o.addLocalAttributes('peel')
# c = Cherry(isRemote=True)

# o.peel(1)
# o.remotePeel(3)
# c.juice(2, b=3)