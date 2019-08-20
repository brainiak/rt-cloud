const React = require('react')
import {XYPlot, FlexibleXYPlot, XAxis, YAxis, ChartLabel, HorizontalGridLines, LineSeries, LineMarkSeries} from 'react-vis';


class XYPlotPane extends React.Component {
  constructor(props) {
    super(props)
    this.state = {
    }
    this.renderRunGraph = this.renderRunGraph.bind(this);
  }

  renderRunGraph(runClassVals, runId) {
    var xLabel = this.props.config['plotXLabel']
    var yLabel = this.props.config['plotYLabel']
    var xRangeLow = this.props.config['plotXRangeLow'] || 0;
    var xRangeHigh = this.props.config['plotXRangeHigh'] || 0;
    var yRangeLow = this.props.config['plotYRangeLow'] || 0;
    var yRangeHigh = this.props.config['plotYRangeHigh'] || 0;
    var xRange = [xRangeLow, xRangeHigh]
    var yRange = [yRangeLow, yRangeHigh]
    var uniqueKey = runId.toString() // + '.' + numPoints.toString()
    var plotColor = '#E0E0E0'
    var plotMargins = {left: 90, right: 25, top: 15, bottom: 70}
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
            data={runClassVals}/>
          <XAxis style={axesStyle} tickTotal={11} />
          <ChartLabel
            text={xLabel}
            className="x-label"
            includeMargin={false}
            xPercent={0.48}
            yPercent={1.35}
            style={{fill: plotColor, fontSize: 'large'}}
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
              textAnchor: 'end',
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
        <div style={{fontSize: '1.5em'}}>{this.props.config['plotTitle']}</div>
        <hr />
        {plots}
      </div>
    )
  }
}

module.exports = XYPlotPane;
