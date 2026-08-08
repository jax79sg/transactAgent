import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement scrollIntoView, which @radix-ui/react-select calls when
// its content actually opens (e.g. via defaultOpen) -- no test exercised that path
// until one actually opened the dropdown, so this went unnoticed until now.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
