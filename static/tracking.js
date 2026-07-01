let map, marker, routeLine, completedLine, timer;
let index = 0;
let points = [];
let running = false;

function selectedPlate() {
  return document.getElementById('truckSelect')?.value || 'KDG 142A';
}

function truckIcon(plate) {
  return L.divIcon({
    className: 'truck-marker',
    html: `<div class="vehicle-marker">
      <div class="vehicle-body"><span class="vehicle-cab"></span><span class="vehicle-load"></span></div>
      <div class="vehicle-plate">${plate}</div>
    </div>`,
    iconSize: [104, 54],
    iconAnchor: [52, 27]
  });
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function addLog(text) {
  const log = document.getElementById('eventLog');
  const li = document.createElement('li');
  li.textContent = text;
  log.prepend(li);
}

function updatePanel(p) {
  setText('area', p.area);
  setText('speed', `${p.speed} km/h`);
  setText('fuel', `${p.fuel} L`);
  setText('signal', p.signal);
  setText('status', p.status);
  setText('stopTime', `${p.stop} min`);

  const alertBox = document.getElementById('alertBox');
  if (p.signal === 'Lost' || p.stop >= 30 || p.status.includes('Alert')) {
    alertBox.className = 'alert-box hot';
    alertBox.textContent = 'Risk alert: extended stop, signal loss, and major fuel drop detected.';
  } else if (p.stop > 0) {
    alertBox.className = 'alert-box warn';
    alertBox.textContent = 'Vehicle stopped. Monitoring stop duration and fuel level.';
  } else {
    alertBox.className = 'alert-box quiet';
    alertBox.textContent = 'Vehicle moving normally. Signal and fuel levels are stable.';
  }
}

function updateOverlayVehicle(i) {
  const coords = [
    [16, 76], [22, 66], [31, 56], [39, 49], [48, 42],
    [56, 37], [62, 35], [69, 35], [77, 31], [84, 26]
  ];
  const vehicle = document.getElementById('overlayVehicle');
  const progress = document.getElementById('overlayProgress');
  if (!vehicle || !progress) return;
  const pos = coords[Math.max(0, Math.min(i, coords.length - 1))];
  vehicle.style.left = `${pos[0]}%`;
  vehicle.style.top = `${pos[1]}%`;
  vehicle.querySelector('strong').textContent = selectedPlate();
  const pct = i / (coords.length - 1);
  progress.style.strokeDashoffset = String(260 - (260 * pct));
}

function drawPoint(i) {
  if (!points.length) return;
  index = Math.max(0, Math.min(i, points.length - 1));
  const p = points[index];
  const latlng = [p.lat, p.lng];
  marker.setIcon(truckIcon(selectedPlate()));
  marker.setLatLng(latlng);
  marker.bindTooltip(`${selectedPlate()} · ${p.area}`, { permanent: false, direction: 'top' });
  completedLine.setLatLngs(points.slice(0, index + 1).map(point => [point.lat, point.lng]));
  updateOverlayVehicle(index);
  updatePanel(p);
  addLog(p.message);
}

function step() {
  if (!running) return;
  drawPoint(index + 1);
  if (index >= points.length - 1) {
    running = false;
    clearInterval(timer);
    addLog('Route complete: vehicle arrived at Kisumu delivery point.');
  }
}

function addOtherTrails() {
  const trails = [
    {
      name: 'Nairobi to Mombasa corridor',
      color: '#94a3b8',
      pts: [[-1.286389,36.817223],[-1.5177,37.2634],[-2.2717,38.0126],[-3.3961,38.5561],[-4.0435,39.6682]]
    },
    {
      name: 'Nairobi to Eldoret corridor',
      color: '#64748b',
      pts: [[-1.286389,36.817223],[-0.7167,36.4333],[-0.3031,36.0800],[0.5143,35.2698]]
    },
    {
      name: 'Kisumu regional return route',
      color: '#cbd5e1',
      pts: [[-0.0917,34.7680],[-0.6773,34.7796],[-1.0634,34.4731]]
    }
  ];
  trails.forEach(t => {
    L.polyline(t.pts, { color: t.color, weight: 3, opacity: 0.65, dashArray: '6 8' })
      .addTo(map)
      .bindTooltip(t.name);
  });
}

async function init() {
  const res = await fetch('/api/demo-route');
  const data = await res.json();
  points = data.points;
  setText('routeName', data.route);

  map = L.map('map', { zoomControl: true, scrollWheelZoom: true }).setView([-0.70, 35.82], 7);
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    maxZoom: 16,
    attribution: 'Tiles &copy; Esri &mdash; Sources: Esri, HERE, Garmin, OpenStreetMap contributors'
  }).addTo(map);

  addOtherTrails();
  const latlngs = points.map(p => [p.lat, p.lng]);
  routeLine = L.polyline(latlngs, { color: '#020617', weight: 14, opacity: 0.95 }).addTo(map).bindTooltip('Assigned route: Nairobi to Kisumu');
  completedLine = L.polyline([], { color: '#2563eb', weight: 8, opacity: 1 }).addTo(map);
  L.polyline(latlngs.slice(5, 7), { color: '#dc2626', weight: 10, opacity: 0.95 }).addTo(map).bindTooltip('Risk segment: Mau Summit blackout');
  points.forEach((p, n) => {
    if ([0,3,4,5,7,9].includes(n)) {
      L.circleMarker([p.lat, p.lng], { radius: 6, color: '#020617', weight: 2, fillColor: '#f8fafc', fillOpacity: 1 })
        .addTo(map)
        .bindTooltip(p.area, { permanent: n === 0 || n === 9, direction: 'top', offset: [0, -6] });
    }
  });
  marker = L.marker(latlngs[0], { icon: truckIcon(selectedPlate()), zIndexOffset: 1000 }).addTo(map);

  setTimeout(() => {
    map.invalidateSize(true);
    map.fitBounds(routeLine.getBounds(), { padding: [36, 36] });
    drawPoint(0);
  }, 250);
  setTimeout(() => {
    map.invalidateSize(true);
    map.fitBounds(routeLine.getBounds(), { padding: [36, 36] });
  }, 900);
}

document.addEventListener('DOMContentLoaded', () => {
  init();
  document.getElementById('truckSelect').addEventListener('change', () => drawPoint(index));
  document.getElementById('startBtn').addEventListener('click', () => {
    running = true;
    clearInterval(timer);
    timer = setInterval(step, 1500);
    addLog('Route simulation started. Vehicle movement is now being monitored.');
  });
  document.getElementById('pauseBtn').addEventListener('click', () => {
    running = false;
    clearInterval(timer);
    addLog('Route simulation paused.');
  });
  document.getElementById('resetBtn').addEventListener('click', () => {
    running = false;
    clearInterval(timer);
    index = 0;
    document.getElementById('eventLog').innerHTML = '<li>KDG 142A is loaded in Nairobi and assigned to the Kisumu delivery route.</li>';
    drawPoint(0);
  });

  setTimeout(() => {
    if (!running && index === 0) {
      document.getElementById('startBtn').click();
    }
  }, 1200);
});
