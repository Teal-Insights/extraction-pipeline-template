/**
 * Column placement for the viewer's layered layout.
 *
 * Node boxes grow with their value text (up to 360 px), so a constant column
 * pitch lets wide neighbours overlap. columnXs spaces each column from the
 * previous one by half of each column's widest box plus a fixed gap.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SeriesGraphLayeredLayout = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  /**
   * @param {{columns: string[][], widths: Record<string, number>,
   *   originX: number, gap: number}} o
   * @returns {number[]} x of each column's centre line.
   */
  function columnXs(o) {
    const halfWidths = o.columns.map(
      (col) => Math.max(0, ...col.map((id) => o.widths[id])) / 2,
    );
    const xs = [];
    halfWidths.forEach((half, index) => {
      xs.push(index === 0 ? o.originX : xs[index - 1] + halfWidths[index - 1] + o.gap + half);
    });
    return xs;
  }

  return { columnXs };
});
