// Fills the page's ad slots (<div class="ad" data-slot="...">) with Google AdSense units,
// once a publisher ID is set in config.js. Without one, the slots stay hidden.
(function () {
  var site = window.SITE || {};
  var client = (site.ADSENSE_CLIENT || "").trim();
  var slots = document.querySelectorAll(".ad[data-slot]");
  if (!/^ca-pub-\d{10,20}$/.test(client)) {
    slots.forEach(function (el) { el.hidden = true; });
    return;
  }
  var s = document.createElement("script");
  s.async = true;
  s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + encodeURIComponent(client);
  s.crossOrigin = "anonymous";
  document.head.appendChild(s);
  slots.forEach(function (el) {
    var id = (site.SLOTS || {})[el.dataset.slot] || "";
    el.hidden = false;
    if (!id) return; // no unit ID: Auto ads (enabled in AdSense) decides placement
    var ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", client);
    ins.setAttribute("data-ad-slot", id);
    ins.setAttribute("data-ad-format", "auto");
    ins.setAttribute("data-full-width-responsive", "true");
    el.appendChild(ins);
    (window.adsbygoogle = window.adsbygoogle || []).push({});
  });
})();
