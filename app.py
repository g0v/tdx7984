# apt install python3-flask python3-flask-cors python3-apscheduler
import tdx, time, atexit, os
from flask import Flask, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

tdx.load_credential()
scheduler = BackgroundScheduler()
scheduler.add_job(func=tdx.load_credential, trigger='interval', seconds=7200)
atexit.register(lambda: scheduler.shutdown())
scheduler.start()

@app.route('/')
def hello():
    return 'This is a flask web server'

@app.route('/geojson/bike/stations/<cities>')
def bike_stations(cities):
    cities = cities.split('+')
    res = []
    for ct in cities:
        res += tdx.bike_stations(ct) 
    return jsonify( res )

@app.route('/geojson/bus/stops/<city>/<rtname>')
@app.route('/geojson/bus/stops/<city>/<int:to_fro>/<rtname>')
def gj_bus_stops(city, rtname, to_fro=2):
    return jsonify( tdx.bus_stops(city, rtname, to_fro) )

@app.route('/geojson/bus/pos/<city>/<rtname>')
def gj_bus_pos(city, rtname):
    return jsonify( tdx.bus_pos(city, rtname) )

@app.route('/geojson/bus/est/<city>/<rtname>')
def gj_bus_est(city, rtname):
    return jsonify( tdx.bus_est(city, rtname) )

@app.route('/bus/rte/<city>/<rtname>.html')
def bus_rte(city, rtname):
    est = tdx.bus_est(city, rtname)
    empty = { 'StopSequence': '', 'est': '', 'EstimateTime': '', '': 'PlateNumb' }
    for s in est:
        if 'dir0' in s:
            if 'EstimateTime' in s['dir0']:
                s['dir0']['est'] = int(s['dir0']['EstimateTime']/60) if s['dir0']['EstimateTime'] >= 0 else 9999
            else:
                s['dir0']['est'] = '-'
#            if not 'PlateNumb' in s['dir0']: s['dir0']['PlateNumb'] = ''
        else:
            s['dir0'] = empty
        if 'dir1' in s:
            if 'EstimateTime' in s['dir1']:
                s['dir1']['est'] = int(s['dir1']['EstimateTime']/60) if s['dir1']['EstimateTime'] >= 0 else 9999
            else:
                s['dir1']['est'] = '-'
#            if not 'PlateNumb' in s['dir1']: s['dir1']['PlateNumb'] = ''
        else:
            s['dir1'] = empty
    return render_template('route-est.html', city=city, rtname=rtname, est=est)

if __name__ == '__main__':
    # openssl req -x509 -newkey rsa:4096 -nodes -out flask-cert.pem -keyout flask-key.pem -days 36500
    # https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https
    app.run(host='0.0.0.0', port=7984, ssl_context=(os.environ['HOME']+'/secret/flask-cert.pem', os.environ['HOME']+'/secret/flask-key.pem'))
