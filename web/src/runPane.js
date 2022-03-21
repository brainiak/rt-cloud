const React = require('react')
import AutoscrolledList from "./AutoscrolledList";

const elem = React.createElement;


class RunPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
    // this.scrollRef = React.createRef()
    this.runNumOnChange = this.runNumOnChange.bind(this)
    this.scanNumOnChange = this.scanNumOnChange.bind(this)
    this.runBttnOnClick = this.runBttnOnClick.bind(this)
    this.stopBttnOnClick = this.stopBttnOnClick.bind(this)

  }

  runNumOnChange(event) {
    this.props.setConfigItem('runNum', [event.target.value])
    this.props.clearRunStatus()
  }

  scanNumOnChange(event) {
    this.props.setConfigItem('scanNum', [event.target.value])
    this.props.clearRunStatus()
  }

  runBttnOnClick(event) {
    this.props.startRun()
    this.props.clearRunStatus()
  }

  stopBttnOnClick(event) {
    this.props.stopRun()
  }

  // componentDidUpdate () {
  //   this.scrollRef.scrollIntoView({ behavior: 'smooth' })
  // }
  // componentDidMount() {
  // }

  render() {
    var errorStr
    if (this.props.error != '') {
      errorStr = "Error: " + this.props.error
    }
    return (
      <div>
        <span className="connStatusText">
          browser: {(this.props.connected) ? 'connected' : 'disconnected'}
          <br />
          dataConn: {(this.props.dataConn > 0) ? 'connected' : 'disconnected'}
          <br />
          subjConn: {(this.props.subjectConn > 0) ? 'connected' : 'disconnected'}
        </span>
        <span className="statusText">
          subjectNum: {this.props.getConfigItem('subjectNum')}
          &emsp;
          subjectDay: {this.props.getConfigItem('subjectDay')}
        </span>
        <div className="table">
          <p className="row">
            <label className="cell10p">Run #:</label>
            <input className="cell5p" size="20"
              value={this.props.getConfigItem('runNum')}
              onChange={this.runNumOnChange} />
          </p>
          <p className="row">
            <label className="cell10p">Scan #:</label>
            <input className="cell5p" size="20"
              value={this.props.getConfigItem('scanNum')}
              onChange={this.scanNumOnChange} />
          </p>
        </div>
        <p>
        Run Status: {this.props.runStatus}
        </p>
        <button onClick={this.runBttnOnClick}>Run</button>
        <button onClick={this.stopBttnOnClick}>Stop</button>
        <p>{errorStr}</p>
        <hr />
        <AutoscrolledList items={this.props.userLog} height="600px" />
      </div>
    );
  }
}

module.exports = RunPane;
