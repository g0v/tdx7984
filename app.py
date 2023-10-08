# apt install python3-flask python3-flask-cors python3-apscheduler
import tdx, time, atexit, os, sqlite3, argparse, csv, re, operator, math, json
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

@app.route('/bus')
@app.route('/bus/')
def bus_index():
    return render_template('bus-index.html', city_list=tdx.city_list)

@app.route('/bus/routes/<city>')
def bus_all(city):
    sqcon = sqlite3.connect(G['args'].dbpath)
    sqcursor = sqcon.cursor()
    sqcursor.execute(
        'select cname from subroute where substr(uid,1,3)=?', (tdx.city_code(city),)
    )
    all_routes = list( [ x[0] for x in sqcursor.fetchall() ] )
    return render_template('city-routes.html', city=city, all_routes=all_routes)

@app.route('/geojson/bike/stations/<cities>')
def bike_stations(cities):
    cities = cities.split('+')
    res = []
    for ct in cities:
        res += tdx.query(f'/Bike/Station/City/{tdx.city_ename(ct)}')
    return jsonify( [tdx.geojify(b, name_path='StationName/Zh_tw', coord_path='StationPosition') for b in res] )

@app.route('/geojson/bus/stops/<city>/<rtname>')
@app.route('/geojson/bus/stops/<city>/<int:to_fro>/<rtname>')
def gj_bus_stops(city, rtname, to_fro=2):
    res = tdx.bus_stops(city, rtname, to_fro)
    return jsonify( [tdx.geojify(b, name_path='StopName/Zh_tw', coord_path='StopPosition') for b in res] )

@app.route('/geojson/bus/pos/<city>/<rtname>')
def gj_bus_pos(city, rtname):
    return jsonify( [
        tdx.geojify(b, name_path='PlateNumb', coord_path='BusPosition') for b in tdx.bus_pos(city, rtname)
    ] )

@app.route('/geojson/bus/est/<city>/<rtname>')
def gj_bus_est(city, rtname):
    return jsonify( tdx.bus_est(city, rtname) )

@app.route('/bus/rte/<city>/<rtname>')
def bus_rte(city, rtname):
    est = tdx.bus_est(city, rtname)
    empty = { 'StopSequence': '', 'est': '', 'EstimateTime': '', '': 'PlateNumb' }
    for s in est:
        if 'dir0' in s:
            if 'EstimateTime' in s['dir0']:
                s['dir0']['est_min'] = int(s['dir0']['EstimateTime']/60) if s['dir0']['EstimateTime'] >= 0 else 9999
            else:
                s['dir0']['est_min'] = '-'
#            if not 'PlateNumb' in s['dir0']: s['dir0']['PlateNumb'] = ''
        else:
            s['dir0'] = empty
        if 'dir1' in s:
            if 'EstimateTime' in s['dir1']:
                s['dir1']['est_min'] = int(s['dir1']['EstimateTime']/60) if s['dir1']['EstimateTime'] >= 0 else 9999
            else:
                s['dir1']['est_min'] = '-'
#            if not 'PlateNumb' in s['dir1']: s['dir1']['PlateNumb'] = ''
        else:
            s['dir1'] = empty
    return render_template('route-est.html', city=city, rtname=rtname, est=est)

def position_diff(tail, head):
    # 從兩點的經緯度計算 x 座標差與 y 座標差 (單位： 公尺)
    head = head['StopPosition']
    tail = tail['StopPosition']
    dy = (tail['PositionLat'] - head['PositionLat']) * 4e7 / 360
    dx = (tail['PositionLon'] - head['PositionLon']) * 4.0075e7 / 360
    dx *= math.cos( (tail['PositionLat']+head['PositionLat'])/2/180*math.pi )
    return (dx, dy)

def find_stop_fill_next(stopname, dir, rt_est):
    # 在 rt_est 某路線預估清單裡面找到站名為 stopname、
    # 方向為 dir 的那一筆， 並且幫它建立 'nextstop' 欄位，
    # 填入下一站的名稱。 方法是把同方向的站牌順過一次，
    # 找到等待同一部公車的任意相鄰兩站， 如果兩者的預估時間不同，
    # 就可以確定哪個方向才是下一站。

    # 注意： 台北市的 EstimatedTimeOfArrival 沒有 StopSequence，
    # 但此處假設他處已幫忙填好
    samedir = [ est for est in rt_est if est['Direction']==dir ]
    samedir = sorted(samedir, key=operator.itemgetter('StopSequence'))
    i = 0
    for i in range(len(samedir)):
        if samedir[i]['StopName']['Zh_tw'] == stopname: break
    if i >= len(samedir): return None
    focus = i
    city_code = samedir[focus]['RouteUID'][:3]
    samedir[focus]['rte_city'] = tdx.city_list['by_code'][city_code]['ename']
    if not 'PlateNumb' in samedir[0]:
        # 台北市的 EstimatedTimeOfArrival 沒有 PlateNumb
        samedir[focus]['nextstop'] = samedir[focus+1 if focus+1<len(samedir) else focus]
        return samedir[focus]
    for i in range(len(samedir)-1):
        if samedir[i]['PlateNumb'] == samedir[i+1]['PlateNumb'] and samedir[i]['est_min'] != samedir[i+1]['est_min']:
            if samedir[i]['est_min'] < samedir[i+1]['est_min']:
                samedir[focus]['nextstop'] = samedir[focus+1 if focus+1 < len(samedir) else focus]
            else:
                samedir[focus]['nextstop'] = samedir[focus-1 if focus>0 else 0]
            break
    if not 'nextstop' in samedir[focus]: return None
    samedir[focus]['next_vector'] = position_diff(samedir[focus]['nextstop'], samedir[focus])
    samedir[focus]['nextstop'] = samedir[focus]['nextstop']['StopName']['Zh_tw']
    return samedir[focus]

