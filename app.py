#!/usr/bin/env python3

# apt install python3-flask python3-flask-cors python3-apscheduler
import logging, tdx, time, atexit, os, sqlite3, argparse, csv, re, operator, math, json
from datetime import datetime
from flask import Flask, jsonify, render_template, send_from_directory, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
from flask_cors import CORS
from werkzeug.serving import WSGIRequestHandler, _log
from logging.config import dictConfig

G = {
    'date_format': '%m/%d %H:%M:%S',
}

# https://stackoverflow.com/questions/36299494/how-to-remove-the-from-flasks-logging
class MyRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        _log(type, '%s %s\n' % (
            self.address_string(),
            message % args)
        )

# https://betterstack.com/community/guides/logging/how-to-start-logging-with-flask/
dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(filename)s %(lineno)d | %(message)s",
                "datefmt": G['date_format'],
            },
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": "/var/log/tdx7984/query.log",
                "formatter": "default",
            },

        },
        "root": {"level": "DEBUG", "handlers": ["file"]},
    }
)

app = Flask(__name__, static_folder='static')
CORS(app)

# https://stackoverflow.com/a/14625619
@app.route('/robots.txt')
# @app.route('/sitemap.xml')
def static_from_root():
    return send_from_directory(app.static_folder, request.path[1:])

# https://stackoverflow.com/questions/74155189/how-to-log-uncaught-exceptions-in-flask-routes-with-logging
@app.errorhandler(Exception)
def handle_exception(e):
    # log the exception
    logging.exception(f'{request.remote_addr} "{request.method} {request.full_path}" 500 -')
    # return a custom error page or message
    return render_template('error.html'), 500

# https://ithelp.ithome.com.tw/articles/10266705?sc=iThelpR
@app.errorhandler(404)
def page_not_found(e=None):
    # https://stackoverflow.com/questions/50346512/flask-404-catch-requested-url
    logging.warning('page not found (404) ' + request.path)
    return render_template('404.html'), 404

def now_string():
    global G
    return datetime.now().strftime(G['date_format'])

@app.route('/')
def doc_root():
    return redirect("/bus/", code=302)

@app.route('/bus')
@app.route('/bus/')
def bus_index():
    return render_template('bus-index.html', city_list=tdx.city_list, now=now_string())

@app.route('/bus/routes/<city>')
def bus_all(city):
    dbcursor = tdx.G['dbcon'].cursor()
    dbcursor.execute(
        'select cname from subroute where substr(uid,1,3)=?', (tdx.city_code(city),)
    )
    all_routes = list( [ x[0] for x in dbcursor.fetchall() ] )
    return render_template('city-routes.html', city=city, all_routes=all_routes, now=now_string())

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
    return jsonify( tdx.fill_stops_info_along_srt(tdx.bus_est(city, rtname)) )

@app.route('/bus/rte/<city>/<rtname>')
def bus_rte(city, rtname):
    est = tdx.fill_stops_info_along_srt(tdx.bus_est(city, rtname))
    missing_seq = [s for s in est if not 'StopSequence' in s]
    if float(len(missing_seq)) / len(est) < 0.1:
        # 台北 208 只有 「捷運公館站」 欠缺 StopSequence、
        # 台北 235 只有 「仁愛安和路口」 欠缺 StopSequence
        # 還是盡力試著合併去回程站牌吧..
        for s in missing_seq:
            s['StopSequence'] = 999 if s['Direction']==0 else -1
    else:
        est_pair = [[], []]
        for s in est:
            s['est_min'] = int(s['EstimateTime']/60) if 'EstimateTime' in s and s['EstimateTime'] >= 0 else 9999
            est_pair[s['Direction']].append(s)
        # logging.info('est_pair: {} + {}'.format(len(est_pair[0]), len(est_pair[1])))
        return render_template('route-est-seq-missing.html', city=city, rtname=rtname, est_pair=est_pair, now=now_string())
    est = tdx.merged_bus_est(est)
    if len(est) < 1:
        return page_not_found()
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
    return render_template('route-est.html', city=city, rtname=rtname, est=est, now=now_string())

