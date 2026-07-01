let map, marker, routeLine, timer;
let index = 0;
let points = [];
let running = false;

const truckIcon = L.divIcon({
  className: 'truck-marker',
  html: '<div class="truck-bubble">TRK</div>',
  iconSize: [42, 42],
  iconAnchor: [21, 21]
});

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

  const demoTruck = document.getElementById('demoTruck');
  const dangerZone = document.getElementById('dangerZone');
  const overlayPath = [
    {x: 12, y: 72}, {x: 22, y: 61}, {x: 35, y: 51}, {x: 46, y: 46}, {x: 56, y: 41},
    {x: 63, y: 34}, {x: 63, y: 34}, {x: 73, y: 44}, {x: 83, y: 52}, {x: 91, y: 60}
  ];
  if (demoTruck && overlayPath[index]) {
    demoTruck.style.left = overlayPath[index].x + '%';
    demoTruck.style.top = overlayPath[index].y + '%';
  }
  if (dangerZone) dangerZone.classList.toggle('active', p.signal === 'Lost' || p.stop >= 30 || p.status.includes('Alert'));

  const alertBox = document.getElementById('alertBox');
  if (p.signal === 'Lost' || p.stop >= 30 || p.status.includes('Alert')) {
    alertBox.className = 'alert-box hot';
    alertBox.innerHTML = 'Possible theft: long stop + signal loss + fuel drop detected.';
  } else if (p.stop > 0) {
    alertBox.className = 'alert-box warn';
    alertBox.innerHTML = 'Truck is stopped. Timer running.';
  } else {
    alertBox.className = 'alert-box quiet';
    alertBox.innerHTML = 'Normal movement.';
  }
}

function drawPoint(i) {
  if (!points.length) return;
  index = Math.max(0, Math.min(i, points.length - 1));
  const p = points[index];
  marker.setLatLng([p.lat, p.lng]);
  marker.bindPopup(`<strong>${document.getElementById('truckSelect').value}</strong><br>${p.area}<br>${p.status}`).openPopup();
  updatePanel(p);
  addLog(p.message);
}

function step() {
  if (!running) return;
  drawPoint(index + 1);
  if (index >= points.length - 1) {
    running = false;
    clearInterval(timer);
    addLog('Demo complete: Nairobi to Kisumu trip finished.');
  }
}

async function init() {
  const res = await fetch('/api/demo-route');
  const data = await res.json();
  points = data.points;
  setText('routeName', data.route);

  map = L.map('map').setView([-0.76, 35.77], 8);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  const latlngs = points.map(p => [p.lat, p.lng]);
  routeLine = L.polyline(latlngs, { color: '#2563eb', weight: 5, opacity: 0.85 }).addTo(map);
  L.polyline(latlngs.slice(5, 7), { color: '#ef4444', weight: 8, opacity: 0.55 }).addTo(map);
  marker = L.marker(latlngs[0], { icon: truckIcon }).addTo(map);
  setTimeout(() => {
    map.invalidateSize();
    map.setView([-0.70, 35.82], 7);
    drawPoint(0);
  }, 250);
}

document.addEventListener('DOMContentLoaded', () => {
  init();
  document.getElementById('startBtn').addEventListener('click', () => {
    running = true;
    clearInterval(timer);
    timer = setInterval(step, 1700);
    addLog('Demo started. Watch the truck move on the route.');
  });
  document.getElementById('pauseBtn').addEventListener('click', () => {
    running = false;
    clearInterval(timer);
    addLog('Demo paused.');
  });
  document.getElementById('resetBtn').addEventListener('click', () => {
    running = false;
    clearInterval(timer);
    index = 0;
    document.getElementById('eventLog').innerHTML = '<li>Truck is loaded in Nairobi and begins the Kisumu delivery route.</li>';
    drawPoint(0);
  });
});
