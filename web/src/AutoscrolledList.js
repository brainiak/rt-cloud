import React from "react";
import autoscroll from "autoscroll-react";

// const styles = {
//   overflowY: "scroll",
//   height: "600px"
// };

class List extends React.Component {
  render() {
    const { items, height, ...props } = this.props;

    const styles = {
      overflowY: "scroll",
      height: height,
    };

    return (
      <div style={styles} {...this.props}>
        {items}
      </div>
    );
  }
}
// {items.map((item, idx) => <pre key={idx}>{item}</pre>)}
export default autoscroll(List, { isScrolledDownThreshold: 5 });
