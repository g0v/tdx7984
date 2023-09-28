import argparse, csv, json, os, sqlite3
from warnings import warn

parser = argparse.ArgumentParser(
    description='讀取 (從 tdx 取得的) *.json 公車路線與站牌資訊、 轉而存入 sqlite3 資料庫',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('dbfile', help='資料庫.sqlite3')

args = parser.parse_args()
city_dict = { 'by_code':{}, 'by_cname':{}, 'by_ename':{} }
with open('cities.csv') as F:
    for row in csv.DictReader(F):
        city_dict['by_code'][row['code']] = row
        city_dict['by_cname'][row['cname']] = row
        city_dict['by_ename'][row['ename']] = row
sqcon = sqlite3.connect(args.dbfile)
# https://jetswayss.medium.com/sqlite-insert-performance-part-1-c4a57de337bb
# https://medium.com/@JasonWyatt/squeezing-performance-from-sqlite-insertions-971aff98eef2
# https://iafisher.com/blog/2021/10/using-sqlite-effectively-in-python
for ct in list(city_dict['by_ename'].keys()):
# for ct in ['LienchiangCounty']:
    print('[', city_dict['by_ename'][ct]['cname'], ']')
    with open(f'{ct}.json') as F:
        data = json.load(F)
#    print(json.dumps(data, ensure_ascii=False))
    # https://stackoverflow.com/a/6556536 connection.execute()
    sqcon.execute('begin')
    for rt in data:
        if not 'En' in rt['SubRouteName']: rt['SubRouteName']['En'] = ''
        # NWT159525
        if not 'En' in rt['RouteName']: rt['RouteName']['En'] = ''
        # KIN92
        values = [
            rt['SubRouteUID'], rt['Direction'], rt['SubRouteName']['Zh_tw'], rt['SubRouteName']['En'], rt['RouteName']['Zh_tw'],
            rt['RouteName']['En'], rt['Stops'][0]['StopUID'], rt['Stops'][-1]['StopUID']
        ]
        sqcon.execute(
            'insert or replace into subroute(uid, dir, cname, ename, main_cname, main_ename, first_stop, last_stop) values (?, ?, ?, ?, ?, ?, ?, ?)', values
        )
        for st in rt['Stops']:
            if not 'En' in st['StopName']: st['StopName']['En'] = ''
            # NewTaipei => 917延 => 鶯歌火車站
            if not 'StationID' in st: st['StationID'] = ''
            # 連江縣的資料沒有這個欄位
            values = [
                st['StopUID'], rt['Direction'], rt['SubRouteUID'], st['StationID'], st['StopName']['Zh_tw'], st['StopName']['En'],
                st['StopSequence'], st['StopPosition']['PositionLon'], st['StopPosition']['PositionLat']
            ]
            sqcon.execute(
                'insert or replace into stop(uid, dir, srt_uid, station_id, cname, ename, sequence, longitude, latitude) values (?, ?, ?, ?, ?, ?, ?, ?, ?)', values
            )
    sqcon.execute('commit')

sqcon.close()

