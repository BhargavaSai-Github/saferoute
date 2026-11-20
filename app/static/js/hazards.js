/**
 * SafeRoute Hazard Markers, Category Filtering & Realtime Stream Controller (Issue B4).
 *
 * Integrates with SafeRouteMap (Issue B3) to query visible bounding box hazards,
 * render severity-colored pins, manage marker popups, and listen for live SSE events.
 */
(function () {
  "use strict";

  var hazardLayerGroup = null;
  var hazardsMap = {};
  var activeCategory = null;
  var showFixed = false;
  var boundsTimer = null;
  var eventSource = null;

  function sanitizeText(text) {
    return String(text || "").replace(/[<>&"]/g, "");
  }

  function getCategoryIcon(cat) {
    switch (cat) {
      case "pothole":
        return "🕳️";
      case "road_break":
        return "🚧";
      case "streetlight":
        return "💡";
      case "footpath":
        return "🚶";
      default:
        return "⚠️";
    }
  }

  function getSeverityColor(score) {
    if (score >= 70) return "#D92D20";
    if (score >= 40) return "#F5A524";
    return "#2E9E5B";
  }

  function renderHazardMarkers(items) {
    var map = window.SafeRouteMap ? window.SafeRouteMap.getMap() : null;
    if (!hazardLayerGroup || !map) return;

    hazardLayerGroup.clearLayers();
    hazardsMap = {};

    items.forEach(function (h) {
      if (!window.SafeRouteMap.isValidCoordinates(h.lat, h.lng)) return;
      var color = getSeverityColor(h.severity_score);
      var iconEmoji = getCategoryIcon(h.category);

      var markerIcon = window.L.divIcon({
        className: "sr-hazard-pin",
        html:
          '<div style="background-color:' +
          color +
          ';width:28px;height:28px;border-radius:50%;border:2px solid white;box-shadow:0 2px 5px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;font-size:13px;cursor:pointer;">' +
          iconEmoji +
          "</div>",
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        popupAnchor: [0, -14],
      });

      var marker = window.L.marker([h.lat, h.lng], { icon: markerIcon });
      var popupContent = [
        '<div style="min-width:180px;font-family:sans-serif;padding:2px;">',
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">',
        '<strong style="text-transform:capitalize;font-size:13px;color:#0F2A43;">' +
          sanitizeText(h.category.replace("_", " ")) +
          "</strong>",
        '<span style="font-size:10px;font-weight:bold;padding:1px 6px;border-radius:999px;background:' +
          color +
          "22;color:" +
          color +
          ';">' +
          h.severity_score +
          " / 100</span>",
        "</div>",
        '<p style="font-size:12px;color:#5B6B7C;margin:0 0 6px 0;line-height:1.3;">' +
          sanitizeText(h.address_text || h.description || "") +
          "</p>",
        '<div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;border-top:1px solid #D9E4EE;padding-top:4px;">',
        '<span style="color:#5B6B7C;">' + (h.confirm_count || 0) + " confirms</span>",
        '<a href="/reports/' +
          h.id +
          '" style="color:#106EBE;font-weight:bold;text-decoration:none;">View &rarr;</a>',
        "</div>",
        "</div>",
      ].join("");

      marker.bindPopup(popupContent);
      hazardsMap[h.id] = marker;
      hazardLayerGroup.addLayer(marker);
    });

    // Notify Alpine shell
    var shell = document.getElementById("sr-map-workspace");
    if (shell && shell.__x) {
      shell.__x.$data.hazards = items;
      shell.__x.$data.hazardCount = items.length;
    }
  }

  function fetchHazardsInBounds() {
    var map = window.SafeRouteMap ? window.SafeRouteMap.getMap() : null;
    if (!map) return;

    var b = map.getBounds();
    var minLat = b.getSouth();
    var minLng = b.getWest();
    var maxLat = b.getNorth();
    var maxLng = b.getEast();

    var url =
      "/api/reports?bounds=" +
      minLat.toFixed(5) +
      "," +
      minLng.toFixed(5) +
      "," +
      maxLat.toFixed(5) +
      "," +
      maxLng.toFixed(5);
    if (activeCategory) {
      url += "&category=" + encodeURIComponent(activeCategory);
    }
    if (!showFixed) {
      url += "&status=open";
    }

    var xhr = new window.XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.onload = function () {
      if (xhr.status === 200) {
        try {
          var res = JSON.parse(xhr.responseText);
          renderHazardMarkers(res.items || []);
        } catch (_err) {}
      }
    };
    xhr.send();
  }

  function scheduleFetchHazards() {
    if (boundsTimer) {
      window.clearTimeout(boundsTimer);
    }
    boundsTimer = window.setTimeout(fetchHazardsInBounds, 400);
  }

  function initRealtimeStream() {
    if (eventSource || typeof window.EventSource === "undefined") return;
    try {
      eventSource = new window.EventSource("/api/reports/stream");
      eventSource.onmessage = function () {
        scheduleFetchHazards();
      };
    } catch (_e) {}
  }

  function focusHazard(id) {
    var marker = hazardsMap[id];
    var map = window.SafeRouteMap ? window.SafeRouteMap.getMap() : null;
    if (marker && map) {
      map.setView(marker.getLatLng(), Math.max(map.getZoom(), 17));
      marker.openPopup();
    }
  }

  function setCategory(cat) {
    activeCategory = cat || null;
    fetchHazardsInBounds();
  }

  function setShowFixed(val) {
    showFixed = Boolean(val);
    fetchHazardsInBounds();
  }

  function initHazardsController() {
    var map = window.SafeRouteMap ? window.SafeRouteMap.getMap() : null;
    if (!map) {
      window.setTimeout(initHazardsController, 100);
      return;
    }

    hazardLayerGroup = window.L.layerGroup().addTo(map);
    map.on("moveend", scheduleFetchHazards);
    scheduleFetchHazards();
    initRealtimeStream();
  }

  window.SafeRouteHazards = {
    init: initHazardsController,
    setCategory: setCategory,
    setShowFixed: setShowFixed,
    focusHazard: focusHazard,
    refresh: scheduleFetchHazards,
  };

  document.addEventListener("DOMContentLoaded", function () {
    window.setTimeout(initHazardsController, 200);
  });
})();
