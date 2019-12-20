const React = require('react')
const ReactDOM = require('react-dom')
const dateformat = require('dateformat');
const path = require('path');
const SettingsPane = require('./settingsPane.js')
const StatusPane = require('./statusPane.js')
const XYPlotPane = require('./xyplotPane.js')
const UploadFilesPane = require('./uploadFilesPane.js')
const SessionPane = require('./sessionPane.js')
const { Tab, Tabs, TabList, TabPanel } = require('react-tabs')

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
      uploadedFileLog: [],
      sessionLog: [],
    }
    this.resultVals = [[], []] // mutable version of plotVals to accumulate changes
    this.webSocket = null
    this.setConfigFileName = this.setConfigFileName.bind(this);
    this.setConfig = this.setConfig.bind(this);
    this.getConfigItem = this.getConfigItem.bind(this);
    this.setConfigItem = this.setConfigItem.bind(this);
    this.requestDefaultConfig = this.requestDefaultConfig.bind(this)
    this.requestDataPoints = this.requestDataPoints.bind(this)
    this.startRun = this.startRun.bind(this);
    this.stopRun = this.stopRun.bind(this);
    this.uploadFiles = this.uploadFiles.bind(this);
    this.runSession = this.runSession.bind(this);
    this.createWebSocket = this.createWebSocket.bind(this)
    this.formatConfigValues = this.formatConfigValues.bind(this)
    this.clearRunStatus = this.clearRunStatus.bind(this)
    this.clearPlots = this.clearPlots.bind(this)
    this.createWebSocket()
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
    this.setState({error: ''})

    var cfg = this.formatConfigValues(this.state.config)
    if (cfg == null) {
        return
    }
    this.webSocket.send(JSON.stringify({cmd: 'run', config: cfg}))
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

  runSession(cmd) {
    // clear previous log output
    var firstLogMsg = '##### ' + cmd + ' #####'
    this.setState({sessionLog: [firstLogMsg]})
    this.setState({error: ''})

    var cfg = this.formatConfigValues(this.state.config)
    if (cfg == null) {
        return
    }
    this.webSocket.send(JSON.stringify({cmd: cmd}))
  }

  formatConfigValues(cfg) {
    // After user changes on the web page we need to convert some values from strings
    // First format runNum and scanNum to be numbers not strings
    var runs = cfg['runNum']
    var scans = cfg['scanNum']

    // Handle runs values
    if (Array.isArray(runs)) {
      if (typeof runs[0] === 'string') {
        if (runs.length > 1) {
          runs = runs.map(Number);
        } else {
          runs = runs[0].split(',').map(Number);
        }
      }
    }
    if (typeof(runs) === 'string') {
      runs = runs.split(',').map(Number);
    }
    cfg['runNum'] = runs

    // Handle scan value
    if (Array.isArray(scans)) {
      if (typeof scans[0] === 'string') {
        if (scans.length > 1) {
          scans = scans.map(Number);
        } else {
          scans = scans[0].split(',').map(Number);
        }
      }
    }
    if (typeof(scans) === 'string') {
      scans = scans.split(',').map(Number);
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
          var regexInt = /^\d+$/;
          var regexFloat = /^[\d\.]+$/;
          var regexIP = /\d+\.\d+.\d+\.\d+/;
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
    };
    webSocket.onclose = (closeEvent) => {
      this.setState({connected: false})
      console.log("WebSocket CLOSE: ");
    };
    webSocket.onerror = (errorEvent) => {
      this.setState({error: JSON.stringify(errorEvent, null, 4)})
      console.log("WebSocket ERROR: " + JSON.stringify(errorEvent, null, 4));
    };
    webSocket.onmessage = (messageEvent) => {
      var wsMsg = messageEvent.data;
      var request = JSON.parse(wsMsg)
      // reset error message
      // this.setState({error: ''})
      var cmd = request['cmd']
      if (cmd == 'config') {
        var config = request['value']
        var filename = request['filename']
        this.setConfig(config)
        this.setConfigFileName(filename)
      } else if (cmd == 'userLog') {
        var logItem = request['value'].trim()
        var itemPos = this.state.logLines.length + 1
        var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
        // Need to use concat() to create a new logLines object or React won't know to re-render
        var logLines = this.state.logLines.concat([newLine])
        this.setState({logLines: logLines})
      } else if (cmd == 'sessionLog') {
        var logItem = request['value'].trim()
        var itemPos = this.state.sessionLog.length + 1
        var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
        // Need to use concat() to create a new logLines object or React won't know to re-render
        var sessionLog = this.state.sessionLog.concat([newLine])
        this.setState({sessionLog: sessionLog})
      } else if (cmd == 'runStatus') {
        var status = request['status']
        if (status == undefined || status.length == 0) {
          status = ''
        }
        this.setState({runStatus: status})
      } else if (cmd == 'uploadProgress') {
        var fileName = request['file']
        var itemPos = this.state.uploadedFileLog.length + 1
        var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, fileName)
        // Need to use concat() to create a new logLines object or React won't know to re-render
        var uploadedFileLog = this.state.uploadedFileLog.concat([newLine])
        this.setState({uploadedFileLog: uploadedFileLog})
      } else if (cmd == 'resultValue') {
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
      } else if (cmd == 'dataPoints') {
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
      } else if (cmd == 'error') {
        console.log("## Got Error: " + request['error'])
        this.setState({error: request['error']})
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
     elem(Tabs, {},
       elem(TabList, {},
         elem(Tab, {}, 'Run'),
         elem(Tab, {}, 'Data Plots'),
         elem(Tab, {}, 'Session'),
         elem(Tab, {}, 'Settings'),
         // elem(Tab, {}, 'Upload Files'),
       ),
       elem(TabPanel, {},
         elem(StatusPane,
           {logLines: this.state.logLines,
            config: this.state.config,
            connected: this.state.connected,
            runStatus: this.state.runStatus,
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
         elem(XYPlotPane,
           {config: this.state.config,
            plotVals: this.state.plotVals,
            clearPlots: this.clearPlots,
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

function Render() {
  document.getElementById('title').innerHTML = projectTitle;

  const tabDiv = document.getElementById('tabs_container');
  ReactDOM.render(elem(TopPane), tabDiv);
}

Render()
