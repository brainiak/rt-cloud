const React = require('react')
const ReactDOM = require('react-dom')
const dateformat = require('dateformat');
const path = require('path');
const SettingsPane = require('./settingsPane.js')
const StatusPane = require('./statusPane.js')
const XYPlotPane = require('./xyplotPane.js')
const UploadFilesPane = require('./uploadFilesPane.js')
const { Tab, Tabs, TabList, TabPanel } = require('react-tabs')

const elem = React.createElement;

const logLineStyle = {
    margin: '0',
}

// This will be updated based on the value in the config file
var projectTitle = 'Real-Time Study';

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
      classVals: [[{x:0, y:0}], []], // classification results
      logLines: [],  // image classification log
      uploadedFileLog: [],
    }
    this.classVals = [[], [{x:0, y:0}]]
    this.webSocket = null
    this.setConfigFileName = this.setConfigFileName.bind(this);
    this.setConfig = this.setConfig.bind(this);
    this.getConfigItem = this.getConfigItem.bind(this);
    this.setConfigItem = this.setConfigItem.bind(this);
    this.requestDefaultConfig = this.requestDefaultConfig.bind(this)
    this.startRun = this.startRun.bind(this);
    this.stopRun = this.stopRun.bind(this);
    this.uploadFiles = this.uploadFiles.bind(this);
    this.createWebSocket = this.createWebSocket.bind(this)
    this.formatConfigValues = this.formatConfigValues.bind(this)
    this.clearRunStatus = this.clearRunStatus.bind(this)
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

  formatConfigValues(cfg) {
    // After user changes on the web page we need to convert some values from strings
    // First format Runs and ScanNums to be numbers not strings
    var runs = cfg['Runs']
    var scans = cfg['ScanNums']
    if (! Array.isArray(runs) || ! Array.isArray(scans)) {
      this.setState({error: 'Runs or ScanNums must be an array'})
      return null
    }
    if (typeof runs[0] === 'string') {
      if (runs.length > 1) {
        this.setState({error: 'Runs is string array > length 1'})
        return null
      }
      cfg['Runs'] = runs[0].split(',').map(Number);
    }

    if (typeof scans[0] === 'string') {
      if (scans.length > 1) {
        this.setState({error: 'Scans is string array > length 1'})
        return null
      }
      cfg['ScanNums'] = scans[0].split(',').map(Number);
    }

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
        this.setConfig(config)
      } else if (cmd == 'userLog') {
        var logItem = request['value'].trim()
        var itemPos = this.state.logLines.length + 1
        var newLine = elem('pre', { style: logLineStyle,  key: itemPos }, logItem)
        // Need to use concat() to create a new logLines object or React won't know to re-render
        var logLines = this.state.logLines.concat([newLine])
        this.setState({logLines: logLines})
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
      } else if (cmd == 'classificationResult') {
        var runId = request['runId']
        var vol = request['trId']
        var classVal = request['value']
        // Make sure classVals has at least as many arrays as runIds
        for (let i = this.classVals.length; i < runId; i++) {
          this.classVals.push([])
        }
        // clear plots with runId greater than the current one
        for (let i = runId; i < this.classVals.length; i++) {
          this.classVals[i] = []
        }
        // console.log(`classificationResult: ${classVal} ${vol} ${runId}`)
        if (typeof(vol) == 'number') {
          // ClassVals is zero-based and runId is 1-based, so classVal index will be runId-1
          // add new data point to classVals for this runId
          var runClassVals = this.classVals[runId-1]
          var itemPos = runClassVals.length + 1
          runClassVals.push({x: itemPos, y: classVal})
          this.setState({classVals: this.classVals})
        } else {
          // vol is not a number, clear the classVals for this run
          this.classVals[runId-1] = []
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
         elem(Tab, {}, 'Settings'),
         elem(Tab, {}, 'Upload Files'),
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
            classVals: this.state.classVals,
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
           }
         ),
       ),
       elem(TabPanel, {},
         elem(UploadFilesPane,
           {uploadFiles: this.uploadFiles,
            uploadedFileLog: this.state.uploadedFileLog,
            error: this.state.error,
           }
         ),
       ),
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
