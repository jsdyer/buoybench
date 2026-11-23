#!/usr/bin/env python3
"""Retain ECCC observations and narrative forecasts without frontend API calls."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib,json,math,re,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
BASE='https://dd.weather.gc.ca/'
NS={'o':'http://www.opengis.net/om/1.0','g':'http://www.opengis.net/gml'}
FIELDS={
 'windKmh':('avg_wnd_spd_pst10mts','km/h'),
 'gustKmh':('max_wnd_spd_pst10mts','km/h'),
 'windDirection':('avg_wnd_dir_pst10mts','°'),
 'waveM':('avg_sig_wave_hgt_pst20mts','m'),
 'wavePeriodS':('avg_sig_wave_pd_pst20mts','s'),
 'waterC':('avg_sea_sfc_temp_pst10mts','°C'),
 'airC':('avg_air_temp_pst10mts','°C'),
 'pressureHpa':('avg_stn_pres_pst10mts','hPa')
}
def now_iso():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def fetch(url):
 if not url.startswith(BASE) and not url.startswith('https://api.weather.gc.ca/'):raise ValueError('Unexpected source host')
 for n in range(3):
  try:
   with urlopen(Request(url,headers={'User-Agent':'CoolCode-BuoyBench/1.0 (+https://github.com/jsdyer/buoybench)'}),timeout=35) as r:
    data=r.read(4_000_001)
    if len(data)>4_000_000:raise ValueError('Response is too large')
    return data
  except HTTPError as e:
   if e.code<500:raise
   if n==2:raise
  except (OSError,TimeoutError):
   if n==2:raise
  time.sleep(n+1)
def listing(url,pattern):return sorted(set(re.findall('href="('+pattern+')"',fetch(url).decode('utf-8'))))
def validate_config(c):
 stations=c.get('stations',[]);forecasts=c.get('forecasts',[])
 if not 1<=len(stations)<=50 or len({x['id'] for x in stations})!=len(stations):raise ValueError('Use 1–50 distinct station IDs')
 if len({x['id'] for x in forecasts})!=len(forecasts):raise ValueError('Duplicate forecast ID')
 for s in stations:
  if not re.fullmatch(r'\d{5,7}',s['id']) or not s.get('name'):raise ValueError('Invalid station')
  if s.get('forecastId') and s['forecastId'] not in {f['id'] for f in forecasts}:raise ValueError('Unknown forecast reference')
 for f in forecasts:
  if not re.fullmatch(r'm\d{7}',f['id']) or f['domain'] not in ['arctic','atlantic','great_lakes','hudson','mackenzie','pacific','prairies','st_lawrence']:raise ValueError('Invalid forecast area')
 for key,lo,hi in [('retentionDays',7,365),('lookbackDays',1,3),('maxFilesPerStationPerDay',1,48)]:
  if not isinstance(c.get(key),int) or not lo<=c[key]<=hi:raise ValueError('Invalid '+key)
 return c

def parse_observation(raw,station,source,captured):
 root=ET.fromstring(raw);elements={e.get('name'):e for e in root.iter() if e.tag.rsplit('}',1)[-1]=='element'}
 values={k:e.get('value') for k,e in elements.items()}
 observed=values.get('date_tm')
 if not observed or not values.get('stn_nam'):raise ValueError('Incomplete observation')
 datetime.fromisoformat(observed.replace('Z','+00:00'))
 actual=values.get('wmo_id_extnd',values.get('wmo_identifier_extended'))
 if actual and actual!=station['id']:raise ValueError('Wrong station in source')
 result={'stationId':station['id'],'observedAt':observed,'capturedAt':captured,'source':source,'sourceName':values['stn_nam'],'latitude':float(values['lat']),'longitude':float(values['long']),'measurements':{},'qa':{},'fields':{}}
 for key,(field,unit) in FIELDS.items():
  # Older buoy products use sig_wave_hgt instead of avg_sig_wave_hgt.
  selected=field if field in elements else field.replace('avg_sig_','sig_')
  element=elements.get(selected);value=None
  if element is not None:
   if element.get('uom')!=unit:raise ValueError('Unexpected units for '+selected)
   try:
    number=float(element.get('value',''))
    if math.isfinite(number):value=number
   except ValueError:pass
   quality=[q.get('value') for q in element if q.get('name')=='qa_summary']
   result['qa'][key]=quality[0] if quality else None
   # Provider code 100 indicates the value passed its overall QA. Exclude other
   # codes from visual comparisons; retain the code so missingness is explicit.
   if quality and quality[0]!='100':value=None
  result['measurements'][key]=value;result['fields'][key]=selected
 fingerprint=json.dumps({k:v for k,v in result.items() if k not in ['capturedAt','source']},sort_keys=True)
 result['id']=hashlib.sha256(fingerprint.encode()).hexdigest()[:20]
 return result

def stamp(parent,name='Issued'):
 for e in parent.findall('dateTime'):
  if e.get('zone')=='UTC' and e.get('name')==name:
   return datetime.strptime(e.findtext('timeStamp'),'%Y%m%d%H%M').replace(tzinfo=timezone.utc).isoformat().replace('+00:00','Z')
 return None

def parse_forecast(raw,config,source,captured):
 root=ET.fromstring(raw)
 if root.tag!='marineData':raise ValueError('Wrong forecast document')
 sections=[]
 for tag in ['regularForecast','waveForecast','extendedForecast']:
  section=root.find(tag)
  if section is None:continue
  issued=stamp(section)
  for location in section.findall('location'):
   blocks=[]
   for node in location.iter():
    if node.tag in ['periodOfCoverage','wind','weatherVisibility','airTemperature','freezingSpray','wave','waves','waveHeight','textSummary','forecastPeriod','statusStatement'] and (node.text or '').strip():
     blocks.append({'field':node.tag,'period':node.get('name',''),'text':' '.join(node.text.split())})
   if blocks:sections.append({'kind':tag,'issuedAt':issued,'location':location.get('name',''),'blocks':blocks})
 if not sections or not any(x['issuedAt'] and x['kind']=='regularForecast' for x in sections):raise ValueError('Forecast has no dated regular forecast')
 record={'areaId':config['id'],'name':root.findtext('area') or config['name'],'domain':config['domain'],'issuedAt':next(x['issuedAt'] for x in sections if x['kind']=='regularForecast' and x['issuedAt']),'createdAt':stamp(root,'xmlCreation'),'capturedAt':captured,'source':source,'sections':sections}
 # Identical republications do not become separate editions; amended content does.
 record['id']=hashlib.sha256(json.dumps({'areaId':record['areaId'],'sections':sections},sort_keys=True).encode()).hexdigest()[:20]
 return record

def refresh(config_path=ROOT/'web/config.json',output=ROOT/'web/data/ledger.json'):
 c=validate_config(json.loads(config_path.read_text()));captured=now_iso();today=datetime.now(timezone.utc)
 old=json.loads(output.read_text()) if output.exists() else {'observations':[],'forecasts':[],'captures':[],'stations':[]}
 obs={x['id']:x for x in old['observations']};forecasts={x['id']:x for x in old['forecasts']}
 seen_urls={x['source'] for x in obs.values()};new_count=0;station_results=[]
 for station in c['stations']:
  print('Collecting station '+station['id'],flush=True)
  found=0
  for days in range(c['lookbackDays']):
   date=(today-timedelta(days=days)).strftime('%Y%m%d');root=f'{BASE}{date}/WXO-DD/observations/swob-ml/marine/moored-buoys/{date}/{station["id"]}/'
   try:files=listing(root,r'[^"/]+-swob\.xml')[-c['maxFilesPerStationPerDay']:]
   except HTTPError as e:
    if e.code==404:continue
    raise
   found+=len(files)
   urls=[root+name for name in files if root+name not in seen_urls]
   def read_observation(url):return parse_observation(fetch(url),station,url,now_iso())
   with ThreadPoolExecutor(max_workers=4) as pool:
    for record in pool.map(read_observation,urls):
     if record['id'] not in obs:obs[record['id']]=record;new_count+=1

  station_results.append({'stationId':station['id'],'filesAvailable':found,'status':'retrieved' if found else 'no files in requested period'})
 if not any(x['filesAvailable'] for x in station_results):raise ValueError('No station observations were retrieved; existing capture retained')
 # Enumerate each domain/day once; then select latest file per configured area.
 forecast_files={}
 for domain in sorted({f['domain'] for f in c['forecasts']}):
  print('Collecting forecasts for '+domain,flush=True)
  pending={f['id'] for f in c['forecasts'] if f['domain']==domain}
  for days in range(min(2,c['lookbackDays'])):
   if not pending:break
   day=(today-timedelta(days=days)).strftime('%Y%m%d');base=f'{BASE}{day}/WXO-DD/marine_weather/{domain}/'
   try:hours=listing(base,r'\d{2}/')
   except HTTPError as e:
    if e.code==404:continue
    raise
   for hour in reversed(hours):
    if not pending:break
    files=listing(base+hour,r'[^"/]+_en\.xml')
    for area_id in list(pending):
     matches=[x for x in files if '_'+area_id+'_en.xml' in x]
     if matches:forecast_files[area_id]=base+hour+matches[-1];pending.remove(area_id)
  if pending:raise ValueError('No forecast available for '+', '.join(sorted(pending)))
 for f in c['forecasts']:
  url=forecast_files[f['id']];record=parse_forecast(fetch(url),f,url,now_iso())
  forecasts.setdefault(record['id'],record)
 captured=now_iso()
 cutoff=(today-timedelta(days=c['retentionDays'])).isoformat().replace('+00:00','Z')
 observations=sorted((x for x in obs.values() if x['capturedAt']>=cutoff),key=lambda x:(x['observedAt'],x['capturedAt']))
 retained_forecasts=sorted((x for x in forecasts.values() if x['capturedAt']>=cutoff),key=lambda x:(x['issuedAt'],x['capturedAt']))
 # Keep removed station metadata so earlier retained observations remain usable.
 stations={x['id']:x for x in old.get('stations',[])};stations.update({x['id']:x for x in c['stations']})
 captures=[x for x in old['captures'] if x['capturedAt']>=cutoff]+[{'capturedAt':captured,'stationResults':station_results,'stationIds':[x['id'] for x in c['stations']],'observationCount':len(observations),'forecastCount':len(retained_forecasts)}]
 ledger={'schema':'coolcode.buoybench.v1','capturedAt':captured,'source':'Environment and Climate Change Canada','retentionDays':c['retentionDays'],'stations':list(stations.values()),'observations':observations,'forecasts':retained_forecasts,'captures':captures}
 output.parent.mkdir(parents=True,exist_ok=True);temp=output.with_suffix('.tmp');temp.write_text(json.dumps(ledger,ensure_ascii=False,separators=(',',':'))+'\n');temp.replace(output)
 (output.parent/'status.json').write_text(json.dumps({'retrieved_at':captured,'stations':len(c['stations']),'observations':len(observations),'forecasts':len(retained_forecasts)},indent=2)+'\n')
 print(f'Retained {len(observations)} observations, {len(retained_forecasts)} forecast editions; {new_count} new observations')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'web/config.json');p.add_argument('--output',type=Path,default=ROOT/'web/data/ledger.json');a=p.parse_args();refresh(a.config,a.output)
