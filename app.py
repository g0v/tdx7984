# apt install python3-flask python3-flask-cors python3-apscheduler
import tdx, time, atexit, os, sqlite3, argparse, csv, re, operator
from flask import Flask, jsonify, render_template
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS

G = {
}

app = Flask(__name__)
CORS(app)

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

def find_stop_fill_next(stopname, dir, rt_est):
    # 在 rt_est 某路線預估清單裡面找到站名為 stopname、
    # 方向為 dir 的那一筆， 並且幫它建立 'nextstop' 欄位，
    # 填入下一站的名稱。 方法是把同方向的站牌順過一次，
    # 找到等待同一部公車的任意相鄰兩站， 如果兩者的預估時間不同，
    # 就可以確定哪個方向才是下一站。
    samedir = sorted([ est for est in rt_est if est['Direction']==dir ], key='StopSequence')
    for i in range(len(samedir)):
        if samedir[i]['StopName']['Zh_tw'] == stopname: break
    print(stopname, dir, i)
    if i >= len(samedir): return None
    focus = i
    for i in range(len(samedir))-1:
        if samedir[i]['PlateNumb'] == samedir[i+1]['PlateNumb'] and samedir[i]['EstimateTime'] != samedir[i+1]['EstimateTime']:
            if samedir[i]['EstimateTime'] < samedir[i+1]['EstimateTime']:
                samedir[focus]['nextstop'] = samedir[focus+1]['StopName']['Zh_tw'] if focus+1 < len(samedir) else ''
            else:
                samedir[focus]['nextstop'] = samedir[focus-1]['StopName']['Zh_tw'] if focus > 0 else ''
            break
    return samedir[focus]

@app.route('/bus/stop/<city>/<stopname>.html')
def bus_stop(city, stopname):
    global G
    city_ename = tdx.city_ename(city)
    sqcon = sqlite3.connect(G['args'].rsdb)
    sqcursor = sqcon.cursor()
    sqcursor.execute(
        'select stop.uid, stop.cname, stop.srt_uid, subroute.cname, stop.dir from stop join subroute on stop.srt_uid=subroute.uid where stop.cname=?', (stopname,)
    )
    stops = []
    for st_of_srt in sqcursor.fetchall():
        st_of_srt = dict(zip(['stop_uid', 'cname', 'srt_uid', 'srt_cname', 'dir'], st_of_srt))
        city_code = st_of_srt['stop_uid'][:3]
        if not G['city'][city_code]['ename'] == city_ename: continue
    sqcon.close()
    visited = {}
    all_est = []
    # 一開始先按照 rtname 把每一對 (此路線的去回雙向) 估計資訊存入 all_est
    for st in stops:
        rtname = st['srt_cname']
        # 每一個站牌名稱可能有兩個 (方向的) 估計到站時刻
        if rtname in visited: continue
        visited[rtname] = True
        # 台中跟台北的 StopSequence 定義不同，
        # 所以必須保留其他站的預估到站資訊， 才好找 「下一站」。
        rt_est = [ est for est in tdx.query(f'Bus/EstimatedTimeOfArrival/City/{city_ename}/{rtname}') if est['SubRouteName']['Zh_tw'] == rtname ]
        est = find_stop_fill_next(stopname, 0, rt_est)
        if est is not None: all_est.append(est)
        est = find_stop_fill_next(stopname, 1, rt_est)
        if est is not None: all_est.append(est)
    all_est = sorted( all_est, key = operator.itemgetter('nextstop', 'EstimateTime') )
    return render_template('stop-est.html', city=city, stopname=stopname, est=all_est)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='重新包裝少數幾個交通部的 tdx API， 以 geojson 或 html 網頁呈現',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--rsdb', type=str,
        default='',
        help='全國所有縣市公車路線與站牌資料庫檔案')
    G['args'] = parser.parse_args()
    m = re.search(r'(.*)/', __file__)
    my_dir = m.group(1)
    if G['args'].rsdb == '':
        G['args'].rsdb = f'{my_dir}/routes_stops.sqlite3'

    tdx.load_credential()

    G['city'] = {}
    with open(f'{my_dir}/cities.csv') as F:
        for row in csv.DictReader(F):
            G['city'][row['code']] = {
                'cname': row['cname'],
                'ename': row['ename']
            }
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=tdx.load_credential, trigger='interval', seconds=7200)
    atexit.register(lambda: scheduler.shutdown())
    scheduler.start()

    # openssl req -x509 -newkey rsa:4096 -nodes -out flask-cert.pem -keyout flask-key.pem -days 36500
    # https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https
    app.run(host='0.0.0.0', port=7984, ssl_context=(os.environ['HOME']+'/secret/flask-cert.pem', os.environ['HOME']+'/secret/flask-key.pem'))
