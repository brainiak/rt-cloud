const React = require('react')
import {XYPlot, FlexibleXYPlot, XAxis, YAxis, ChartLabel, HorizontalGridLines, LineSeries, LineMarkSeries} from 'react-vis';


function yTickFormat(val) {
  var label = ''
  if (val == 1) {
    label = 'Scene'
  } else if (val == -1) {
    label = 'Face'
  }
  return (<tspan>{label}</tspan>)
}

class XYPlotPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
    this.renderRunGraph = this.renderRunGraph.bind(this);
  }

  renderRunGraph(runClassVals, runId) {
    var numPoints = runClassVals.length
    var xHigh = (numPoints > 100) ? numPoints : 100
    var xLow = xHigh - 100
    var xRange = [xLow, xHigh]
    var uniqueKey = runId.toString() // + '.' + numPoints.toString()
    var plotColor = '#E0E0E0'
    var plotMargins = {left: 90, right: 25, top: 15, bottom: 70}
    var axesStyle = {
      text: {stroke: 'none', fill: plotColor, fontSize: '1.5em'},
      title: {stroke: 'none', fill: plotColor, fontSize: '1.5em'}
    }
    // Note: I couldn't get ChartLabel style={} to change the text style
    //  so instead it is set in react-vis.css .rv-xy-plot__axis__title
    return (
      <div key={uniqueKey}>
        <p style={{fontSize: '1.7em'}}>Run {runId}</p>
        <XYPlot
          width={1000}
          height={300}
          xDomain={xRange}
          yDomain={[-1, 1]}
          margin={plotMargins}
        >
          <HorizontalGridLines />
          <LineMarkSeries
            animation
            color={plotColor}
            data={runClassVals}/>
          <XAxis style={axesStyle} tickTotal={11} />
          <ChartLabel
            text="TR"
            className="x-label"
            includeMargin={false}
            xPercent={0.48}
            yPercent={1.4}
            style={{fill: plotColor, fontSize: 'large'}}
          />
          <YAxis style={axesStyle} tickPadding={5}/>
        </XYPlot>
        <br />
        <hr />
      </div>
    )
  }

  render() {
    var numRuns = this.props.classVals.length
    var plots = []
    for (let i = 0; i < numRuns; i++) {
      if (this.props.classVals[i].length != 0) {
        plots[i] = this.renderRunGraph(this.props.classVals[i], i+1)
      }
    }
    return (
      <div>
        <br />
        <div style={{fontSize: '2em'}}>Classification vs TR</div>
        <hr />
        {plots}
      </div>
    )
  }
}

module.exports = XYPlotPane;
