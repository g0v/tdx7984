# tdx7984
"去坐巴士" 把交通部 tdx 的少數幾個 API 再包裝一下，以 flask 在網頁上提供 geojson 輸出及 html 輸出。


## 準備工作： 所有縣市的路線及站牌靜態資訊

1. 從 tdx API 取得路線與站牌靜態資訊： ```for ct in $(grep -Po '\b[A-Z]\w+$' cities.csv) ; do curl -H 'accept: application/json' -H "authorization: Bearer $TDX_ACCESS_TOKEN" "https://tdx.transportdata.tw/api/basic/v2/Bus/StopOfRoute/City/$ct" > $ct.json ; sleep 8 ; done```
1. zq 範例： 列出某縣市所有路線名稱及起迄站名： ```zq -f csv -i json 'over this | { SubRouteUID, name:SubRouteName.Zh_tw, begin:Stops[0].StopName.Zh_tw, end:Stops[-1].StopName.Zh_tw }' Taipei.json```
1. zq 範例： 列出某縣市所有路線的所有站牌名稱： ```zq -f csv -i json 'over this | over Stops with RouteUID,RouteName => ({rt_uid:RouteUID, rt_name:RouteName.Zh_tw, stn_id:StationID, stop_uid:StopUID, stop_name:StopName.Zh_tw})' Taipei.json```
1. 刪除舊的資料庫、重新建立空的資料庫： ```rm -f routes_stops.sqlite3 ; sqlite3 routes_stops.sqlite3 < create_db.sql```
1. 把各縣市的 json 檔匯入 sqlite3： ```python3 sqlify.py routes_stops.sqlite3```
1. 進入 ```sqlite routes_stops.sqlite3```， 然後測試： ```select stop.uid, stop.cname, stop.station_id, stop.subroute, subroute.cname from stop join subroute on stop.subroute=subroute.uid where stop.cname="一女中(公園)" order by station_id```

參考閱讀：
1. [運輸資料流通服務 tdx 範例 ](https://newtoypia.blogspot.com/2022/10/tdx.html)
1. [json 裁剪/轉檔 (例如轉 csv) 都交給它了： 強大且易用的 zq](https://newtoypia.blogspot.com/2022/05/json-csv-zq.html)
1. [用 zq 處理 json 檔第二層陣列的語法](https://newtoypia.blogspot.com/2022/12/zq.html)

