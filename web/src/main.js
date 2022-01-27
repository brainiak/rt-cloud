const React = require('react')
const ReactDOM = require('react-dom')
const dateformat = require('dateformat');
const path = require('path');
const SettingsPane = require('./settingsPane.js')
const RunPane = require('./runPane.js')
const XYPlotPane = require('./xyplotPane.js')
const VNCViewerPane = require('./vncViewerPane.js')
const UploadFilesPane = require('./uploadFilesPane.js')
const SessionPane = require('./sessionPane.js')
const LogPane = require('./logPane.js')
const { Tab, Tabs, TabList, TabPanel } = require('react-tabs');
const { type } = require('os');

const elem = React.createElement;

const logLineStyle = {
    margin: '0',
}

// This will be updated based on the value in the config file
var projectTitle = 'Real-Time Study';

function arrayCompareXValue(a, b){
  if (a['x'] > b['x']) return 1;
  if (b['x'] > a['x']) return -1;
  return 0;
}

function arrayFindIndexByX(arr, xval){
    var idx = arr.findIndex(function(element){return element['x']==xval})
    return idx
}

class TopPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      config: {
          title: 'Real-Time Study',
          plotXLabel: 'Item #',
          plotYLabel: 'Value',
          plotTitle: 'Value vs. Item #',
      },
      configFileName: 'Default',
      runStatus: '',
      connected: false,
      error: '',
      plotVals: [[{x:0, y:0}], []], // results to plot
      logLines: [],
      userLog: [],
      uploadedFileLog: [],
      sessionLog: [],
      dataConn: 0,
      subjectConn: 0,
    }
    this.resultVals = [[], []] // mutable version of plotVals to accumulate changes
    this.webSocket = null
    this.setConfigFileName = this.setConfigFileName.bind(this);
    this.setConfig = this.setConfig.bind(this);
    this.getConfigItem = this.getConfigItem.bind(this);
    this.setConfigItem = this.setConfigItem.bind(this);
    this.requestDefaultConfig = this.requestDefaultConfig.bind(this)
    this.requestDataPoints = this.requestDataPoints.bind(this)
    this.requestRunStatus = this.requestRunStatus.bind(this)
    this.startRun = this.startRun.bind(this);
    this.stopRun = this.stopRun.bind(this);
    this.uploadFiles = this.uploadFiles.bind(this);
    this.runSession = this.runSession.bind(this);
    this.createWebSocket = this.createWebSocket.bind(this)
    this.clearRunStatus = this.clearRunStatus.bind(this)
    this.clearPlots = this.clearPlots.bind(this)
    this.vncTabIndex = 4
    this.onTabSelected = this.onTabSelected.bind(this);
    this.createWebSocket()
  }

  onTabSelected(index, lastIndex, event) {
    if (index == this.vncTabIndex) {
      // show the screen div
      var screenDiv = document.getElementById('screen')
      screenDiv.style.display = "initial";
    } else if (lastIndex == this.vncTabIndex && index != lastIndex){
      // hide the screen div
      var screenDiv = document.getElementById('screen')
      screenDiv.style.display = "none";
    }
  }

  setConfigFileName(filename) {
    this.setState({configFileName: filename})
  }

  setConfig(newConfig) {
    if (projectTitle != newConfig['title']) {
        projectTitle = newConfig['title']
        document.getElementById('title').innerHTML = projectTitle;
    }
    this.setState({config: newConfig})
  }

  getConfigItem(name) {
    for (let key in this.state.config) {
      if (key == name) {
        return this.state.config[key]
      }
    }
    return ''
  }

  setConfigItem(name, value) {
    for (let key in this.state.config) {
      if (key == name) {
          var revConfig = Object.assign({}, this.state.config, { [name]: value })
          this.setConfig(revConfig)
          return
      }
    }
  }

  clearRunStatus(){
    this.setState({runStatus: ''})
  }

  // ###################################################
  // #### Remote Server Methods (Outgoing Requests) ####
  // ###################################################
  requestDefaultConfig() {
    var cmd = {cmd: 'getDefaultConfig'}
    var cmdStr = JSON.stringify(cmd)
    this.webSocket.send(cmdStr)
  }

  requestDataPoints() {
    var cmd = {cmd: 'getDataPoints'}
    var cmdStr = JSON.stringify(cmd)
    this.webSocket.send(cmdStr)
  }

  requestRunStatus() {
    var cmd = {cmd: 'getRunStatus'}
    var cmdStr = JSON.stringify(cmd)
    this.webSocket.send(cmdStr)
  }

  clearPlots() {
    // clear plots remote data
    var cmd = {cmd: 'clearDataPoints'}
    var cmdStr = JSON.stringify(cmd)
    this.webSocket.send(cmdStr)
    // clear plots local data
    for (let i = 0; i < this.resultVals.length; i++) {
      this.resultVals[i] = []
    }
    // Set a zero value so and empty plot appears
    this.resultVals[0] = [{x:0, y:0}]
    this.setState({plotVals: this.resultVals})
  }

  startRun() {
    // clear previous log output
    this.setState({logLines: []})
    this.setState({userLog: []})
    this.setState({error: ''})

    var cfg = formatConfigValues(this.state.config)
    if (cfg == null) {
        return
    }
    this.webSocket.send(JSON.stringify({cmd: 'runScript', args: ['mainScript'], config: cfg}))
  }

  runSession(scriptType) {
    // clear previous log output
    var firstLogMsg = '##### ' + scriptType + ' #####'
    this.setState({sessionLog: [firstLogMsg]})
    this.setState({error: ''})
    var cfg = formatConfigValues(this.state.config)
    if (cfg == null) {
        return
    }
    this.webSocket.send(JSON.stringify({cmd: 'runScript', args: [scriptType], config: cfg }))
  }

  stopRun() {
    this.webSocket.send(JSON.stringify({cmd: 'stop'}))
  }

  uploadFiles(srcFile, compress) {
    this.setState({error: ''})
    var cmdStr = {cmd: 'uploadFiles',
                  srcFile: srcFile,
                  compress: compress,
                 }
    this.webSocket.send(JSON.stringify(cmdStr))
  }
  // #### End Remote Server Methods (Outgoing Requests) ####


  // ##############################################
  // #### Message handlers for server reqeusts ####
  // ##############################################
  on_userLog(request) {
    var logItem = request['value'].trim()
    var itemPos = this.state.userLog.length + 1
    var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
    // Need to use concat() to create a new logLines object or React won't know to re-render
    var userLog = this.state.userLog.concat([newLine])
    this.setState({userLog: userLog})
    // Add all userLog messages to debugLog
    this.debugLog(logItem)
  }

  on_sessionLog(request) {
    var logItem = request['value'].trim()
    var itemPos = this.state.sessionLog.length + 1
    var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
    // Need to use concat() to create a new logLines object or React won't know to re-render
    var sessionLog = this.state.sessionLog.concat([newLine])
    this.setState({sessionLog: sessionLog})
    // Add all sessionLog messages to debugLog
    this.debugLog(logItem)
  }

  debugLog(logItem) {
    var itemPos = this.state.logLines.length + 1
    var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
    // Need to use concat() to create a new logLines object or React won't know to re-render
    var logLines = this.state.logLines.concat([newLine])
    this.setState({logLines: logLines})
  }
  on_debugLog(request) {
    var logItem = request['value'].trim()
    this.debugLog(logItem)
  }

  on_userError(request) {
    var errMsg = request['error']
    console.log("## Got Error: " + errMsg)
    this.setState({error: errMsg})
    this.debugLog(errMsg)
  }

  // TODO - currently this does the same as userError, but make a separate detailed debug error message in Log tab
  on_debugError(request) {
    var errMsg = request['error']
    console.log("## Got Error: " + errMsg)
    this.setState({error: errMsg})
    this.debugLog(errMsg)
  }

  on_runStatus(request) {
    var status = request['status']
    if (status == undefined || status.length == 0) {
      status = ''
    }
    if (typeof(status) === 'string') {
      this.setState({runStatus: status})
    } else {
      var name = status['name']
      var val = status['val']
      if (name == 'dataConn') {
        this.setState({dataConn: val})
      }
      if (name == 'subjectConn') {
        this.setState({subjectConn: val})
      }
    }
  }

  on_uploadStatus(request) {
    var fileName = request['file']
    var itemPos = this.state.uploadedFileLog.length + 1
    var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, fileName)
    // Need to use concat() to create a new logLines object or React won't know to re-render
    var uploadedFileLog = this.state.uploadedFileLog.concat([newLine])
    this.setState({uploadedFileLog: uploadedFileLog})
  }

  on_setConfig(request) {
    var config = request['value']
    var filename = request['filename']
    this.setConfig(config)
    this.setConfigFileName(filename)
  }

  on_setDataPoints(request) {
    var dataPoints = request['value']
    if (Array.isArray(dataPoints)) {
      this.resultVals = []
      for (let i = 0; i < dataPoints.length; i++) {
          var runVals = dataPoints[i]
          runVals.sort(arrayCompareXValue)
          this.resultVals.push(runVals)
      }
      this.setState({plotVals: this.resultVals})
    }
  }

  on_plotDataPoint(request) {
    var runId = request['runId']
    var vol = request['trId']
    var resultVal = request['value']
    // Make sure resultVals has at least as many arrays as runIds
    for (let i = this.resultVals.length; i < runId; i++) {
      this.resultVals.push([])
    }
    // clear plots with runId greater than the current one
    // for (let i = runId; i < this.resultVals.length; i++) {
    //   this.resultVals[i] = []
    // }
    // console.log(`resultValue: ${resultVal} ${vol} ${runId}`)
    if (typeof(vol) == 'number') {
      // ResultVals is zero-based and runId is 1-based, so resultVal index will be runId-1
      var runResultVals = this.resultVals[runId-1]
      // see if there is already a plot point for this vol (x-value)
      var idx = arrayFindIndexByX(runResultVals, vol)
      if (idx >= 0) {
        // overwrite the existing point
        runResultVals[idx] = {x: vol, y: resultVal}
      } else {
        // add new data point to resultVals for this runId
        runResultVals.push({x: vol, y: resultVal})
      }
      runResultVals.sort(arrayCompareXValue)
    } else {
      // vol is not a number, clear the resultVals for this run
      this.resultVals[runId-1] = []
    }
    this.setState({plotVals: this.resultVals})
  }

  // #### END Message handlers for server reqeusts ####

  createWebSocket() {
    var wsProtocol = 'wss://'
    if (location.protocol == 'http:') {
        wsProtocol = 'ws://'
    }
    var wsUserURL = wsProtocol + location.hostname + ':' + location.port + '/wsUser'
    console.log(wsUserURL)
    var webSocket = new WebSocket(wsUserURL);
    webSocket.onopen = (openEvent) => {
      this.setState({connected: true})
      console.log("WebSocket OPEN: ");
      this.requestDefaultConfig();
      this.requestDataPoints();
      this.requestRunStatus();
    };
    webSocket.onclose = (closeEvent) => {
      this.setState({connected: false})
      this.setState({dataConn: 0})
      this.setState({subjectConn: 0})
      console.log("WebSocket CLOSE: ");
    };
    webSocket.onerror = (errorEvent) => {
      this.setState({error: JSON.stringify(errorEvent, null, 4)})
      console.log("WebSocket ERROR: " + JSON.stringify(errorEvent, null, 4));
    };
    webSocket.onmessage = (messageEvent) => {
      // Handle requests from WebDisplayInterface
      var wsMsg = messageEvent.data;
      var request = JSON.parse(wsMsg)
      // reset error message
      // this.setState({error: ''})
      var cmd = request['cmd']
      // message handler functions are prepended with 'on_'
      var cmd_handler = 'on_' + cmd
      if (this[cmd_handler]) {
        this[cmd_handler](request)
      } else {
        var errStr = "Unknown message type: " + cmd
        console.log(errStr)
        this.setState({error: errStr})
      }
    };
    this.webSocket = webSocket
  }

  render() {
    var tp =
     elem(Tabs, {onSelect: this.onTabSelected},
       elem(TabList, {},
         elem(Tab, {}, 'Run'),
         elem(Tab, {}, 'Session'),
         elem(Tab, {}, 'Settings'),
         elem(Tab, {}, 'Data Plots'),
         elem(Tab, {}, 'VNC Viewer'),
         elem(Tab, {}, 'Log'),
         // elem(Tab, {}, 'Upload Files'),
       ),
       elem(TabPanel, {},
         elem(RunPane,
           {userLog: this.state.userLog,
            config: this.state.config,
            connected: this.state.connected,
            runStatus: this.state.runStatus,
            dataConn: this.state.dataConn,
            subjectConn: this.state.subjectConn,
            error: this.state.error,
            startRun: this.startRun,
            stopRun: this.stopRun,
            setConfig: this.setConfig,
            getConfigItem: this.getConfigItem,
            setConfigItem: this.setConfigItem,
            clearRunStatus: this.clearRunStatus,
           }
         ),
       ),
       elem(TabPanel, {},
         elem(SessionPane,
           {runSession: this.runSession,
            stopRun: this.stopRun,
            sessionLog: this.state.sessionLog,
            connected: this.state.connected,
            runStatus: this.state.runStatus,
            error: this.state.error,
           }
         ),
       ),
       elem(TabPanel, {},
         elem(SettingsPane,
           {config: this.state.config,
            configFileName: this.state.configFileName,
            setConfig: this.setConfig,
            getConfigItem: this.getConfigItem,
            setConfigItem: this.setConfigItem,
            setConfigFileName: this.setConfigFileName,
            requestDefaultConfig: this.requestDefaultConfig,
           }
         ),
       ),
       elem(TabPanel, {},
        elem(XYPlotPane,
          {config: this.state.config,
           plotVals: this.state.plotVals,
           clearPlots: this.clearPlots,
          }
        ),
      ),
       elem(TabPanel, {},
        elem(VNCViewerPane,
          {error: this.state.error,
          }
        ),
      ),
       elem(TabPanel, {},
        elem(LogPane,
          {logLines: this.state.logLines,
           connected: this.state.connected,
           runStatus: this.state.runStatus,
           error: this.state.error,
          }
        ),
      ),
       // elem(TabPanel, {},
       //   elem(UploadFilesPane,
       //     {uploadFiles: this.uploadFiles,
       //      uploadedFileLog: this.state.uploadedFileLog,
       //      error: this.state.error,
       //     }
       //   ),
       // ),
     )
    return tp
  }
}

