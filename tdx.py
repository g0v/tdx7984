import logging, configparser, requests, json, csv, re, sqlite3
from operator import itemgetter

city_list = {
    'by_code': {}, 'by_cname': {}, 'by_ename': {}
}

G = {
    'headers': {
        'accept': 'application/json'
    },
}

def init(config_path=''):
    global city_list, G

    if not config_path:
        m = re.search(r'(.*)/', __file__)
        config_path = m.group(1) + '/tdx.ini'
    G['config'] = configparser.ConfigParser()
    G['config'].read(config_path)
    # 還有 "interpolation" 功能!
    # https://florian-dahlitz.de/articles/how-to-work-with-config-files-in-python
    dbpath = G['config']['DEFAULT']['WORK_DIR'] + '/routes_stops.sqlite3'
    G['dbcon'] = sqlite3.connect(dbpath, check_same_thread=False)
    # https://stackoverflow.com/a/2894830
    # https://ricardoanderegg.com/posts/python-sqlite-thread-safety/
    # https://stackoverflow.com/a/53253110 還沒用到

    G['dbcon'].row_factory = sqlite3.Row
    # https://stackoverflow.com/questions/3300464/how-can-i-get-dict-from-sqlite-query
    with open(G['config']['DEFAULT']['WORK_DIR'] + '/cities.csv') as F:
        for row in csv.DictReader(F):
            city_list['by_code'][row['code']] = row
            city_list['by_cname'][row['cname']] = row
            city_list['by_ename'][row['ename']] = row
    load_credential()

def city_code(name):
    global city_list
    if name in city_list['by_code'].keys():
        return name
    if name in city_list['by_ename'].keys():
        return city_list['by_ename'][name]['code']
    if re.search(r'(縣|市)$', name):
        return city_list['by_cname'][name]['code'] if name in city_list['by_cname'].keys() else ''
    if name+'市' in city_list['by_cname'].keys():
        return city_list['by_cname'][name+'市']['code']
    elif name+'縣' in city_list['by_cname'].keys():
        return city_list['by_cname'][name+'縣']['code']
    return ''

def city_ename(name):
    global city_list
    code = city_code(name)
    return city_list['by_code'][code]['ename'] if code != '' else ''

def load_credential():
    global G
    with open(G['config']['DEFAULT']['TDX_TOKEN_DIR']+'/tdx-credential.json') as f:
        G['credential'] = json.load(f)['access_token']
    G['headers']['authorization'] = f'Bearer {G["credential"]}'

def query(qs):
    global G
    try:
        response = requests.get(f'https://tdx.transportdata.tw/api/basic/v2/{qs}', headers=G['headers'], timeout=5).json()
    except Exception as ex:
        # https://stackoverflow.com/a/9824050
        logging.warning(str(ex))
        return []
    if type(response) is dict:
        msg = response['message'] if 'message' in response else response['Message']
        if 'Not Found' in msg or 'not accepted' in msg:
            # 南投沒有 ubike
            # warn(json.dumps(qs + ': ' + response, ensure_ascii=False))
            logging.warning(json.dumps(qs + ': ' + msg, ensure_ascii=False))
            return []
    return response

def geojify(point, coord_path='', name_path=''):
    name = point
    for k in name_path.split('/'): name = name[k]
    coord = point[coord_path]
    ans = {
        'type': 'Feature',
        'properties': {
            'name': name,
            'GeoHash': coord['GeoHash']
        },
        'geometry': {
            'type': 'Point',
            'coordinates': [
                coord['PositionLon'],
                coord['PositionLat']
            ]
        }
    }
    for k in point:
        if k in [coord_path, name_path]: continue
        ans['properties'][k] = point[k]
    return ans
    
def merge_dir(stops_to, stops_fro, keep_dup=False):
    # logging.debug('# of stops_to and stops_fro: {} {}'.format(len(stops_to), len(stops_fro)))
    stops_to = sorted(stops_to, key=itemgetter('StopSequence'))
    stops_fro = sorted(stops_fro, key=itemgetter('StopSequence'), reverse=True)
    # logging.warning(json.dumps([ x['StopName']['Zh_tw'] for x in stops_to], ensure_ascii=False))
    by_name_to = {}
    by_name_fro = {}
    for s in stops_to:
        by_name_to[ s['StopName']['Zh_tw'] ] = s
    for s in stops_fro:
        by_name_fro[ s['StopName']['Zh_tw'] ] = s
    i_to = 0 ; i_fro = 0 ; ans = []
    while i_to < len(stops_to) and i_fro < len(stops_fro) :
        # logging.debug('{} {} {} {}'.format(i_to, stops_to[i_to]['StopName']['Zh_tw'], stops_fro[i_fro]['StopName']['Zh_tw'], i_fro))
        if stops_to[i_to]['StopName']['Zh_tw'] ==  stops_fro[i_fro]['StopName']['Zh_tw'] :
            ans.append(stops_to[i_to])
            if keep_dup:
                ans.append(stops_fro[i_fro])
            i_to += 1 ; i_fro += 1
            continue
        while i_to < len(stops_to) and not stops_to[i_to]['StopName']['Zh_tw'] in by_name_fro :
            ans.append(stops_to[i_to])
            i_to += 1
        while i_fro < len(stops_fro) and not stops_fro[i_fro]['StopName']['Zh_tw'] in by_name_to :
            ans.append(stops_fro[i_fro])
            i_fro += 1
        if i_to < len(stops_to) and stops_to[i_to]['StopName']['Zh_tw'] in by_name_fro and \
           i_fro < len(stops_fro) and stops_fro[i_fro]['StopName']['Zh_tw'] in by_name_to:
            # 南投/3 台北/310 會讓流程走到這裡
            i_to += 1
            i_fro += 1
    # logging.debug('# of ans, i_to, i_fro: {} {} {}'.format(len(ans), i_to, i_fro)) 
    ans += stops_to[i_to:] + stops_fro[i_fro:]
    return ans

