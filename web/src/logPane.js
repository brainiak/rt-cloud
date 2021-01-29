const React = require('react')
import AutoscrolledList from "./AutoscrolledList";

const elem = React.createElement;


class LogPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
  }

  render() {
    var errorStr
    if (this.props.error != '') {
      errorStr = "Error: " + this.props.error
    }
    return (
      <div>
        <p>Status: {(this.props.connected) ? this.props.runStatus : 'disconnected'}</p>
        <p>{errorStr}</p>
        <hr />
        <AutoscrolledList items={this.props.logLines} height="600px" />
      </div>
    );
  }
}

module.exports = LogPane;
