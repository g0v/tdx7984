[city route stops]

for ct in $(cat cities.txt) ; do curl -H 'accept: application/json' -H "authorization: Bearer $TDX_ACCESS_TOKEN" "https://tdx.transportdata.tw/api/basic/v2/Bus/StopOfRoute/City/$ct" > $ct.json ; sleep 8 ; done

zq -f csv 'over this | { SubRouteUID, name:SubRouteName.Zh_tw, begin:Stops[0].StopName.Zh_tw, end:Stops[-1].StopName.Zh_tw }' MiaoliCounty.json

