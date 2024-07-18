#!/bin/bash

source tdx-credential.sh

for ct in $(grep -Po '\b[A-Z]\w+$' cities.csv) ; do
# for ct in TaitungCounty ; do # 省時測試版，只更新台東縣
    curl -H 'accept: application/json' -H "authorization: Bearer $TDX_ACCESS_TOKEN" "https://tdx.transportdata.tw/api/basic/v2/Bus/StopOfRoute/City/$ct" > city-stops/$ct.json
    sleep 8
done

./sqlify.py -f -d ./city-stops/ routes_stops.sqlite3

