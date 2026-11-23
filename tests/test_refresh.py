import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import parse_observation,parse_forecast,validate_config,refresh,fetch
from urllib.error import HTTPError
ROOT=Path(__file__).resolve().parents[1]

def obs(value='18.52',qa='100',unit='km/h'):
 return f'''<root><element name="wmo_id_extnd" value="4600146"/><element name="stn_nam" value="HALIBUT BANK"/><element name="date_tm" value="2026-01-01T00:00:00Z"/><element name="lat" value="49.34"/><element name="long" value="-123.73"/><element name="avg_wnd_spd_pst10mts" uom="{unit}" value="{value}"><qualifier name="qa_summary" value="{qa}"/></element></root>'''.encode()
FORECAST=b'''<marineData><area>Test area</area><regularForecast><dateTime name="Issued" zone="UTC"><timeStamp>202601010000</timeStamp></dateTime><location name="South"><weatherCondition><periodOfCoverage>Today and tonight.</periodOfCoverage><wind>Wind east 15 knots.</wind></weatherCondition></location></regularForecast></marineData>'''
class RefreshTests(unittest.TestCase):
 def test_missing_badqa_zero_and_wrong_units(self):
  args=({'id':'4600146'},'https://dd.weather.gc.ca/a.xml','2026-01-01T01:00:00Z')
  self.assertEqual(parse_observation(obs(),*args)['measurements']['windKmh'],18.52)
  self.assertEqual(parse_observation(obs('0'),*args)['measurements']['windKmh'],0)
  self.assertIsNone(parse_observation(obs('MSNG'),*args)['measurements']['windKmh'])
  self.assertIsNone(parse_observation(obs(qa='200'),*args)['measurements']['windKmh'])
  with self.assertRaisesRegex(ValueError,'units'):parse_observation(obs(unit='m/s'),*args)
 def test_capture_is_not_part_of_edition_identity(self):
  c={'id':'m0000028','name':'Test','domain':'pacific'}
  a=parse_forecast(FORECAST,c,'https://dd.weather.gc.ca/a.xml','2026-01-01T01:00:00Z');b=parse_forecast(FORECAST,c,'https://dd.weather.gc.ca/b.xml','2026-01-01T02:00:00Z')
  self.assertEqual(a['id'],b['id']);self.assertEqual(a['issuedAt'],'2026-01-01T00:00:00Z')
  amended=parse_forecast(FORECAST.replace(b'15 knots',b'20 knots'),c,'https://dd.weather.gc.ca/c.xml','2026-01-01T03:00:00Z');self.assertNotEqual(a['id'],amended['id'])
 def test_wave_narrative_and_its_issue_time_are_retained(self):
  wave=b'<waveForecast><dateTime name="Issued" zone="UTC"><timeStamp>202601010300</timeStamp></dateTime><location><weatherCondition><periodOfCoverage>Today.</periodOfCoverage><textSummary>Seas 1 to 2 metres.</textSummary></weatherCondition></location></waveForecast>'
  data=FORECAST.replace(b'</marineData>',wave+b'</marineData>')
  r=parse_forecast(data,{'id':'m0000028','name':'Test','domain':'pacific'},'https://dd.weather.gc.ca/a.xml','2026-01-01T04:00:00Z')
  section=next(x for x in r['sections'] if x['kind']=='waveForecast')
  self.assertEqual(section['issuedAt'],'2026-01-01T03:00:00Z');self.assertEqual(section['blocks'][-1]['text'],'Seas 1 to 2 metres.')
 def test_forecast_requires_dated_regular_content(self):
  with self.assertRaisesRegex(ValueError,'dated regular'):parse_forecast(b'<marineData><area>Test</area></marineData>',{'id':'m0000028'},'x','2026-01-01T00:00:00Z')
 def test_can_add_station_beyond_starter_list(self):
  c=json.loads((ROOT/'web/config.json').read_text());original=len(c['stations']);c['stations'].append({'id':'4600206','name':'La Perouse Bank','coast':'Pacific','forecastId':'','forecastLocation':''});self.assertEqual(len(validate_config(c)['stations']),original+1)
 def test_denial_or_rate_limit_is_not_retried(self):
  for code in [403,429]:
   with self.subTest(code=code),patch('refresh.urlopen',side_effect=HTTPError('https://dd.weather.gc.ca/x',code,'denied',{},None)) as request,patch('refresh.time.sleep') as wait:
    with self.assertRaises(HTTPError):fetch('https://dd.weather.gc.ca/x')
    self.assertEqual(request.call_count,1);wait.assert_not_called()
 def test_failed_fetch_never_replaces_good_data(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'ledger.json';value={'observations':[],'forecasts':[],'captures':[],'stations':[]};p.write_text(json.dumps(value));before=p.read_bytes()
   with patch('refresh.fetch',side_effect=OSError('Source unavailable')):
    with self.assertRaises(OSError):refresh(ROOT/'web/config.json',p)
   self.assertEqual(p.read_bytes(),before)
if __name__=='__main__':unittest.main()
