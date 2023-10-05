import requests, json, os, csv, re
from operator import itemgetter

city_list = {
    'by_code': {}, 'by_cname': {}, 'by_ename': {}
}

G = {
    'headers': {
        'accept': 'application/json'
    },
}

def init(dbpath=''):
    global city_list, G
    m = re.search(r'(.*)/', __file__)
    my_dir = m.group(1)
    G['dbpath'] = f'{my_dir}/routes_stops.sqlite3' if dbpath == '' else dbpath
    with open(f'{my_dir}/cities.csv') as F:
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
    with open(os.environ['HOME']+'/.cache/tdx/tdx-credential.json') as f:
        G['credential'] = json.load(f)['access_token']
    G['headers']['authorization'] = f'Bearer {G["credential"]}'

def query(qs):
    global G
    try:
        response = requests.get(f'https://tdx.transportdata.tw/api/basic/v2/{qs}', headers=G['headers'], timeout=5).json()
    except Exception as ex:
        # https://stackoverflow.com/a/9824050
        print(type(ex).__name__, ex.args)
        return []
    if type(response) is dict and 'Not Found' in response['message']:
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
    stops_to = sorted(stops_to, key=itemgetter('StopSequence'))
    stops_fro = sorted(stops_fro, key=itemgetter('StopSequence'), reverse=True)
    by_name_to = {}
    by_name_fro = {}
    for s in stops_to:
        by_name_to[ s['StopName']['Zh_tw'] ] = s
    for s in stops_fro:
        by_name_fro[ s['StopName']['Zh_tw'] ] = s
    i_to = 0 ; i_fro = 0 ; ans = []
    while i_to < len(stops_to) and i_fro < len(stops_fro) :
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
    ans += stops_to[i_to:] + stops_fro[i_fro:]
    return ans

def bike_stations(city):
    ans = query(f'/Bike/Station/City/{city_ename(city)}')
    return [geojify(b, name_path='StationName/Zh_tw', coord_path='StationPosition') for b in ans]

def bus_pos(city, srt_name, to_fro=2):
    # to_fro: 0 去程 / 1 回程 / 2 全部
    ans = query(f'Bus/RealTimeByFrequency/City/{city_ename(city)}/{srt_name}')
    if to_fro < 2:
        ans = [ b for b in ans if b['Direction']==to_fro ]
    return [geojify(b, name_path='PlateNumb', coord_path='BusPosition') for b in ans]

def bus_stops(city, srt_name, to_fro=3):
    # to_fro: 0 去程 / 1 回程 / 2 全部 / 3 聯集， 刪除重複
    ans = query(f'Bus/StopOfRoute/City/{city_ename(city)}/{srt_name}')
    # 例如台北 "307"， 在 tdx api 裡面會撈到
    # 307莒光往板橋前站、 307莒光往撫遠街、 307西藏往板橋前站(停駛)、 307西藏往撫遠街(停駛)、 307西藏往板橋前站、 307西藏往撫遠街、
    route = list(filter(lambda r: not '停駛' in r['SubRouteName']['Zh_tw'], ans))
    route = list(filter(lambda r: r['RouteName']['Zh_tw']==srt_name, route))
    if len(route) > 2:
        # 例如新北 243
        route = list(filter(lambda r: r['SubRouteName']['Zh_tw']==srt_name, route))
    # if len(route) == 0: return []
    assert(len(route) <= 2)
    if route[0]['Direction']==1 and len(route)>1:
        route = [ route[1], route[0] ]
    if len(route) < 2 : to_fro = 0
    if to_fro < 2:
        route = route[to_fro]['Stops']
    elif to_fro == 3 and len(route) == 2:
        route = merge_dir(route[0]['Stops'], route[1]['Stops'])
    else:
        route = [ s for srt in route for s in srt['Stops'] ]
    return [geojify(s, name_path='StopName/Zh_tw', coord_path='StopPosition') for s in route]

def bus_est(city, srt_name):
    # https://motc-ptx.gitbook.io/tdx-zi-liao-shi-yong-kui-hua-bao-dian/data_notice/public_transportation_data/bus_static_data 站牌、站位與組站位間之差異
    ans = query(f'Bus/EstimatedTimeOfArrival/City/{city_ename(city)}/{srt_name}')
    if ans == []: return []
    n = len(list(filter(lambda r: 'StopSequence' in r, ans)))
    if float(n)/len(ans)<0.2:
        # 台北市的 EstimatedTimeOfArrival 好像都沒有 StopSequence
        stop_info = dict(
            (s['properties']['StopUID'], s) for s in bus_stops(city, srt_name, to_fro=2)
        )
    est_to = [] ; est_fro = []
#    print(json.dumps(ans, ensure_ascii=False))
    for stop in ans:
        if stop['RouteName']['Zh_tw'] != srt_name: continue
        # 台北市沒有 SubRouteID？ 例如 243、 307
        if '裁撤' in stop['StopName']['Zh_tw']:
            # NWT34537 '連城景平路(暫時裁撤)'
            continue
        est_1 = stop
        if not 'StopSequence' in stop:
            if stop['StopUID'] in stop_info:
                stop['StopSequence'] = stop_info[stop['StopUID']]['properties']['StopSequence']
            else:
                # 台北 藍28、
                stop['StopSequence'] = 999
                print(f'不存在的 StopUID： { stop["StopUID"] } ({srt_name})')
        if stop['Direction'] == 0 :
            est_to.append(est_1)
        else:
            est_fro.append(est_1)
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

init()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='tdx api test',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('city', type=str, help='縣市')
    parser.add_argument('route_name', type=str, help='路線名稱')
    args = parser.parse_args()
#    ans = query(f'Bus/EstimatedTimeOfArrival/City/Taichung/{args.route_name}')
#    print(json.dumps(ans, ensure_ascii=False))
#    print(json.dumps(bus_est(args.city, args.route_name), ensure_ascii=False))
    print(json.dumps(bus_est(args.city, args.route_name), ensure_ascii=False))
