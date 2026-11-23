// The Plotly.js basic bundle (scatter, bar, pie; no WebGL) has the full library's API.
declare module "plotly.js-basic-dist-min" {
  import type * as Plotly from "plotly.js";
  const plotly: typeof Plotly;
  export default plotly;
}
