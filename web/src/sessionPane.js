const React = require('react')
import AutoscrolledList from "./AutoscrolledList";

const elem = React.createElement;


class SessionPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
    this.initBttnOnClick = this.initBttnOnClick.bind(this)
    this.finalizeBttnOnClick = this.finalizeBttnOnClick.bind(this)
    this.stopBttnOnClick = this.stopBttnOnClick.bind(this)
  }

  initBttnOnClick(event) {
    this.props.runSession('initScript')
  }

  finalizeBttnOnClick(event) {
    this.props.runSession('finalizeScript')
  }

  stopBttnOnClick(event) {
    this.props.stopRun()
  }

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
        <p>Run scripts that initialize or finalize the session</p>
        <span className="statusText">
          subjectNum: {this.props.getConfigItem('subjectNum')}
          &emsp;
          subjectDay: {this.props.getConfigItem('subjectDay')}
        </span>
        <br />
        <button onClick={this.initBttnOnClick}>Initialize Session</button>
        <button onClick={this.finalizeBttnOnClick}>finalize Session</button>
        <button onClick={this.stopBttnOnClick}>Stop</button>
        <p>Status: {(this.props.connected) ? this.props.runStatus : 'disconnected'}</p>
        <p>{errorStr}</p>
        <hr />
        <AutoscrolledList items={this.props.sessionLog} height="600px" />
      </div>
    );
  }
}

module.exports = SessionPane;