def bus_pos(city, srt_name, to_fro=2):
    # to_fro: 0 去程 / 1 回程 / 2 全部
    ans = query(f'Bus/RealTimeByFrequency/City/{city_ename(city)}/{srt_name}')
    if to_fro < 2:
        ans = [ b for b in ans if b['Direction']==to_fro ]
    return ans

def bus_est(city, srt_name):
    ans = stops_need_srt_key(query(f'Bus/EstimatedTimeOfArrival/City/{city_ename(city)}/{srt_name}'))
    return [ s for s in ans if srt_name==s['SubRouteName']['Zh_tw'] ]

def bus_stops(city, srt_name, to_fro=3):
    # to_fro: 0 去程 / 1 回程 / 2 全部 / 3 聯集， 刪除重複
    ans = query(f'Bus/StopOfRoute/City/{city_ename(city)}/{srt_name}')
    # 一個路線名稱可能會撈到好幾筆實際路線的記錄；
    # 例如台北 "307"， 在 tdx api 裡面會撈到
    # 307莒光往板橋前站、 307莒光往撫遠街、 307西藏往板橋前站(停駛)、 307西藏往撫遠街(停駛)、 307西藏往板橋前站、 307西藏往撫遠街、
    route = []
    # 2024/5/3 tdx 有時會傳回 "message" 而不是一個 dict!?
    for rte in ans:
        if type(rte) == dict and rte['RouteName']['Zh_tw']==srt_name and not '停駛' in rte['SubRouteName']['Zh_tw']:
            route.append(rte)
    if len(route) > 2:
        # 例如新北 243
        route = list(filter(lambda r: r['SubRouteName']['Zh_tw']==srt_name, route))
    # if len(route) == 0: return []
    if len(route) > 2:
        # 南投 3 號傳回六筆， 但起迄只有 「南岸到溪頭」、
        # 「溪頭到南岸」 兩種 => 刪除重複的
        deduped = []
        seen = {}
        for rte in route:
            first = f"{rte['Stops'][0]['StopName']['Zh_tw']}"
            last = f"{rte['Stops'][-1]['StopName']['Zh_tw']}"
            key = f'{first}#{last}'
            if key in seen: continue
            seen[key] = True
            deduped.append(rte)
        route = deduped
    assert(len(route) <= 2)
    if len(route) == 0:
        # select stop.uid, stop.cname, stop.srt_uid, subroute.cname, stop.dir, stop.station_id from stop join subroute on stop.srt_uid=s ubroute.uid where stop.cname="第三市場" and substr(stop.uid,1,3)="TXG"
        # => 出現不存在的 48 路
        return []
    if route[0]['Direction']==1 and len(route)>1:
        route = [ route[1], route[0] ]
    if len(route) < 2 : to_fro = 0
    if to_fro < 2:
        route = route[to_fro]['Stops']
    elif to_fro == 3 and len(route) == 2:
        route = merge_dir(route[0]['Stops'], route[1]['Stops'])
    else:
        route = [ s for srt in route for s in srt['Stops'] ]
    return route

def stops_need_srt_key(stops):
    # 台北市跟新北市沒有 SubRouteUID？ 例如 243、 307
    # 拿 RouteUID 來補。 SubRouteName 也是。
    # 可以處理一個 stop 或一整個 list 的 stops
    if not isinstance(stops, (list, tuple)):
        stops = [stops]
    for s in stops:
        if not 'SubRouteName' in s:
            if 'RouteName' in s:
                s['SubRouteName'] = s['RouteName']
            else:
                s['SubRouteName'] = {'Zh_tw': '不明'}
                logging.warning('這個站牌沒有 SubRouteName 也沒有 RouteName： ' + json.dumps(s, ensure_ascii=False))
        if not 'SubRouteUID' in s:
            if 'RouteUID' in s:
                s['SubRouteUID'] = s['RouteUID']
            else:
                s['SubRouteUID'] = '不明'
                logging.warning('這個站牌沒有 SubRouteUID 也沒有 RouteUID： ' + json.dumps(s, ensure_ascii=False))
    return stops