def position_diff(tail, head):
    # 從兩點的經緯度計算 x 座標差與 y 座標差 (單位： 公尺)
    if 'StopPosition' in head and 'StopPosition' in tail:
        head = head['StopPosition']
        tail = tail['StopPosition']
        dy = (tail['PositionLat'] - head['PositionLat']) * 4e7 / 360
        dx = (tail['PositionLon'] - head['PositionLon']) * 4.0075e7 / 360
        dx *= math.cos( (tail['PositionLat']+head['PositionLat'])/2/180*math.pi )
        return (dx, dy)
    else:
        # 曾經在 台中 青年高中 出現 KeyError: 'StopPosition'
        return (0, 0)

def find_stop_fill_next(stopname, dir, rt_est):
    # 在 rt_est 某路線預估清單裡面找到站名為 stopname、
    # 方向為 dir 的那一筆， 並且幫它建立 'next_stop' 欄位，
    # 填入下一站的名稱。 方法是把同方向的站牌順過一次，
    # 找到等待同一部公車的任意相鄰兩站， 如果兩者的預估時間不同，
    # 就可以確定哪個方向才是下一站。

    # 注意： 台北市的 EstimatedTimeOfArrival 沒有 StopSequence，
    # 但此處假設他處已幫忙填好
    samedir = [ est for est in rt_est if est['Direction']==dir ]
    if all('StopSequence' in est for est in rt_est):
        samedir = sorted(samedir, key=operator.itemgetter('StopSequence'))
    else:
        # 新北 936
        pass
    i = 0
    for i in range(len(samedir)):
        if samedir[i]['StopName']['Zh_tw'] == stopname: break
    if i >= len(samedir): return None
    focus = i
    city_code = samedir[focus]['SubRouteUID'][:3]
    samedir[focus]['rte_city'] = tdx.city_list['by_code'][city_code]['ename']
    if 'PlateNumb' in samedir[0]:
        for i in range(len(samedir)-1):
            if samedir[i]['PlateNumb'] == samedir[i+1]['PlateNumb'] and samedir[i]['est_min'] != samedir[i+1]['est_min']:
                if samedir[i]['est_min'] < samedir[i+1]['est_min']:
                    samedir[focus]['next_stop'] = samedir[focus+1 if focus+1 < len(samedir) else focus]
                else:
                    samedir[focus]['next_stop'] = samedir[focus-1 if focus>0 else 0]
                break
        if not 'next_stop' in samedir[focus]: return None
    else:
        # 台北市的 EstimatedTimeOfArrival 沒有 PlateNumb
        samedir[focus]['next_stop'] = samedir[focus+1 if focus+1<len(samedir) else focus]
    samedir[focus]['next_vector'] = position_diff(samedir[focus]['next_stop'], samedir[focus])
    samedir[focus]['next_stop'] = samedir[focus]['next_stop']['StopName']['Zh_tw']
    if not 'StopSequence' in samedir[focus]:
        samedir[focus]['next_stop'] = '？'
        # 例如新北 溫哥華社區 站牌的 936、 F250 等等路線，
        # 欠 Sequence 資訊， 「下一站」 資料不可信
    return samedir[focus]

