import argparse, tdx, json

parser = argparse.ArgumentParser(
    description='取得某縣市公車名稱清單',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument('city', type=str, help='縣市')
args = parser.parse_args()

tdx.load_credential()
ans = tdx.query(f'Bus/Route/City/{tdx.city_ename(args.city)}')
# print(json.dumps(ans, ensure_ascii=False))
print('uid,路線,起站,迄站')
out = []
for route in ans:
    for sr in route['SubRoutes']:
        line = [ sr['SubRouteUID'] ]
        line.append( sr['SubRouteName']['Zh_tw'] )
        line.append( route['DepartureStopNameZh'] if 'DepartureStopNameZh' in route else '' )
        line.append( route['DestinationStopNameZh'] if 'DestinationStopNameZh' in route else '' )
        out.append(line)
out = sorted(out, key=lambda x: x[0])
for line in out:
    print(','.join(line))
