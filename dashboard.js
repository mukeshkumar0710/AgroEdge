/**
 * Geospatial Command Dashboard Orchestrator.
 * Connects Leaflet map, MarkerCluster, SSE real-time stream, and KPI counters.
 */

// Global State
let map;
let markerClusterGroup;
let allIncidents = [];
let activeMarkersMap = new Map(); // incident_id -> L.CircleMarker
let activeFilterSeverity = 'ALL';

const SEVERITY_COLORS = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#10b981'
};

// DOM Elements
const kpiTotal = document.getElementById('kpi-total');
const kpiCritical = document.getElementById('kpi-critical');
const kpiConfidence = document.getElementById('kpi-confidence');
const feedContainer = document.getElementById('feed-container');
const filterSeverity = document.getElementById('filter-severity');
const btnSimulate = document.getElementById('btn-simulate');

// 1. Initialize Map
function initMap() {
  map = L.map('map', {
    zoomControl: true,
    minZoom: 3
  }).setView([20.5937, 78.9629], 5);

  // CartoDB Dark Matter Tiles
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
  }).addTo(map);

  // Initialize MarkerCluster Group
  markerClusterGroup = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: 45,
    spiderfyOnMaxZoom: true,
    showCoverageOnHover: false
  });

  map.addLayer(markerClusterGroup);
}

// 2. Marker Factory
function createIncidentMarker(feature) {
  const [lng, lat] = feature.geometry.coordinates;
  const props = feature.properties;
  const color = SEVERITY_COLORS[props.severity] || '#38bdf8';

  const marker = L.circleMarker([lat, lng], {
    radius: 9,
    fillColor: color,
    color: '#ffffff',
    weight: 1.5,
    opacity: 0.95,
    fillOpacity: 0.85
  });

  const popupHtml = `
    <div style="font-family: inherit; font-size: 13px; line-height: 1.4;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <strong style="color: #f8fafc; font-size: 14px;">${props.condition}</strong>
        <span class="badge badge-${props.severity.toLowerCase()}">${props.severity}</span>
      </div>
      <div style="color: #94a3b8; font-size: 11px; margin-bottom: 8px;">
        Agent: <code>${props.agent_id || 'pwa-edge'}</code> • Conf: <strong>${(props.confidence * 100).toFixed(1)}%</strong>
      </div>
      <div style="background: rgba(255,255,255,0.06); padding: 8px; border-radius: 6px; margin-bottom: 8px;">
        <span style="color: #38bdf8; font-weight: 600; font-size: 11px; display: block; margin-bottom: 2px;">Localized Action Plan:</span>
        <span style="color: #e2e8f0; font-size: 12px;">${props.treatment_plan}</span>
      </div>
      <div style="font-size: 11px; color: #64748b;">
        Coordinates: ${lat.toFixed(4)}, ${lng.toFixed(4)}
      </div>
    </div>
  `;

  marker.bindPopup(popupHtml, { maxWidth: 300 });
  return marker;
}

// 3. Process & Add Incident
function addIncidentToDashboard(feature, isNewLive = false) {
  // Prevent duplicate additions
  if (allIncidents.some(i => i.id === feature.id)) return;

  allIncidents.unshift(feature);

  // Add marker
  const marker = createIncidentMarker(feature);
  activeMarkersMap.set(feature.id, marker);

  if (activeFilterSeverity === 'ALL' || feature.properties.severity === activeFilterSeverity) {
    markerClusterGroup.addLayer(marker);
  }

  // Prepend to activity feed
  renderFeedItem(feature, isNewLive);

  // Recalculate KPIs
  updateKpiMetrics();

  if (isNewLive) {
    const [lng, lat] = feature.geometry.coordinates;
    map.panTo([lat, lng], { animate: true, duration: 1 });
    marker.openPopup();
  }
}

