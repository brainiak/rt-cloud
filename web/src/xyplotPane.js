const React = require('react')
import {XYPlot, FlexibleXYPlot, XAxis, YAxis, ChartLabel, HorizontalGridLines, LineSeries, LineMarkSeries} from 'react-vis';

function parseBoolean(str) {
  switch (String(str).toLowerCase()) {
    case "true":
    case "1":
    case "yes":
    case "y":
      return true;
    case "false":
    case "0":
    case "no":
    case "n":
      return false;
    default:
      // could throw an error, but return false for now
      return false;
  }
}

class XYPlotPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
    this.renderRunGraph = this.renderRunGraph.bind(this);
  }

  renderRunGraph(runPlotVals, runId) {
    var xLabel = this.props.config['plotXLabel']
    var yLabel = this.props.config['plotYLabel']
    var autoRangeX = parseBoolean(this.props.config['plotAutoRangeX'])
    var autoRangeY = parseBoolean(this.props.config['plotAutoRangeY'])
    var xRangeLow = this.props.config['plotXRangeLow'] || 0;
    var xRangeHigh = this.props.config['plotXRangeHigh'] || 0;
    var yRangeLow = this.props.config['plotYRangeLow'] || 0;
    var yRangeHigh = this.props.config['plotYRangeHigh'] || 0;
    if (autoRangeX || autoRangeY) {
        var minY, minX, maxY, maxX
        minY = minX = Number.MAX_VALUE
        maxY = maxX = Number.MIN_VALUE
        for (let i = 0; i < runPlotVals.length; i++) {
          var xval = runPlotVals[i]['x']
          var yval = runPlotVals[i]['y']
          if (xval > maxX) {
              maxX = xval
          }
          if (xval < minX) {
              minX = xval
          }
          if (yval > maxY) {
              maxY = yval
          }
          if (yval < minY) {
              minY = yval
          }
        }
    }
    if (autoRangeX) {
        xRangeLow = minX
        xRangeHigh = maxX
    }
    if (autoRangeY) {
        yRangeLow = minY
        yRangeHigh = maxY
    }
    var xRange = [xRangeLow, xRangeHigh]
    var yRange = [yRangeLow, yRangeHigh]
    var uniqueKey = runId.toString() // + '.' + numPoints.toString()
    var plotColor = '#E0E0E0'
    var plotMargins = {left: 120, right: 25, top: 15, bottom: 70}
    var axesStyle = {
      text: {stroke: 'none', fill: plotColor, fontSize: '1.2em'},
      title: {stroke: 'none', fill: plotColor, fontSize: '1.2em'}
    }
    // Note: I couldn't get ChartLabel style={} to change the text style
    //  so instead it is set in react-vis.css .rv-xy-plot__axis__title
    return (
      <div key={uniqueKey}>
        <p style={{fontSize: '1.4em'}}>Run {runId}</p>
        <XYPlot
          width={1000}
          height={300}
          xDomain={xRange}
          yDomain={yRange}
          margin={plotMargins}
        >
          <HorizontalGridLines />
          <LineMarkSeries
            animation
            color={plotColor}
            data={runPlotVals}/>
          <XAxis style={axesStyle} tickTotal={11} />
          <ChartLabel
            text={xLabel}
            className="x-label"
            includeMargin={false}
            xPercent={0.48}
            yPercent={1.35}
            style={{
                textAnchor: 'middle',
                fill: plotColor,
                fontSize: 'large'
            }}
          />
          <YAxis style={axesStyle} tickPadding={5}/>
          <ChartLabel
            text={yLabel}
            className="y-label"
            includeMargin={true}
            xPercent={0.04}
            yPercent={0.01}
            style={{
              transform: 'rotate(-90)',
              textAnchor: 'middle',
              fill: plotColor,
              fontSize: 'large'
            }}
          />
        </XYPlot>
        <br />
        <hr />
      </div>
    )
  }

  render() {
    var numRuns = this.props.plotVals.length
    var plots = []
    for (let i = 0; i < numRuns; i++) {
      if (this.props.plotVals[i].length != 0) {
        plots[i] = this.renderRunGraph(this.props.plotVals[i], i+1)
      }
    }
    return (
      <div>
        <br />
        <div style={{fontSize: '1.5em'}}>
          {this.props.config['plotTitle']}
          <button
            style={{float: "right", margin: "0px 0px 0px 0px", fontSize: "0.5em"}}
            onClick={this.props.clearPlots}
          >
            Clear Plots
          </button>
        </div>
        <hr />
        {plots}
      </div>
    )
  }
}

module.exports = XYPlotPane;
