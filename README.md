# GSM Jamming + Fuel Theft Detection Prototype

Working Flask prototype for Kelvin Nyaga's project. It detects GSM signal gaps/jamming, compares fuel before/after the gap, flags suspected fuel theft, and exports forensic reports.

## Run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Pages
- `/` dashboard
- `/vehicles` vehicle/driver management
- `/incidents` flagged incidents
- `/reports/<incident_id>.csv` CSV forensic report
- `/reports/<incident_id>.pdf` PDF forensic report
