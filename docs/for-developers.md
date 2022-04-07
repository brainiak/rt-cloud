# Information and Overview for Developers

### **Software Tests**
There is an extensive set of software tests in the ```rt-cloud/tests/``` directory that use the pytest framework. To run the tests from the rt-cloud directory use command:

    python -m pytest -s -v tests/

### **Web Interface**
The projectServer runs a Tornado web server, launched from within module ```rt-cloud/rtCommon/webServer.py```. This web server provides url endpoints for the main webpage /index.html, and for various websocket interfaces such as wsData, wsSubject, and wsUser for sending and receiving commands. The main web page (index.html) loads a javascript bundle that uses React to create the webpage that the user interacts with.

The web interface source code is in the ```rt-cloud/web/``` directory. The javascript code that is used to render the main webpage is in the web/src/ directory. There is essentially one javascript file per panel (tab) shown on the main webpage. Before building the javascript bundle for the first time, the npm packages must be installed. The installation and build specifications are provided to npm through the package.json file.

    cd web/
    npm install

From then on, the javascript bundle can be built with command:

    npm run build

### **Software Overview**
**Functional Description:**
The projectServer is the central control point within the system. It serves as a communication hub linking components. For example, it is the intermediary that receives brain scan volumes, forwards those to the model processing script, returns classification feedback results, and provides researcher user controls through a web interface. 

The webServer is part of the projectServer that provides user control and feedback, but it also is a communication hub accepting secure web socket (WSS) connections for data transfer and subject feedback. This is convenient because the same web port and ssl certificate can be used for all forms of network communication.

**Interfaces and Services:**
Various utilities and functions are provided by the rt-cloud framework for use by the experiment specific scripts. For example, functions that allow watching for Dicom data to be written by the scanner, and many others. These functions are provide in python modules, such as dataInterface, subjectInterface and bidsInterface. These modules can be loaded directly by the experiment script and used, however most often these module need to run remotely and accessed via connection to the projectServer.

For example, the dicom data typically arrives at the control room computer, and so we want the dataInterface to run on that computer and connect to the projectServer to provide remote access to the experiment script.

If the module is running remotely we call it a service, and the service connects to the projectServer via a websocket and receives commands to run functions and return results. From within the experiment script it just makes normal function calls to these interfaces, and depending on the configuration, those calls can be transparently forwarded to the remote service for processinng.

So from a high-level, rt-cloud provides sets of functions for the experiment script to use. Some related to getting and putting data (dataInterface) and some related to setting classification results (subjectInterface), and others. Those functions can be run locally with the experiment script by simply importing the modules. However, if the data or presentation is on a remote computer then these functions need to run remotely. In that case we wrap the functions (dataInterace, subjectInterface etc) within a service that houses the functions and makes a websocket connection to projectServer. Then when the experiment script makes a function call to one of these services, it is packaged into a network message, send to the service to be run, and the results returned back to the experiment script (all transparent to the script).

**Other Interface Details**

The dataInterface (formerly fileWatcher) is a component for getting/putting/listing and watching for files. It's main task is to watch for the creation of Dicom files on MRI scanner filesystem, and then read and forward those to the projectServer for processing. Other related components are a bidsInterface for returning volumes in BIDS format. And an OpenNeuro interface for retrieving and replaying OpenNeuro data.

The subjectInterface provides a data queue which the experiment script can push classification results onto, and the presentation script can pop results off from, in order to provide feedback to the subject in the MRI scanner. This can also be incorporated into tools such as jsPsych or psychoPy.

The BIDS data modules allow converting a stream of Dicom images to a BIDS stream and other BIDS related functions like creating a BIDS archive from the data.

**Configurations:**

System configuration is handled through a toml file that is provided via the projectServer along with the experimenter’s script. This has settings that can be configured by the researcher that are used by the experiment script.

The paths to the experiment script and configuration files are provided to the projectServer so it can start the script as a separate process and forward data and communications to it.


**Where Interfaces Run:**

Interface objects can be instantiated in one of 3 places. 1) Within the experiment script directly. In this case there is no projectServer needed and no remote communication. 2) Within the projectServer - In this case the functions are run within the projectServer and the results returned to the script via RPyC. 3) At a remote computer (i.e. a remote service) - In this case the interface functions are run at the remote computer and the experiment script's request to run a command is packaged into a network message and sent to the remote service, which then runs the function corresponding to the request and returns the result.

**Remote Communication Between Components** -
Expanding on the 3 options:
1. Local Only Case: when no ProjectServer is used. In this case all interfaces run locally within the same process as the researcher's script (such as dataInterface, subjectInterace etc). In this case there are no RPyC or wsRPC (WebSocket RPC) hops involved and ```clientInterface.isUsingProjectServer() == False``` and ```dataInterace.isRunningRemote() == False```.

2. ProjectServer with local services: The data and/or subject services run on the same computer and in the same process as the ProjectServer (note that one service could be local and another remote). In this case there is a RPyC hop from the researcher's script to the ProjectServer, but no wsRPC hop from there to a remote service. The interface's isRunningRemote() function will return False (such as dataInterface.isRunningRemote()), indicating that the interface or service is running on the same computer as the ProjectServer. In this case ```clientInterface.isUsingProjectServer() == True```, but ```dataInterace.isRunningRemote() == False```. A rpc_timeout parameter can be supplied as an extra kwarg to function call to increase the RPyC timeout for that call.

3. ProjectServer with remote services: The data and/or subject services are running on different computers from the ProjectServer (note that one service could be remote and another local). In this case there is a RPyC hop from the researcher's script to the ProjectServer, and a wsRPC hop from the ProjectServer to the remote services. The ```clientInterface.isUsingProjectServer() == True```, and ```dataInterace.isRunningRemote() == True```. A rpc_timeout can be supplied as an extra kwarg to function calls to increase both the RPyC and wsRPC timeouts for that call.

<!--
There are 2 broad types of components, *Interfaces* and *Services*:
1. Interfaces: These are sets of functions that the experiment script can call. They provide functionality to the script such as getting data, sending classification results, setting information on the web page. These are implemented by a class in a python module where the class functions implement logic (code) for the interface.
2. Services: These are processes which provide the instantiated *Interface* that the experiment script calls. For example a dataService would instantiate a dataInterface object and receive requests from an experiment script to run a function and return the results.
-->