// ADO simulator board (feature 017): two small behaviours the strict content security policy
// keeps out of the templates. (1) A failed refresh shows the "not current" banner; the next
// successful refresh replaces the columns, banner hidden. (2) A collapsed column the person opened
// stays open across refreshes: its state travels with each poll as an "open" field.
document.addEventListener("htmx:sendError", showStale);
document.addEventListener("htmx:responseError", showStale);
function showStale() {
  var stale = document.getElementById("stale");
  if (stale) { stale.hidden = false; }
}
document.addEventListener("toggle", function (event) {
  var details = event.target;
  if (!(details instanceof HTMLDetailsElement) || !details.closest("#columns")) { return; }
  var heading = details.querySelector("summary h2");
  var state = heading ? heading.firstChild.textContent.trim() : "";
  var marker = details.querySelector("input[name='open']");
  if (details.open && !marker) {
    marker = document.createElement("input");
    marker.type = "hidden"; marker.name = "open"; marker.value = state;
    details.appendChild(marker);
  } else if (!details.open && marker) {
    marker.remove();
  }
}, true);