@app.route('/bus/stop/<city>/<stopname>')
def bus_stop(city, stopname):
    global G
    city_ename = tdx.city_ename(city)
    sqcon = sqlite3.connect(G['args'].dbpath)
    sqcursor = sqcon.cursor()
    # 先不篩選縣市。 一個站牌 - 例如 「重慶南路一段」 -
    # 可能會有來自不同縣市的路線經過。
    # 例如在 243 線上本站稱為 NWT34514，
    # 但在 670 線上本站稱為 TPE38456 =>
    # 藍28 TPE196974 =>
    # 第一輪篩選站牌中文名稱， 第二輪篩選 station_id。
    sqcursor.execute(
        'select uid, station_id from stop where cname=?', (stopname,)
    )
    stations = {}
    for st_of_srt in sqcursor.fetchall():
        (stop_uid, station_id) = st_of_srt
        city_code = stop_uid[:3]
        if tdx.city_list['by_code'][city_code]['ename'] == city_ename:
            stations[station_id] = True
    stations = list(stations.keys())
    sqcursor.execute(
        'select stop.uid, stop.cname, stop.srt_uid, subroute.cname, stop.dir, stop.station_id from stop join subroute on stop.srt_uid=subroute.uid where stop.cname=? and stop.station_id in ('+','.join(['?']*len(stations))+')', [stopname]+stations
    )
    stops = [
        dict(zip(['stop_uid', 'cname', 'srt_uid', 'srt_cname', 'dir', 'stn_id'], st)) for st in sqcursor.fetchall()
    ]
    sqcon.close()
    stations = {}
    visited = {}
    all_est = []
    # 一開始先按照 srt_name 把每一對 (此路線的去回雙向) 估計資訊存入 all_est
    for st in stops:
        srt_name = st['srt_cname']
        this_srt_city_code = st['srt_uid'][:3]
        this_srt_city_ename = tdx.city_list['by_code'][this_srt_city_code]['ename']
        print(srt_name, end=', ', flush=True)
        # 每一個站牌名稱可能有兩個 (方向的) 估計到站時刻
        if srt_name in visited: continue
        visited[srt_name] = True
        raw_est = list( tdx.query(f'Bus/EstimatedTimeOfArrival/City/{this_srt_city_ename}/{srt_name}') )
        if len(raw_est) < 1: continue
        # 新北 243寵物公車
        # 台北的估計到站時刻資訊不含 StopSequence
        # 台中的不含 StationID， 都需要讀取靜態資訊來補充
        stop_info_by_uid = dict(
            (s['StopUID'], s) for s in tdx.bus_stops(this_srt_city_ename, srt_name, to_fro=2)
        )
        # 台中跟台北的 StopSequence (方向) 定義不同。
        # 保留同一路線上其他站的預估到站資訊， 才好找 「下一站」。
        rt_est = []     # 一條路線的 (最多) 兩筆預估記錄
        for est in raw_est:
            # 台北市沒有 SubRouteName
            if 'SubRouteName' in est:
                if est['SubRouteName']['Zh_tw'] != srt_name: continue
            else:
                if est['RouteName']['Zh_tw'] != srt_name: continue
                est['SubRouteName'] = est['RouteName']
            est['est_min'] = est['EstimateTime']/60 if 'EstimateTime' in est else 9999
            if not 'StopSequence' in est:
                est['StopSequence'] = tdx.lookup_by_stopuid(est['StopUID'], stop_info_by_uid, 'StopSequence', default=999, rtname=srt_name)
            if not 'StationID' in est:
                est['StationID'] = tdx.lookup_by_stopuid(est['StopUID'], stop_info_by_uid, 'StationID')
            if est['StopUID'] in stop_info_by_uid:
                est['StopPosition'] = stop_info_by_uid[est['StopUID']]['StopPosition']
            rt_est.append(est)
        est = find_stop_fill_next(stopname, 0, rt_est)
        if est is not None: all_est.append(est)
        est = find_stop_fill_next(stopname, 1, rt_est)
        if est is not None: all_est.append(est)
    print('')
    all_est = sorted(all_est, key=operator.itemgetter('nextstop','est_min'))
    return render_template('stop-est.html', city=city, stopname=stopname, est=all_est)

@app.route('/bus/sched/<city>/<rtname>')
def bus_sched(city, rtname):
    dtt_all = tdx.query(f'Bus/DailyTimeTable/City/{tdx.city_ename(city)}/{rtname}')
    return render_template('time-table.html', city=city, rtname=rtname, dtt_all=dtt_all)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='重新包裝少數幾個交通部的 tdx API， 以 geojson 或 html 網頁呈現',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-d', '--dbpath', type=str,
        default='',
        help='全國所有縣市公車路線與站牌資料庫檔案')
    G['args'] = parser.parse_args()
    m = re.search(r'(.*)/', __file__)
    my_dir = m.group(1)
    if G['args'].dbpath == '':
        G['args'].dbpath = f'{my_dir}/routes_stops.sqlite3'

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=tdx.load_credential, trigger='interval', seconds=7200)
    atexit.register(lambda: scheduler.shutdown())
    scheduler.start()

    # openssl req -x509 -newkey rsa:4096 -nodes -out flask-cert.pem -keyout flask-key.pem -days 36500
    # https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https
    app.run(host='0.0.0.0', port=7984, ssl_context=(os.environ['HOME']+'/secret/flask-cert.pem', os.environ['HOME']+'/secret/flask-key.pem'))
