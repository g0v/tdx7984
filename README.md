# tdx7984
"去坐巴士" 把交通部 tdx 的少數幾個 API 再包裝一下，以 flask 在網頁上提供 geojson 輸出及 html 輸出。


## 準備工作： 所有縣市的路線及站牌靜態資訊

1. 取得靜態資訊：
```for ct in $(cat cities.txt) ; do curl -H 'accept: application/json' -H "authorization: Bearer $TDX\_ACCESS\_TOKEN" "https://tdx.transportdata.tw/api/basic/v2/Bus/StopOfRoute/City/$ct" > $ct.json ; sleep 8 ; done```
2. 列出某縣市所有路線名稱及起迄站名：
```zq -f csv -i json 'over this | { SubRouteUID, name:SubRouteName.Zh\_tw, begin:Stops[0].StopName.Zh\_tw, end:Stops[-1].StopName.Zh\_tw }' Taipei.json```
3. 列出某縣市所有路線的所有站牌名稱：
```zq -f csv -i json 'over this | over Stops with RouteUID,RouteName => ({rt\_uid:RouteUID, rt\_name:RouteName.Zh\_tw, stn\_id:StationID, stop\_uid:StopUID, stop\_name:StopName.Zh\_tw})' Taipei.json```

參考閱讀：
1. [運輸資料流通服務 tdx 範例 ](https://newtoypia.blogspot.com/2022/10/tdx.html)
2. [json 裁剪/轉檔 (例如轉 csv) 都交給它了： 強大且易用的 zq](https://newtoypia.blogspot.com/2022/05/json-csv-zq.html)
3. [用 zq 處理 json 檔第二層陣列的語法](https://newtoypia.blogspot.com/2022/12/zq.html)

