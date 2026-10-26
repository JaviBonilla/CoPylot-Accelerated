from pathlib import Path
import sys,unittest
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'benchmarks'))
from annual_matrix import epw_candidates,retained
class AnnualWorkload(unittest.TestCase):
 def rows(self):
  start=datetime(2011,1,1);rows=[]
  for i in range(8760):
   d=start+timedelta(hours=i);r=['0']*35;r[1:5]=[str(d.month),str(d.day),str(d.hour+1),'0'];r[14]='123';rows.append(r)
  return rows
 def test_full_calendar_midpoints_and_hour24(self):
  points=epw_candidates(self.rows());self.assertEqual(len(points),8760);self.assertEqual(points[0]['hour'],.5);self.assertEqual(points[23]['hour'],23.5);self.assertEqual(points[-1]['dni'],123.)
 def test_missing_duplicate_or_invalid_weather_is_rejected(self):
  rows=self.rows()
  with self.assertRaises(RuntimeError):epw_candidates(rows[:-1])
  rows[2]=rows[1]
  with self.assertRaises(RuntimeError):epw_candidates(rows)
  rows=self.rows();rows[0][14]='9999'
  with self.assertRaises(RuntimeError):epw_candidates(rows)
 def test_night_omission_keeps_every_daylight_zero_dni_and_identity(self):
  points=[{'month':1,'day':1,'hour':v,'dni':0.} for v in range(4)]
  selected,night=retained(points,lambda site,m,d,h:[42.,h-1],[])
  self.assertEqual(night,2);self.assertEqual([p['id'] for p in selected],[2,3]);self.assertEqual([p['dni'] for p in selected],[0.,0.])
if __name__=='__main__':unittest.main()
