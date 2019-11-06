const React = require('react')
const toml = require('toml')

const elem = React.createElement;

const AdvancedBarStyle = {
    backgroundColor: '#6e84a3',
    color: 'white',
    font: 'bold 12px Helvetica',
    padding: '6px 5px 4px 5px',
    borderBottom: '1px outset',
    cursor: 'pointer',
    textAlign: 'center',
}

class SettingsPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
      tomlErrorMsg: '',
      showAdvancedOptions: false,
    }
    this.tomlInputForm = this.tomlInputForm.bind(this)
    this.loadTomlFile = this.loadTomlFile.bind(this)
    this.inputOnChange = this.inputOnChange.bind(this)
    this.textInputField = this.textInputField.bind(this)
    this.settingsInputForm = this.settingsInputForm.bind(this)
    this.toggleAdvancedOptions = this.toggleAdvancedOptions.bind(this)
  }

  tomlInputForm(props) {
    const form = (
        <fieldset>
          <legend>Select Toml Configuration File:</legend>
          <p>Current Config: {this.props.configFileName}</p>
          <input type='file' className='inputfile'
            onChange={(event) => {
              this.props.setConfigFileName(event.target.files[0].name)
              let reader = new FileReader()
              reader.onload = this.loadTomlFile
              reader.readAsText(event.target.files[0])
            }}
          />
          <br />
          <button className="smallButton"
            onClick={this.props.requestDefaultConfig}>
            Reload Default Config
          </button>
          <p>{this.state.tomlErrorMsg}</p>
        </fieldset>
      );
    return form
  }

  loadTomlFile(event) {
    try {
      const configData = toml.parse(event.target.result)
      this.props.setConfig(configData)
    } catch (err) {
      this.setState({ tomlErrorMsg: err.message })
    }
  }

  inputOnChange(event) {
    var revConfig = Object.assign({}, this.props.config, { [event.target.name]: event.target.value })
    this.props.setConfig(revConfig)
  }

  textInputField(props) {
    return (
      <div key={props.name} className="row">
        <label className="cell10p">{props.name}:</label>
        <input className="cell5p" size="20"
          {...props}
          value={this.props.config[props.name]}
          onChange={this.inputOnChange} />
      </div>
    );
  }

  settingsInputForm(props) {
    var optionBar =
    (
        <div style={AdvancedBarStyle}
          onClick={this.toggleAdvancedOptions}
          key='optionBar' value=''>
            {(this.state.showAdvancedOptions) ? 'hide' : 'show'} advanced options
        </div>
    );

    var subform = []
    var addEndBar = false
    for (var key in this.props.config) {
      if (key == 'advancedOptionDemarcation') {
        if (this.state.showAdvancedOptions == false) {
          subform.push(optionBar)
          break
        } else {
          addEndBar = true
          continue
        }
      }
      subform.push(this.textInputField({ name: key }))
    }

    if (addEndBar) {
      subform.push(optionBar)
    }

    const form = (
      <fieldset>
        <legend>Configurations</legend>
        <div>{subform}</div>
      </fieldset>
    );
    return form
  }

  toggleAdvancedOptions(event) {
    var showAdvOptions = this.state.showAdvancedOptions ? false : true;
    this.setState({showAdvancedOptions: showAdvOptions})
  }

  render() {
    // if (this.errorMsg) {
    // var errElem = elem('span', {}, this.errorMsg)
    // }
    return elem('div', {},
      this.tomlInputForm({}),
      elem('br'),
      this.settingsInputForm({})
    )
  }
}

module.exports = SettingsPane;