function formatConfigValues(cfg) {
  // After user changes on the web page we need to convert some values from strings
  // Only consider as Int if no leading 0s, otherwise consider it a string
  var regexInt = /^[1-9]\d*$/;
  // Float must have a dot in it
  var regexFloat = /^[+-]?\d*\.\d+$/;
  var regexIP = /\d+\.\d+.\d+\.\d+/;

  // First format runNum and scanNum to be numbers not strings
  var runs = cfg['runNum']
  var scans = cfg['scanNum']

  // Handle runs values
  if (Array.isArray(runs)) {
    if (typeof runs[0] === 'string') {
      if (runs.length == 1) {
        runs = runs[0].split(',')
      }
      if (regexInt.test(runs[0]) == true) {
        runs = runs.map(Number);
      }
    }
  }
  if (typeof(runs) === 'string') {
    runs = runs.split(',')
    if (regexInt.test(runs[0]) == true) {
      runs = runs.map(Number);
    }
  }
  cfg['runNum'] = runs

  // Handle scan value
  if (Array.isArray(scans)) {
    if (typeof scans[0] === 'string') {
      if (scans.length == 1) {
        scans = scans[0].split(',')
      }
      if (regexInt.test(scans[0]) == true) {
        scans = scans.map(Number);
      }
    }
  }
  if (typeof(scans) === 'string') {
    scans = scans.split(',')
    if (regexInt.test(scans[0]) == true) {
      scans = scans.map(Number);
    }
  }
  cfg['scanNum'] = scans

  // Next change all true/false strings to booleans
  // and change all number strings to numbers
    for (let key in cfg) {
      if (typeof cfg[key] === 'string') {
        var value = cfg[key]
        // check if the string should be a boolean
        switch(value.toLowerCase()) {
          case 'false':
          case 'flase':
          case 'fales':
          case 'flsae':
          case 'fasle':
            cfg[key] = false
            break;
          case 'true':
          case 'ture':
          case 'treu':
            cfg[key] = true
            break;
        }
        if (regexInt.test(value) == true) {
          // string should be an integer
          cfg[key] = parseInt(value, 10)
        } else if (regexFloat.test(value) == true &&
                   regexIP.test(value) == false) {
          // string should be a float
          cfg[key] = parseFloat(value)
        }
      }
    }
    return cfg
}

function Render() {
  document.getElementById('title').innerHTML = projectTitle;

  const tabDiv = document.getElementById('tabs_container');
  ReactDOM.render(elem(TopPane), tabDiv);
}

Render()
