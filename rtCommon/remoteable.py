"""
A set of classes that can be subclassed or extended to allow for automatically forwarding
methods calls on the subclass to a remote RPC handler.

On cloud side we will have a remoteInstance (with remoteCall stub) that calls
the networking crossbar to send the request to the remote.
On the remote side we will have a RemoteHandler instance and when messages are received
will dispatch them to the handler.
"""
import inspect
import rpyc
from rtCommon.errors import RequestError, StateError


# Possibility A - the "has a" model, returns a 'remote' instance, nothing to do with the original class
class Remoteable(object):
    """
    A class that can be subclassed to allow remote invocation.
    When isRemote is True it returns a remote stub instance, when false it returns the real instance
    """
    def __new__(cls, isRemote=False):
        if isRemote is True:
            # instance = RemoteStub(cls.__name__)
            instance = RemoteStub(cls)
        else:
            instance = object.__new__(cls)
        return instance

    def __init__(self, isRemote=False):
        self.isRemote = isRemote


class RemoteStub(object):
    """
    A remote stub class where none of the attributes of the original class are defined.
    Therefore __getattr__ will be called for all attributes (i.e. intercepting normal calls)
    and this class overrides __getattr__ to forward the call request to a remote instance
    via the registered communication channel function.
    """
    def __init__(self, classType, isRemote=True):
        assert isRemote is True
        self.isRemote = True  # always true for the remote stup
        self.classType = classType
        self.classname = classType.__name__
        self.commFunction = None
        self.timeout = 5

    def setRPCTimeout(self, timeout):
        self.timeout = timeout

    def registerCommFunction(self, commFunction):
        # TODO - perhaps we register a channel instead which goes directly to one end point
        self.commFunction = commFunction

    def remoteCall(self, attribute, *args, **kwargs) -> any:
        # args and kwargs may be of type rpyc.core.netref.type if rpyc was used to
        #   send this request from the client script to the projectServer; pull the actual object
        args = rpyc.classic.obtain(args)
        kwargs = rpyc.classic.obtain(kwargs)
        callStruct = {'cmd': 'rpc', 'class': self.classname, 'attribute': attribute, 'args': args, 'kwargs': kwargs}
        # print(f'remoteCall: {callStruct}}')
        timeout = self.timeout
        if 'rpc_timeout' in kwargs:
            timeout = kwargs.pop('rpc_timeout')
        return self.commFunction(callStruct, timeout=timeout)

    def __getattr__(self, name):
        # Previously just 'return self.remoteCall'
        # Create an closure function that populates the self and name args
        def anonymous(*args, **kwargs):
            return self.remoteCall(name, *args, **kwargs)
        attr = getattr(self.classType, name, None)
        if attr is None or not callable(attr):
            # if attr is None it should be an instance variable
            # if attr is not callable is is a class variable
            # call the closure function immediately and return the results
            return anonymous()
        # it is callable so return the function instance
        return anonymous


# Possibility B - the "is a" model, subclass the remoteable class
# Note - this just seems too complicated with the recursion of __getattribute__
class RemoteableExtensible(object):
    """
    A class that can be subclassed to allow remote invocation. The remote and local versions
    are the same class type (not a stub) and in the remote instance case attributes can
    be registerd as 'local' meaning calls to them will be handled local, all other calls
    would be sent to the remote instance.
    """
    def __init__(self, isRemote=False):
        self.isRemote = isRemote
        self.commFunction = None
        self.timeout = 5
        self.localAttributes = [
            'localAttributes', 'commFunction', 'timeout',
            'addLocalAttributes', 'registerCommFunction',
            'setRPCTimeout', 'isRunningRemote', 'isRemote'
            ]

    def isRunningRemote(self):
        return self.isRemote

    def setRPCTimeout(self, timeout):
        self.timeout = timeout

    def registerCommFunction(self, commFunction):
        # TODO - perhaps we register a channel instead which goes directly to one end point
        self.commFunction = commFunction

    def remoteCall(self, attribute, *args, **kwargs) -> any:
        # args and kwargs may be of type rpyc.core.netref.type if rpyc was used to
        #   send this request to the projectServer from the client script, pull the actual object
        args = rpyc.classic.obtain(args)
        kwargs = rpyc.classic.obtain(kwargs)
        callStruct = {'cmd': 'rpc', 'class': type(self).__name__, 'attribute': attribute, 'args': args, 'kwargs': kwargs}
        # print(f'### remoteCall callStruct: {callStruct}')
        timeout = self.timeout
        if 'rpc_timeout' in kwargs:
            timeout = kwargs.pop('rpc_timeout')
        # print(f'Remote call using timeout: {timeout}')
        result = self.commFunction(callStruct, timeout=timeout)
        # print(f'result: {type(result)}')
        return result

    def addLocalAttributes(self, methods):
        if type(methods) is str:
            self.localAttributes.append(methods)
        elif type(methods) is list:
            self.localAttributes.extend(methods)

    def __getattribute__(self, name):
        # callername = inspect.stack()[1][3]
        # if callername in ('__getattribute__', 'remoteCall'):
        #     raise RecursionError('Remoteable __getattribute__ {name}: add all object attrs to localAttributes')
        isremote = object.__getattribute__(self, 'isRemote')
        if isremote:
            localAttrs = object.__getattribute__(self, 'localAttributes')
            if name not in localAttrs:
                remoteCallFunc = object.__getattribute__(self, 'remoteCall')
                def anonymous(*args, **kwargs):
                    return remoteCallFunc(name, *args, **kwargs)
                attr = object.__getattribute__(self, name)
                if attr is None or not callable(attr):
                    # if attr is None it should be an instance variable
                    # if attr is not callable it is a class variable
                    # call the closure function immediately and return the results
                    return anonymous()
                return anonymous
        # return super().__getattribute__(name)
        # return super(RemoteableB, self).__getattribute__(name)
        return object.__getattribute__(self, name)


# TODO - support per client remote instances, either by having a per-client classInstanceDict
#  or by supporting a 'new' function call, or by returning handles of the instances (although
#  that might be more complext than needed)
class RemoteHandler:
    """
    Class that runs at the remote and as message requests are received they are dispatched
    to this class for processing.
    """
    def __init__(self):
        self.classInstanceDict = {}

    def registerClassInstance(self, classType, classInstance):
        self.classInstanceDict[classType.__name__] = classInstance

    def registerClassNameInstance(self, className, classInstance):
        self.classInstanceDict[className] = classInstance

    def runRemoteCall(self, callDict):
        # print(f'remoteCall {callDict}')
        className = callDict.get('class')
        attributeName = callDict.get('attribute')
        if None in (className, attributeName):
            raise RequestError(f'Malformed remote call struct: missing one of '
                               f'class {className}, attribute {attributeName}')
        classInstance = self.classInstanceDict.get(className)
        if classInstance is None:
            raise StateError(f'RemoteHandler: class {className} not registered')
        attributeInstance = getattr(classInstance, attributeName)
        if not callable(attributeInstance):
            return attributeInstance
        args = callDict.get('args', ())
        if args is None:  # Can happen if key 'args' exists and is set to None
            args = ()
        kwargs = callDict.get('kwargs', {})
        if kwargs is None:
            kwargs = {}
        res = attributeInstance(*args, **kwargs)
        return res