// 4. Render Feed Item
function renderFeedItem(feature, isNew = false) {
  const props = feature.properties;
  const [lng, lat] = feature.geometry.coordinates;
  const timeFormatted = new Date(props.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const itemEl = document.createElement('div');
  itemEl.className = 'feed-item';
  itemEl.id = `feed-${feature.id}`;

  itemEl.innerHTML = `
    <div class="feed-item-top">
      <div class="feed-item-title">${props.condition}</div>
      <span class="badge badge-${props.severity.toLowerCase()}">${props.severity}</span>
    </div>
    <div class="feed-item-treatment">${props.treatment_plan}</div>
    <div class="feed-item-time" style="margin-top: 4px;">${timeFormatted} • [${lat.toFixed(2)}, ${lng.toFixed(2)}]</div>
  `;

  itemEl.addEventListener('click', () => {
    map.flyTo([lat, lng], 12, { animate: true, duration: 1.2 });
    const marker = activeMarkersMap.get(feature.id);
    if (marker) {
      markerClusterGroup.zoomToShowLayer(marker, () => {
        marker.openPopup();
      });
    }
  });

  feedContainer.prepend(itemEl);

  // Keep feed to latest 25 items
  if (feedContainer.children.length > 25) {
    feedContainer.removeChild(feedContainer.lastChild);
  }
}

// 5. KPI Calculator
function updateKpiMetrics() {
  const total = allIncidents.length;
  kpiTotal.textContent = total;

  const critical = allIncidents.filter(i => i.properties.severity === 'CRITICAL' || i.properties.severity === 'HIGH').length;
  kpiCritical.textContent = critical;

  if (total > 0) {
    const avgConf = (allIncidents.reduce((acc, curr) => acc + curr.properties.confidence, 0) / total) * 100;
    kpiConfidence.textContent = `${avgConf.toFixed(1)}%`;
  }
}

// 6. Filter Handling
function applyFilters() {
  activeFilterSeverity = filterSeverity.value;
  markerClusterGroup.clearLayers();

  allIncidents.forEach((feat) => {
    const marker = activeMarkersMap.get(feat.id);
    if (!marker) return;

    if (activeFilterSeverity === 'ALL' || feat.properties.severity === activeFilterSeverity) {
      markerClusterGroup.addLayer(marker);
    }
  });
}

// 7. Initial Fetch
async function loadInitialIncidents() {
  try {
    const res = await fetch('/api/v1/incidents/geojson');
    if (res.ok) {
      const data = await res.json();
      data.features.forEach((feature) => {
        addIncidentToDashboard(feature, false);
      });
    }
  } catch (err) {
    console.error('[Dashboard] Error fetching initial GeoJSON:', err);
  }
}

// 8. Connect to Real-Time SSE Stream
function connectRealTimeStream() {
  const eventSource = new EventSource('/api/v1/dashboard/stream');

  eventSource.onmessage = (event) => {
    try {
      const feature = JSON.parse(event.data);
      if (feature && feature.geometry) {
        addIncidentToDashboard(feature, true);
      }
    } catch (err) {
      console.warn('[SSE] Parse warning:', err);
    }
  };

  eventSource.onerror = (err) => {
    console.warn('[SSE] Connection issue. Auto-reconnecting...', err);
  };
}

// 9. Simulation Trigger (Demo Helper)
btnSimulate.addEventListener('click', async () => {
  btnSimulate.disabled = true;
  btnSimulate.textContent = 'Simulating Outbreak Ping...';

  const conditions = ["PestInfestation", "BacterialBlight", "EarlyBlightFungus", "NutrientChlorosis"];
  const severities = ["CRITICAL", "HIGH", "MEDIUM"];
  const langs = ["en", "hi", "ta", "te", "es", "bn"];

  const randomCondition = conditions[Math.floor(Math.random() * conditions.length)];
  const randomSeverity = severities[Math.floor(Math.random() * severities.length)];
  const randomLang = langs[Math.floor(Math.random() * langs.length)];

  try {
    await fetch('/api/v1/simulate-incident', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        condition: randomCondition,
        severity: randomSeverity,
        language_code: randomLang
      })
    });
  } catch (e) {
    console.error('Simulation error:', e);
  } finally {
    setTimeout(() => {
      btnSimulate.disabled = false;
      btnSimulate.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
        </svg>
        Trigger Simulated Edge Ping
      `;
    }, 400);
  }
});

filterSeverity.addEventListener('change', applyFilters);

// Boot
initMap();
loadInitialIncidents();
connectRealTimeStream();
