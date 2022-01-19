const React = require('react')
const RFB = require('@novnc/novnc').default
// import RFB from '../lib/rfb.js';

const elem = React.createElement
var rfb = null; // global vnc remote framebuffer

const topBarStyle = {
    backgroundColor: '#6e84a3',
    color: 'white',
    font: 'bold 12px Helvetica',
    padding: '6px 5px 4px 5px',
    borderBottom: '1px outset',
}

const statusTextStyle = {
    textAlign: 'center',
}

function initVncConnection(url) {
  rfb = new RFB(document.getElementById('screen'), url, {/* credentials: { password: password } */})
  rfb.focusOnClick = true
  rfb.clipViewport = false
  // this.rfb.showDotCursor = true
}

class VNCViewerPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      status: 'Loading',
      desktopName: 'FSL Viewer',
      vncUrl: '',
    }
    // console.log(document.location.href)
    this.state.vncUrl = 'wss://' + window.location.hostname + ':6080'
    this.connectedToServer = this.connectedToServer.bind(this)
    this.disconnectedFromServer = this.disconnectedFromServer.bind(this)
    this.credentialsAreRequired = this.credentialsAreRequired.bind(this)
    this.updateDesktopName = this.updateDesktopName.bind(this)
    this.reconnectToVnc = this.reconnectToVnc.bind(this)
    if (rfb == null) {
      initVncConnection(this.state.vncUrl)
    }
    this.rfb = rfb
    // Add listeners to important events from the RFB module
    this.rfb.addEventListener("connect",  this.connectedToServer);
    this.rfb.addEventListener("disconnect", this.disconnectedFromServer);
    this.rfb.addEventListener("credentialsrequired", this.credentialsAreRequired);
    this.rfb.addEventListener("desktopname", this.updateDesktopName);
  }

  reconnectToVnc() {
    initVncConnection(this.state.vncUrl)
    this.rfb = rfb
  }

  // When this function is called we have
  // successfully connected to a server
  connectedToServer(e) {
      var status = "Connected to " + this.state.desktopName
      this.setState({ status: status })
  }

  // This function is called when we are disconnected
  disconnectedFromServer(e) {
      if (e.detail.clean) {
          this.setState({ status: "Disconnected" })
      } else {
          this.setState({ status: "Something went wrong, connection is closed" })
      }
  }

  // When this function is called, the server requires
  // credentials to authenticate
  credentialsAreRequired(e) {
      const password = prompt("Password Required:");
      this.rfb.sendCredentials({ password: password });
  }

  // When this function is called we have received
  // a desktop name from the server
  updateDesktopName(e) {
      this.desktopName = e.detail.name;
  }

  render() {
    return (
      <div>
        <div style={topBarStyle}>
          <div style={statusTextStyle}>
            {this.state.status}
            <button
              style={{float: "right", margin: "0px 0px 0px 0px", fontSize: "0.75em"}}
              onClick={this.reconnectToVnc}>
            Reconnnect
            </button>
          </div>
        </div>
      </div>
    )
  }
}

module.exports = VNCViewerPane;
