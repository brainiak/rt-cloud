
## Data Services and Interfaces
### At the Experminter's Script
#### ClientInterface:
The clientInterface is imported and instantiated from within the experimenter's script and tries to connect via RPyC to the ProjectServer, if it can't connect it runs in fully local mode (i.e. without the ProjectServer and without an rpyc connection)

If it connects to ProjectServer (via rpyc), then all the client service interfaces from the experimenter's script (such as dataInterface, subjectInterface, etc) are wrapped in a WrapRpycObject (within the ClientInterface instantiated in the experimenter's script) to facilitate unpacking and receiving actual data from the ProjectServer rather than an rpyc netref to the data.

### At the ProjectServer
At the ProjectServer the data services can either be run locally (isRemote==False), or alternately run remotely on a different computer (isRemote==True). If they are run locally then, for example, an instance of dataInterface will be created within the ProjectServer. If they are run remotely, then a remote service will be started on the separate computer, such as the scannerDataService, which internally runs a dataInterface to handle incoming requests.

### Connection Maps
In the fully remote case the communication is:

- researcher_script --> rpyc --> projectServer --> wsRPC --> scannerDataService (dataInterface)

In the case of a projectServer running local services the communication is:

- researcher_script --> rpyc --> projectServer (dataInterface)

In the fully local case (no projectServer) the communication is:

- researcher_script (dataInterface)

### Setup and timeouts
- RPyC is setup in the clientInterface.py (experiment script side) and corresponding projectServerRPC.py (projectServer side) files.
- wsRPC is setup in the projectServerRPC.py (projectServer side) and the remoteable.py class (dataService side, which the dataInterface and other interfaces inherit their class from).
- RPyC and wsRPC have separate timeouts, however they can be set together per-call by including a 'rpc_timeout' kwarg to any dataInterface call.
- The default RPyC timeout can be set with ClientInterface is instantiated, and the default WsRPC timeout can be set using the setRPCTimeout() of interface (i.e. classes derived from remoteable.py) objects.

