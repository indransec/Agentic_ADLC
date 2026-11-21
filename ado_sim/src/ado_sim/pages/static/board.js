// ADO simulator board (feature 017): two small behaviours the strict content security policy
// keeps out of the templates. (1) A failed refresh shows the "not current" banner; the next
// successful refresh replaces the columns, banner hidden. (2) A collapsed column the person opened
// stays open across refreshes: its state travels with each poll as an "open" field. (3) 018: a
// backlog level the person closed stays closed: its id travels with each poll as a "closed" field.
document.addEventListener("htmx:sendError", showStale);
document.addEventListener("htmx:responseError", showStale);
function showStale() {
  var stale = document.getElementById("stale");
  if (stale) { stale.hidden = false; }
}
function mark(details, name, value, wanted) {
  var marker = details.querySelector(":scope > input[name='" + name + "']");
  if (wanted && !marker) {
    marker = document.createElement("input");
    marker.type = "hidden"; marker.name = name; marker.value = value;
    details.appendChild(marker);
  } else if (!wanted && marker) {
    marker.remove();
  }
}
document.addEventListener("toggle", function (event) {
  var details = event.target;
  if (details instanceof HTMLDetailsElement && details.closest("#rows")) {
    mark(details, "closed", details.dataset.id || "", !details.open);
  }
}, true);
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
