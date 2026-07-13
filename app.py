from flask import Flask, render_template, g, redirect, url_for, Response, send_file, request, session, flash, jsonify
from functools import wraps
import sqlite3, os, csv, io
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'fleet.db')
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'demo-secret-key')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'FuelGuard@2026')
GAP_THRESHOLD_MINUTES = 10
FUEL_DROP_THRESHOLD_LITRES = 15


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user'):
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['user'] = username
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop('db', None)
    if conn:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY, plate TEXT UNIQUE, driver TEXT, tracker_model TEXT, fuel_sensor TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS telemetry(id INTEGER PRIMARY KEY, vehicle_id INTEGER, timestamp TEXT, fuel_level REAL, signal_strength INTEGER, gps_lat REAL, gps_lng REAL);
    CREATE TABLE IF NOT EXISTS incidents(id INTEGER PRIMARY KEY, vehicle_id INTEGER, gap_start TEXT, gap_end TEXT, minutes_offline INTEGER, fuel_before REAL, fuel_after REAL, fuel_drop REAL, severity TEXT, status TEXT, created_at TEXT);
    ''')
    conn.commit()
    if cur.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0] == 0:
        seed(conn)
    else:
        normalize_demo_data(conn)
    conn.close()


def normalize_demo_data(conn):
    cur = conn.cursor()
    cur.execute("UPDATE vehicles SET status='online' WHERE status='alert'")
    cur.execute("UPDATE vehicles SET tracker_model='Teltonika FMB920' WHERE tracker_model IN ('Teltonika FMx920','Phone GPS Demo','')")
    cur.execute("UPDATE vehicles SET fuel_sensor='Ultrasonic fuel sensor' WHERE fuel_sensor IN ('TA34 Ultrasonic','Demo fuel sensor','')")
    cur.execute("INSERT OR IGNORE INTO vehicles(plate,driver,tracker_model,fuel_sensor,status) VALUES (?,?,?,?,?)", ('KDJ 904T', 'Amina Wanjiru', 'Teltonika FMC130', 'Digital fuel probe via RS485', 'active'))
    conn.commit()


def seed(conn):
    cur = conn.cursor()
    vehicles = [
        ('KDG 142A', 'Peter Mwangi', 'Teltonika FMB920', 'Ultrasonic fuel sensor', 'online'),
        ('KDE 811K', 'Samuel Otieno', 'Teltonika FMC130', 'Capacitive fuel sensor', 'online'),
        ('KDB 502M', 'Brian Karanja', 'Teltonika FMB125', 'Digital fuel probe via RS485', 'online'),
        ('KDF 771R', 'Joseph Njoroge', 'Teltonika FMC650', 'Ultrasonic fuel sensor', 'offline'),
        ('KDC 330P', 'David Wekesa', 'Teltonika FMB920', 'Capacitive fuel sensor', 'online'),
        ('KDJ 904T', 'Amina Wanjiru', 'Teltonika FMC130', 'Digital fuel probe via RS485', 'active'),
    ]
    cur.executemany('INSERT INTO vehicles(plate,driver,tracker_model,fuel_sensor,status) VALUES (?,?,?,?,?)', vehicles)
    base = datetime(2026, 7, 1, 8, 0, 0)
    for vid in range(1, 6):
        fuel = 230 - vid * 7
        for i in range(12):
            ts = base + timedelta(minutes=i * 5)
            cur.execute('INSERT INTO telemetry(vehicle_id,timestamp,fuel_level,signal_strength,gps_lat,gps_lng) VALUES (?,?,?,?,?,?)', (vid, ts.isoformat(), fuel - i * 0.7, 80, -1.152 + vid/1000, 36.956 + i/10000))
        if vid in (3, 4):
            before = base + timedelta(minutes=55)
            after = base + timedelta(minutes=90)
            cur.execute('INSERT INTO telemetry(vehicle_id,timestamp,fuel_level,signal_strength,gps_lat,gps_lng) VALUES (?,?,?,?,?,?)', (vid, before.isoformat(), fuel - 7, 78, -1.15, 36.96))
            cur.execute('INSERT INTO telemetry(vehicle_id,timestamp,fuel_level,signal_strength,gps_lat,gps_lng) VALUES (?,?,?,?,?,?)', (vid, after.isoformat(), fuel - 38, 76, -1.15, 36.96))
    conn.commit()
    detect_incidents(conn)


def detect_incidents(conn=None):
    own = conn is None
    conn = conn or sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('DELETE FROM incidents')
    for vehicle in cur.execute('SELECT id FROM vehicles').fetchall():
        rows = cur.execute('SELECT * FROM telemetry WHERE vehicle_id=? ORDER BY timestamp', (vehicle['id'],)).fetchall()
        for prev, nxt in zip(rows, rows[1:]):
            t1 = datetime.fromisoformat(prev['timestamp'])
            t2 = datetime.fromisoformat(nxt['timestamp'])
            gap = int((t2 - t1).total_seconds() // 60)
            drop = round(prev['fuel_level'] - nxt['fuel_level'], 2)
            if gap >= GAP_THRESHOLD_MINUTES and drop >= FUEL_DROP_THRESHOLD_LITRES:
                severity = 'critical' if drop >= 30 else 'high'
                cur.execute('INSERT INTO incidents(vehicle_id,gap_start,gap_end,minutes_offline,fuel_before,fuel_after,fuel_drop,severity,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)', (vehicle['id'], prev['timestamp'], nxt['timestamp'], gap, prev['fuel_level'], nxt['fuel_level'], drop, severity, 'open', datetime.utcnow().isoformat()))
    conn.commit()
    if own:
        conn.close()


@app.route('/')
@login_required
def dashboard():
    conn = get_db()
    stats = {
        'vehicles': conn.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0],
        'online': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status='online'").fetchone()[0],
        'alerts': conn.execute("SELECT COUNT(*) FROM incidents WHERE status='open'").fetchone()[0],
        'fuel_loss': conn.execute("SELECT COALESCE(SUM(fuel_drop),0) FROM incidents WHERE status='open'").fetchone()[0],
        'active': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status IN ('active','online')").fetchone()[0],
        'offline': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status='offline'").fetchone()[0],
    }
    vehicles = conn.execute('SELECT * FROM vehicles ORDER BY plate').fetchall()
    incidents = conn.execute('SELECT incidents.*, vehicles.plate, vehicles.driver FROM incidents JOIN vehicles ON vehicles.id=incidents.vehicle_id ORDER BY incidents.id DESC LIMIT 5').fetchall()
    return render_template('dashboard.html', stats=stats, vehicles=vehicles, incidents=incidents)


@app.route('/vehicles', methods=['GET', 'POST'])
@login_required
def vehicles():
    conn = get_db()
    if request.method == 'POST':
        plate = request.form.get('plate', '').strip().upper()
        driver = request.form.get('driver', '').strip()
        tracker_model = request.form.get('tracker_model', '').strip()
        fuel_sensor = request.form.get('fuel_sensor', '').strip()
        status = request.form.get('status', 'active').strip().lower()
        if plate and driver:
            conn.execute('INSERT OR IGNORE INTO vehicles(plate,driver,tracker_model,fuel_sensor,status) VALUES (?,?,?,?,?)', (plate, driver, tracker_model, fuel_sensor, status))
            conn.commit()
        return redirect(url_for('vehicles'))
    return render_template('vehicles.html', vehicles=conn.execute('SELECT * FROM vehicles ORDER BY plate').fetchall())


@app.route('/vehicles/<int:vehicle_id>/remove', methods=['POST'])
@login_required
def remove_vehicle(vehicle_id):
    conn = get_db()
    row = conn.execute('SELECT plate, driver FROM vehicles WHERE id=?', (vehicle_id,)).fetchone()
    if not row:
        flash('Truck not found.')
        return redirect(url_for('vehicles'))
    conn.execute('DELETE FROM incidents WHERE vehicle_id=?', (vehicle_id,))
    conn.execute('DELETE FROM telemetry WHERE vehicle_id=?', (vehicle_id,))
    conn.execute('DELETE FROM vehicles WHERE id=?', (vehicle_id,))
    conn.commit()
    flash(f"Removed {row['driver']} / {row['plate']} from the dashboard and registry.")
    return redirect(url_for('vehicles'))


@app.route('/incidents/<int:incident_id>/resolve', methods=['POST'])
@login_required
def resolve_incident(incident_id):
    conn = get_db()
    conn.execute("UPDATE incidents SET status='resolved' WHERE id=?", (incident_id,))
    conn.commit()
    flash('Alert resolved and removed from open dashboard count.')
    return redirect(url_for('incidents'))


@app.route('/tracking')
@login_required
def tracking():
    return render_template('tracking.html')


@app.route('/api/demo-route')
@login_required
def demo_route():
    return jsonify({
        'route': 'Nairobi to Kisumu',
        'points': [
            {'area': 'Nairobi CBD', 'lat': -1.286389, 'lng': 36.817223, 'speed': 0, 'fuel': 220, 'signal': 'Online', 'status': 'Loading', 'stop': 0, 'message': 'Truck starts in Nairobi.'},
            {'area': 'Westlands', 'lat': -1.2647, 'lng': 36.8020, 'speed': 32, 'fuel': 219, 'signal': 'Online', 'status': 'Moving', 'stop': 0, 'message': 'Truck leaves Nairobi.'},
            {'area': 'Limuru escarpment', 'lat': -1.1079, 'lng': 36.6426, 'speed': 58, 'fuel': 216, 'signal': 'Online', 'status': 'Moving', 'stop': 0, 'message': 'Normal movement toward Rift Valley.'},
            {'area': 'Naivasha stop', 'lat': -0.7167, 'lng': 36.4333, 'speed': 0, 'fuel': 214, 'signal': 'Online', 'status': 'Normal stop', 'stop': 8, 'message': 'Short legal stop. No alert.'},
            {'area': 'Nakuru', 'lat': -0.3031, 'lng': 36.0800, 'speed': 62, 'fuel': 209, 'signal': 'Online', 'status': 'Moving', 'stop': 0, 'message': 'Truck continues normally.'},
            {'area': 'Mau Summit blackout', 'lat': -0.1808, 'lng': 35.6814, 'speed': 0, 'fuel': 207, 'signal': 'Lost', 'status': 'Stopped', 'stop': 12, 'message': 'Signal disappears while truck is stopped.'},
            {'area': 'Mau Summit blackout', 'lat': -0.1808, 'lng': 35.6814, 'speed': 0, 'fuel': 178, 'signal': 'Lost', 'status': 'Suspicious stop', 'stop': 35, 'message': 'Stopped 35 minutes and fuel drops heavily.'},
            {'area': 'Kericho', 'lat': -0.3677, 'lng': 35.2831, 'speed': 55, 'fuel': 176, 'signal': 'Online', 'status': 'Alert flagged', 'stop': 0, 'message': 'Truck returns online. System flags possible fuel theft.'},
            {'area': 'Ahero', 'lat': -0.1746, 'lng': 34.9163, 'speed': 60, 'fuel': 171, 'signal': 'Online', 'status': 'Moving', 'stop': 0, 'message': 'Truck continues toward Kisumu.'},
            {'area': 'Kisumu delivery point', 'lat': -0.0917, 'lng': 34.7680, 'speed': 0, 'fuel': 168, 'signal': 'Online', 'status': 'Arrived', 'stop': 0, 'message': 'Truck arrives in Kisumu.'}
        ]
    })


@app.route('/incidents')
@login_required
def incidents():
    rows = get_db().execute('SELECT incidents.*, vehicles.plate, vehicles.driver FROM incidents JOIN vehicles ON vehicles.id=incidents.vehicle_id ORDER BY incidents.id DESC').fetchall()
    return render_template('incidents.html', incidents=rows)


@app.route('/scan')
@login_required
def scan():
    detect_incidents()
    return redirect(url_for('incidents'))


def incident_row(incident_id):
    return get_db().execute('SELECT incidents.*, vehicles.plate, vehicles.driver, vehicles.tracker_model, vehicles.fuel_sensor FROM incidents JOIN vehicles ON vehicles.id=incidents.vehicle_id WHERE incidents.id=?', (incident_id,)).fetchone()


@app.route('/reports/<int:incident_id>.csv')
@login_required
def report_csv(incident_id):
    row = incident_row(incident_id)
    if not row:
        return 'Incident not found', 404
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Incident ID','Plate','Driver','Tracker','Fuel Sensor','Gap Start','Gap End','Minutes Offline','Fuel Before','Fuel After','Fuel Drop','Severity','Status'])
    writer.writerow([row['id'], row['plate'], row['driver'], row['tracker_model'], row['fuel_sensor'], row['gap_start'], row['gap_end'], row['minutes_offline'], row['fuel_before'], row['fuel_after'], row['fuel_drop'], row['severity'], row['status']])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=forensic_incident_{incident_id}.csv'})


@app.route('/reports/<int:incident_id>.pdf')
@login_required
def report_pdf(incident_id):
    row = incident_row(incident_id)
    if not row:
        return 'Incident not found', 404
    path = os.path.join(BASE_DIR, f'forensic_incident_{incident_id}.pdf')
    c = canvas.Canvas(path, pagesize=A4)
    y = 27 * cm
    c.setFont('Helvetica-Bold', 16)
    c.drawString(2 * cm, y, 'Forensic Fuel Theft / GSM Jamming Report')
    y -= 1.2 * cm
    fields = [('Incident ID', row['id']), ('Vehicle Plate', row['plate']), ('Driver', row['driver']), ('Tracker Model', row['tracker_model']), ('Fuel Sensor', row['fuel_sensor']), ('Signal Gap Start', row['gap_start']), ('Signal Gap End', row['gap_end']), ('Minutes Offline', row['minutes_offline']), ('Fuel Before Gap', f"{row['fuel_before']} L"), ('Fuel After Gap', f"{row['fuel_after']} L"), ('Detected Fuel Drop', f"{row['fuel_drop']} L"), ('Severity', row['severity'].upper()), ('Case Status', row['status'])]
    for label, value in fields:
        c.setFont('Helvetica-Bold', 10); c.drawString(2 * cm, y, f'{label}:')
        c.setFont('Helvetica', 10); c.drawString(6 * cm, y, str(value)); y -= 0.65 * cm
    y -= 0.4 * cm
    c.setFont('Helvetica-Bold', 11); c.drawString(2 * cm, y, 'System Finding:'); y -= 0.7 * cm
    c.setFont('Helvetica', 10)
    text = 'The system detected a communication blackout above the configured threshold and a major fuel-level drop immediately after signal restoration. This pattern is consistent with possible GSM jamming used to conceal fuel siphoning.'
    for line in [text[i:i+95] for i in range(0, len(text), 95)]:
        c.drawString(2 * cm, y, line); y -= 0.55 * cm
    c.showPage(); c.save()
    return send_file(path, as_attachment=True, download_name=f'forensic_incident_{incident_id}.pdf')


# Ensure the SQLite demo database exists when imported by Gunicorn/Render.
init_db()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
