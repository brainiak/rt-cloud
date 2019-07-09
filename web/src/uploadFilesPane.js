const React = require('react');
import AutoscrolledList from "./AutoscrolledList";

const elem = React.createElement;


class UploadFilesPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
        srcFile: '',
        compress: false,
    }
    this.inputOnChange = this.inputOnChange.bind(this)
    this.checkOnChange = this.checkOnChange.bind(this)
    this.uploadBttnOnClick = this.uploadBttnOnClick.bind(this)
  }

  inputOnChange(event) {
    var name = event.target.name
    var val = event.target.value;
    this.setState({[name]: val})
  }

  checkOnChange(event) {
    var name = event.target.name
    var isChecked = event.target.checked
    this.setState({[name]: isChecked})
  }

  uploadBttnOnClick(event) {
    this.props.uploadFiles(this.state.srcFile, this.state.compress)
  }

  render() {
    var errorStr
    if (this.props.error != '') {
      errorStr = "Error: " + this.props.error
    }
    return (
      <div>
        <div className="table">
          <div>
              <label className="cell5p">Upload filepattern:</label>
              <input className="cell5p" size="60"
                  name='srcFile'
                  value={this.state.srcFile}
                  onChange={this.inputOnChange}
              />
          </div>
          <div style={{whiteSpace: 'nowrap', display: 'inline'}}>
              <input className="cell10p" type="checkbox"
                  name="compress"
                  checked={this.state.compress}
                  onChange={this.checkOnChange}
                  float="left"
              />
              <label className="cell10p" float="right">compress in transit</label>
          </div>
          <div>
              <button className={"cell5p"}
                  name="upload"
                  onClick={this.uploadBttnOnClick}>Upload Files
              </button>
          </div>
          <div>
              <small>Files will be copied to the same path prepended by /rtfmriData/
              <br />
              100 MB max file size
              </small>
          </div>
        </div>
        <p> {errorStr} </p>
        <hr />
        <AutoscrolledList items={this.props.uploadedFileLog} height="500px" />
      </div>
    );
    // <br />
    // <label className="cell5p">Copy To [Local dir]:</label>
    // <input className="cell5p" size="50"
    //   name='dstDir'
    //   value={this.state.destDir}
    //   onChange={this.inputOnChange}
    // />
  }
}

module.exports = UploadFilesPane;