def fill_stops_info_along_srt(stops_along_srt):
    # https://motc-ptx.gitbook.io/tdx-zi-liao-shi-yong-kui-hua-bao-dian/data_notice/public_transportation_data/bus_static_data 站牌、站位與組站位間之差異
    stops_need_srt_key(stops_along_srt)
    if len(stops_along_srt) < 1: return []
    srt_uid = stops_along_srt[0]['SubRouteUID']
    srt_name = stops_along_srt[0]['SubRouteName']['Zh_tw']
    if len(stops_along_srt) > 1:
        if not (srt_uid==stops_along_srt[1]['SubRouteUID'] and srt_uid==stops_along_srt[-1]['SubRouteUID']):
            logging.warning('混雜的 SubRouteUID: ' + json.dumps([(s['SubRouteUID'], s['StopName']['Zh_tw']) for s in stops_along_srt], ensure_ascii=False))
    dbcursor = G['dbcon'].cursor()
    dbcursor.execute( f'select * from stop where srt_uid ="{srt_uid}"' )
    ans = dbcursor.fetchall()
    dbcursor.close()
    if len(ans)<1:
        # 台北市 221 的 SubRouteUID， 有時叫做 TPE10415 有時叫做 TPE104150
        # 再試試看 (無法用 index， 較慢的) like：
        dbcursor = G['dbcon'].cursor()
        dbcursor.execute( f'select * from stop where srt_uid like "{srt_uid}%"' )
        ans = dbcursor.fetchall()
        dbcursor.close()
        if len(ans)<1:
            logging.warning(f'不存在的 SubRouteUID： {srt_uid} [{srt_name}]')
    ans = { s['uid']: s for s in ans } # 轉換成以 StopUID 為 key 的 dict
    for stop in stops_along_srt:
        if stop['StopUID'] in ans:
            stop.update(ans[stop['StopUID']])
        # 從 db 讀來的 sequence 有問題? 可以拿台中 200 號實驗
        # 總之如果原來 estimate 裡面已有 StopSequence， 就不要去動它
        if 'sequence' in stop and not 'StopSequence' in stop:
            stop['StopSequence'] = stop['sequence']
        if 'longitude' in stop and not 'StopPosition' in stop:
            stop['StopPosition'] = {
                'PositionLat': stop['latitude'],
                'PositionLon': stop['longitude'],
            }
        # NWT34537 '連城景平路(暫時裁撤)'
    return stops_along_srt

def fill_stop_info(stop):
    return fill_stops_info_along_srt([stop])

def merged_bus_est(est_list):
    est_to = [] ; est_fro = []
    for stop in est_list:
        if stop['Direction'] == 0 :
            est_to.append(stop)
        else:
            est_fro.append(stop)
    merged = merge_dir(est_to, est_fro, keep_dup=True)
    deduped = []
    i = 0
    to_copy = [ 'StopUID', 'StopSequence', 'EstimateTime', 'PlateNumb', 'Estimates' ]
    while i < len(merged) - 1:
        deduped.append(merged[i])
        if merged[i]['StopName']['Zh_tw'] == merged[i+1]['StopName']['Zh_tw']:
            k0 = i
            if merged[i]['Direction'] == 1:
                k0 = i+1
            k1 = i+i+1 - k0 # 對面的站牌
            assert(merged[k0]['Direction']+merged[k1]['Direction']==1)
            deduped[-1]['dir0'] = { key: merged[k0][key] for key in to_copy if key in merged[k0] }
            deduped[-1]['dir1'] = { key: merged[k1][key] for key in to_copy if key in merged[k1] }
            i += 2
        else:
            if deduped[-1]['Direction'] == 0:
                deduped[-1]['dir0'] = { key: merged[i][key] for key in to_copy if key in merged[i] }
            else:
                deduped[-1]['dir1'] = { key: merged[i][key] for key in to_copy if key in merged[i] }
            i += 1
    if i < len(merged):
        deduped.append(merged[i])
        if deduped[-1]['Direction'] == 0:
            deduped[-1]['dir0'] = { key: merged[i][key] for key in to_copy if key in merged[i] }
        else:
            deduped[-1]['dir1'] = { key: merged[i][key] for key in to_copy if key in merged[i] }
    return deduped

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%m/%d %H:%M:%S',
    )
    m = re.search(r'(.*)/', __file__)
    my_dir = m.group(1)
    import argparse
    parser = argparse.ArgumentParser(
        description='tdx api test',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-c', '--config', type=str, default=my_dir+'/tdx.ini',
        help='設定檔路徑')
    parser.add_argument('city', type=str, help='縣市')
    parser.add_argument('route_name', type=str, help='路線名稱')
    args = parser.parse_args()
    init(args.config)
#    ans = bus_stops(args.city, args.route_name)
    ans = merged_bus_est(fill_stops_info_along_srt(bus_est(args.city, args.route_name)))
    logging.info(json.dumps(ans, ensure_ascii=False))

