import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><div id=root></div>", { url: "http://localhost/sbx-b2b-login" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document,
  HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
let mode = "503", release;
globalThis.fetch = async (...args) => {
  console.error("FETCH", mode);
  if (mode === "pending") await new Promise((r) => { release = r; });
  return new Response(JSON.stringify({ outcome: "SERVICE_UNAVAILABLE", correlation_id: "c-1", error_code: "SBX-B2B-E-NETWORK" }),
    { status: 503, headers: { "content-type": "application/json" } });
};
const { act } = await import("react");
const { createRoot } = await import("react-dom/client");
const React = await import("react");
const Page = (await import("./bundle.mjs")).default;
const out = [];
async function render() {
  document.body.innerHTML = "<div id=root></div>";
  const root = createRoot(document.getElementById("root"));
  await act(async () => root.render(React.createElement(Page)));
  const set = (sel, v) => { const el = document.querySelector(sel);
    const proto = Object.getPrototypeOf(el); Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
    el.dispatchEvent(new window.Event("input", { bubbles: true })); };
  await act(async () => { set("#sbx-email", "demo@sandbox.test"); set("#sbx-password", "x"); });
  return root;
}
// F-ERROR-CTA-NOT-ACTIONABLE
mode = "503"; await render();
await act(async () => { document.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })); });
for (let i = 0; i < 20; i++) await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
console.error("DBG", document.getElementById("root").textContent.slice(0,300), document.querySelector("#sbx-email").value);
const alert = document.querySelector('[role="alert"]');
const ctaText = "Reintentar";
const actionable = [...alert.querySelectorAll("button, a[href]")].some((e) => e.textContent.includes(ctaText));
out.push({ case: "CTA_on_E_NETWORK", alert_text_has_cta: alert.textContent.includes(ctaText), cta_actionable: actionable });
// control: the submit button itself is actionable
out.push({ case: "CTA_control_submit_is_button", value: document.querySelector('button[type="submit"]') !== null });
// F-SINGLE-FLIGHT-NO-PROCESSING-LABEL
mode = "pending"; await render();
await act(async () => { document.querySelector("form").dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })); });
const btn = document.querySelector('button[type="submit"]');
out.push({ case: "PENDING_state", disabled: btn.disabled, button_text: btn.textContent.trim(),
  live_region: document.querySelector('[role="status"]').textContent });
for (let i = 0; i < 50 && !release; i++) await act(async () => { await new Promise((r) => setTimeout(r, 20)); });
console.error("PENDING_DBG", JSON.stringify(out));
await act(async () => { release(); await new Promise((r) => setTimeout(r, 50)); });
out.push({ case: "PENDING_control_after_response", disabled: document.querySelector('button[type="submit"]').disabled });
for (const o of out) console.log(JSON.stringify(o));
process.exit(0);
