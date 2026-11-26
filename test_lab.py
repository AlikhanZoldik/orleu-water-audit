import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from balance import volumes

ROOT = Path(__file__).resolve().parent


class BlindExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = subprocess.Popen([sys.executable,str(ROOT/"app.py"),"--port","0",
            "--no-browser","--db",str(Path(cls.tmp.name)/"audit.db")],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        cls.url = cls.server.stdout.readline().decode().strip()

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait()
        cls.server.stdout.close()
        cls.tmp.cleanup()

    def api(self, op, **data):
        req = Request(self.url+"/api/"+op,json.dumps(data).encode(),{"Content-Type":"application/json"})
        with urlopen(req) as response:
            return json.load(response)

    def test_import(self):
        with urlopen(self.url) as response:
            self.assertIn("Слепой опыт",response.read().decode())
        files = [p.read_text() for p in sorted((ROOT/"examples/calibration").glob("*.csv"))]
        sid = self.api("series",source="real",mode="counter",files=files)["series"]["id"]
        for i,k,x,y,expected in [(1,1,0,0,[]),(2,3,0,.308095,[2]),(3,2,.30646,0,[])]:
            raw = (ROOT/f"examples/run_0{i}.csv").read_text()
            cur = self.api("load",sid=sid,mode="counter",raw=raw)["current"]
            d = dict(sid=sid,rid=cur["id"])
            with self.assertRaises(HTTPError) as denied:
                self.api("reveal",**d,kind=k,x=x,y=y)
            denied.exception.close()
            state = self.api("predict",**d)
            p = state["current"]["p"]
            self.assertEqual(p["zones"],expected)
            self.assertEqual(p["status"],"invalid" if i==3 else "ok")
            self.assertEqual(len(state["log"]),i-1)
            with self.assertRaises(HTTPError) as denied:
                self.api("predict",**d)
            denied.exception.close()
            log = self.api("reveal",**d,kind=k,x=x,y=y)["log"]
            self.assertEqual(log[-1]["p"],p)
            print("CSV",i,p.get("residual",p.get("reason")),p["status"])

    def test_simulator(self):
        sid = self.api("series",source="sim")["series"]["id"]
        for _ in range(30):
            state = self.api("load",sid=sid)
            d = dict(sid=sid,rid=state["current"]["id"])
            self.assertNotIn("truth",state["current"])
            self.api("predict",**d)
            log = self.api("reveal",**d)["log"]
        loss = [r for r in log if r["truth"][0]>=2]
        ctrl = [r for r in log if r["truth"][0]<2]
        self.assertEqual((len(loss),len(ctrl)),(20,10))
        for method in ("zones","base"):
            def alarm(r):
                return bool(r["p"][method]) and (method=="base" or r["p"]["status"]=="ok")
            print(method,"miss",sum(not alarm(r) for r in loss),"false",sum(alarm(r) for r in ctrl))
        good = [r for r in loss if r["p"]["status"]=="ok"]
        hit = sum(r["p"]["zones"]==[r["truth"][0]-1] for r in good)
        errors = [abs(max(0,r["p"]["residual"][r["truth"][0]-2])-sum(r["truth"][1:])) for r in good]
        print("localized",hit,"/20; MAE mL",round(1000*sum(errors)/len(errors),2) if errors else None,"n",len(errors))

    def test_windows_and_pairs(self):
        raw = (ROOT/"examples/run_02.csv").read_text()
        lines = raw.splitlines()
        reset = lines.copy()
        reset[-1] = reset[-1].split(",")
        reset[-1][2] = "0.1"
        reset[-1] = ",".join(reset[-1])
        with self.assertRaisesRegex(ValueError,"Сброс"):
            volumes("\n".join(reset),"counter")
        with self.assertRaisesRegex(ValueError,"Переключение"):
            volumes(raw.replace("8,1,","8,0,"),"counter")
        interval = [lines[0]]
        for i in range(4,len(lines)):
            v = [float(a)-float(b) for a,b in zip(lines[i].split(",")[2:],lines[i-1].split(",")[2:])]
            interval.append(",".join([str(i-1),"1",*map(str,v)]))
        for a,b in zip(volumes("\n".join(interval),"interval"),volumes(raw,"counter")):
            self.assertAlmostEqual(a,b)
        d = dict(ba=2,bc=1,bw=.3,fa=1.7,fc=1,fw=.3)
        self.assertIn("+0.300",self.api("paired",**d)["message"])
        self.assertIn("несопоставимы",self.api("paired",**(d|{"fw":.2}))["message"])


if __name__=="__main__":
    unittest.main()
