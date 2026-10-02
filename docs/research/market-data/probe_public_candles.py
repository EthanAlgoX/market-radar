"""Small unauthenticated, read-only source probes; no dependency installation or live app writes."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from urllib.parse import urlencode
import json,math,time
root=Path(__file__).parent
sources=[('crypto_binance_1h','https://data-api.binance.vision/api/v3/klines?'+urlencode({'symbol':'BTCUSDT','interval':'1h','limit':120})),('us_yahoo_daily','https://query1.finance.yahoo.com/v8/finance/chart/AAPL?'+urlencode({'range':'1mo','interval':'1d','includePrePost':'false','events':'div,splits'})),('hk_yahoo_daily','https://query1.finance.yahoo.com/v8/finance/chart/0700.HK?'+urlencode({'range':'1mo','interval':'1d','includePrePost':'false','events':'div,splits'})),('cn_eastmoney_daily','https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode({'secid':'1.600519','klt':'101','fqt':'0','beg':'0','end':'20500101','lmt':'80','fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}))]
results=[]
for name,url in sources:
    record={'source':name,'request_url':url,'captured_at':datetime.now(timezone.utc).isoformat(),'authentication':'none','method':'GET'}
    started=time.monotonic()
    try:
        with urlopen(Request(url,headers={'User-Agent':'MarketRadarResearch/0.2','Accept':'application/json'}),timeout=8) as response:
            raw=response.read(2*1024*1024+1)
            record['http_status']=response.status
        if len(raw)>2*1024*1024:
            raise ValueError('response size limit')
        data=json.loads(raw)
        (root/(name+'-response.json')).write_text(json.dumps(data,ensure_ascii=False))
        if name.startswith('crypto'):
            now_ms=int(time.time()*1000)
            bars=[{'start':int(row[0]),'open':float(row[1]),'high':float(row[2]),'low':float(row[3]),'close':float(row[4]),'volume':float(row[5]),'end':int(row[6]),'closed':int(row[6])<now_ms} for row in data]
            (root/(name+'-bars.json')).write_text(json.dumps(bars,indent=2))
            record.update(rows=len(bars),duplicate_timestamps=len(bars)-len({b['start'] for b in bars}),ohlc_violations=sum(not (b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high']) for b in bars),nonfinite_or_negative_volume=sum(not math.isfinite(b['volume']) or b['volume']<0 for b in bars),gap_count=sum(bars[i]['start']-bars[i-1]['start']!=3600000 for i in range(1,len(bars))),unclosed_rows=sum(not b['closed'] for b in bars),oldest_bar=datetime.fromtimestamp(bars[0]['start']/1000,timezone.utc).isoformat(),latest_bar=datetime.fromtimestamp(bars[-1]['start']/1000,timezone.utc).isoformat())
        elif 'yahoo' in name:
            result=data['chart']['result'][0]
            quotes=result['indicators']['quote'][0]
            record.update(rows=len(result.get('timestamp',[])),currency=result.get('meta',{}).get('currency'),exchange_timezone=result.get('meta',{}).get('exchangeTimezoneName'),null_ohlcv_rows=sum(any(quotes[key][i] is None for key in ['open','high','low','close','volume']) for i in range(len(result.get('timestamp',[])))),latest_bar=datetime.fromtimestamp(result['timestamp'][-1],timezone.utc).isoformat())
        else:
            k=(data.get('data') or {}).get('klines',[])
            record.update(rows=len(k),latest_bar=k[-1].split(',')[0] if k else None,upstream_code=data.get('rc'))
    except HTTPError as error:
        record.update(http_status=error.code,error='provider rejected this public request; no retry or bypass')
    except (URLError,TimeoutError,OSError,ValueError,KeyError,TypeError) as error:
        record.update(error=type(error).__name__)
    record['elapsed_seconds']=round(time.monotonic()-started,2)
    results.append(record)
    print(json.dumps(record,ensure_ascii=False),flush=True)
    (root/'public-probe-results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
