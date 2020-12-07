import pytest
from rtCommon.remoteable import Remoteable, RemoteableExtensible, RemoteHandler


class TestRemoteable:
    def setup_class(cls):
        pass

    def teardown_class(cls):
        pass

    def test_remoteable(self):
        # The remoteHandler will also be our communication go-between for the remote case
        remoteHandler = RemoteHandler()
        # Create a local version of the class - this would be the class instance at the remote server
        sampleLocal = SampleClassRemoteable(dataremote=False)
        # The local instance will be created on the remote server, register it with the remoteHandler
        remoteHandler.registerClassInstance(SampleClassRemoteable, sampleLocal)
        # Create the remote instance - this would be at the client side
        sampleRemote = SampleClassRemoteable(dataremote=True)
        # Register the remote instance's callstub as the handler.runRemoteCall function
        # Normally there would be a communiction channel between the remote callstub and the remoteHandler
        sampleRemote.registerCommFunction(remoteHandler.runRemoteCall)
        # Test all the functions
        assert sampleLocal.noargs() == sampleRemote.noargs()
        assert sampleLocal.posargs(1, 2) == sampleRemote.posargs(1, 2)
        assert sampleLocal.kwargs(a=3, b=4) == sampleRemote.kwargs(a=3, b=4)
        assert sampleLocal.poskwargs(1, 2, c=3, d=4) == sampleRemote.poskwargs(1, 2, c=3, d=4)
        assert sampleLocal.val1 == sampleRemote.val1
        assert sampleLocal.val2 == sampleRemote.val2
        pass

    def test_remoteableExtensible(self):
        # The remoteHandler will also be our communication go-between for the remote case
        remoteHandler = RemoteHandler()
        # Create a local version of the class - this would be the class instance at the remote server
        sampleLocal = SampleClassRemoteExtensible(dataremote=False)
        # The local instance will be created on the remote server, register it with the remoteHandler
        remoteHandler.registerClassInstance(SampleClassRemoteExtensible, sampleLocal)
        # Create the remote instance - this would be at the client side
        sampleRemote = SampleClassRemoteExtensible(dataremote=True)
        # Register the remote instance's callstub as the handler.runRemoteCall function
        # Normally there would be a communiction channel between the remote callstub and the remoteHandler
        sampleRemote.registerCommFunction(remoteHandler.runRemoteCall)
        # Test all the functions
        assert sampleLocal.noargs() == sampleRemote.noargs()
        assert sampleLocal.posargs(1, 2) == sampleRemote.posargs(1, 2)
        assert sampleLocal.kwargs(a=3, b=4) == sampleRemote.kwargs(a=3, b=4)
        assert sampleLocal.poskwargs(1, 2, c=3, d=4) == sampleRemote.poskwargs(1, 2, c=3, d=4)
        assert sampleLocal.val1 == sampleRemote.val1
        assert sampleLocal.val2 == sampleRemote.val2
        pass

    def test_remoteableHandler(self):
        rh = RemoteHandler()
        # The remote server instantiates a local instance
        testObj = SampleClassRemoteable(dataremote=False)
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

class SampleClassRemoteable(Remoteable):
    val1 = 'class field val1'
    def __init__(self, dataremote=False):
        super().__init__(dataremote)
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
    def __init__(self, dataremote=False):
        super().__init__(dataremote)
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

# o = Orange(dataremote=True)
# c = Cherry(dataremote=True)

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

# o = Orange(dataremote=True)
# o.addLocalAttributes('peel')
# c = Cherry(dataremote=True)

# o.peel(1)
# o.remotePeel(3)
# c.juice(2, b=3)