@app.route('/bus/stop/<city>/<stopname>')
def bus_stop(city, stopname):
    global G
    city_ename = tdx.city_ename(city)
    dbcursor = tdx.G['dbcon'].cursor()
    # 先不篩選縣市。 一個站牌 - 例如 「重慶南路一段」 -
    # 可能會有來自不同縣市的路線經過。
    # 例如在 243 線上本站稱為 NWT34514，
    # 但在 670 線上本站稱為 TPE38456、
    # 藍28 TPE196974 =>
    # 第一輪篩選站牌中文名稱， 第二輪篩選 station_id。
    dbcursor.execute(
        'select uid, station_id from stop where cname=?', (stopname,)
    )
    stations = {}
    for st_of_srt in dbcursor.fetchall():
        (stop_uid, station_id) = st_of_srt
        city_code = stop_uid[:3]
        if tdx.city_list['by_code'][city_code]['ename'] == city_ename:
            stations[station_id] = True
    stations = list(stations.keys())
    dbcursor.execute(
        'select stop.uid, stop.cname, stop.srt_uid, subroute.cname, stop.dir, stop.station_id from stop join subroute on stop.srt_uid=subroute.uid where stop.cname=? and stop.station_id in ('+','.join(['?']*len(stations))+')', [stopname]+stations
    )
    stops = [
        dict(zip(['stop_uid', 'cname', 'srt_uid', 'srt_cname', 'dir', 'stn_id'], st)) for st in dbcursor.fetchall()
    ]
    # 隸屬於不同路線與方向的所有 stops
    stations = {}
    visited = {}
    all_est = []
    # 一開始先按照 srt_name 把每一對 (此路線的去回雙向) 估計資訊存入 all_est
    query_log = f'[{stopname}] '
    for st in stops:
        # 隸屬於某條路線的某個方向的一個 stop
        srt_name = st['srt_cname']
        this_srt_city_code = st['srt_uid'][:3]
        this_srt_city_ename = tdx.city_list['by_code'][this_srt_city_code]['ename']
        # 每一個站牌名稱可能有兩個 (方向的) 估計到站時刻
        if srt_name in visited: continue
        query_log += srt_name + ', '
        visited[srt_name] = True
        raw_est = tdx.fill_stops_info_along_srt(tdx.bus_est(this_srt_city_ename, srt_name))
        if len(raw_est) < 1: continue
        # 新北 243寵物公車
        # 台北的估計到站時刻資訊不含 StopSequence
        # 台中的不含 StationID， 都需要讀取靜態資訊來補充
        # 台中跟台北的 StopSequence (方向) 定義不同。
        # 保留同一路線上其他站的預估到站資訊， 才好找 「下一站」。
        rt_est = []     # 一條路線的 (最多) 兩筆預估記錄
        for est in raw_est:
            # 本路線上所有站牌的到站時刻估計
            if est['SubRouteName']['Zh_tw'] != srt_name: continue
            # logging.error(f'est 內找不到 SubRouteName: {stopname}/{srt_name} ## ' + str(est))
            est['est_min'] = est['EstimateTime']/60 if 'EstimateTime' in est else 9999
            rt_est.append(est)
        est = find_stop_fill_next(stopname, 0, rt_est)
        if est is not None: all_est.append(est)
        est = find_stop_fill_next(stopname, 1, rt_est)
        if est is not None: all_est.append(est)
    logging.info(query_log)
    all_est = sorted(all_est, key=operator.itemgetter('next_stop','est_min'))
    return render_template('stop-est.html', city=city, stopname=stopname, est=all_est, now=now_string())

@app.route('/bus/sched/<city>/<rtname>')
def bus_sched(city, rtname):
    global G
    dtt_all = tdx.query(f'Bus/DailyTimeTable/City/{tdx.city_ename(city)}/{rtname}')
    for srt in dtt_all:
        srt['Timetables'] = sorted(srt['Timetables'], key=lambda rte: rte['StopTimes'][0]['DepartureTime'])
    return render_template('time-table.html', city=city, rtname=rtname, dtt_all=dtt_all, now=now_string())

if __name__ == '__main__':
    m = re.search(r'(.*)/', __file__)
    my_dir = m.group(1)
    parser = argparse.ArgumentParser(
        description='重新包裝少數幾個交通部的 tdx API， 以 geojson 或 html 網頁呈現',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-c', '--config', type=str, default=my_dir+'/tdx.ini',
        help='設定檔路徑')
    G['args'] = parser.parse_args()
    tdx.init(G['args'].config)

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=tdx.load_credential, trigger='interval', seconds=7200)
    atexit.register(lambda: scheduler.shutdown())
    scheduler.start()

    # openssl req -x509 -newkey rsa:4096 -nodes -out flask-cert.pem -keyout flask-key.pem -days 36500
    # https://blog.miguelgrinberg.com/post/running-your-flask-application-over-https
    pem_dir = tdx.G['config']['DEFAULT']['FLASK_PEM_DIR']
    app.run(
        debug=True,
        host='0.0.0.0',
        port=7984,
        request_handler=MyRequestHandler,
        # ssl_context=(pem_dir+'/flask-cert.pem', pem_dir+'flask-key.pem')
        ssl_context=(pem_dir+'/flask-cert.pem', pem_dir+'/flask-key.pem')
    )
