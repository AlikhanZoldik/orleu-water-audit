import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer
import argparse
import json
import webbrowser
from lab import Lab
from journal import analyze, load_file
from balance import number

ROOT = Path(__file__).resolve().parent


def paired(d):
    before, after = [[number(d[p+k]) for k in ("a","c","w")] for p in ("b","f")]
    if any(a < c+w-1e-9 or c<=0 for a,c,w in (before,after)):
        raise ValueError("Проверьте баланс. Доставка должна быть положительной, а вход покрывать доставку и отбор.")
    why = []
    if before[1] != after[1]:
        why.append("получателю доставлены разные объёмы")
    if before[2] != after[2]:
        why.append("различается штатный отбор")
    if why:
        return {"message":"Опыты несопоставимы — " + " и ".join(why) + "."}
    delta = before[0]-after[0]
    return {"message":f"Забор до ремонта минус забор после ремонта = {delta:+.3f} л. "
            + ("Забор уменьшился." if delta>0 else "Уменьшения забора не наблюдалось.")}


class Handler(BaseHTTPRequestHandler):
    def reply(self, body, mime, code=200):
        self.send_response(code)
        self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        assets = {"/journal.js": ("journal.js","application/javascript; charset=utf-8"), "/journal.xlsx": ("examples/journal.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        if self.path in assets:
            file, mime = assets[self.path]
            self.reply((ROOT/file).read_bytes(),mime)
        elif self.path == "/":
            self.reply((ROOT/"index.html").read_bytes(),"text/html; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != origin[7:] or self.headers.get("Origin",origin)!=origin or self.headers.get_content_type()!="application/json":
            self.send_error(403)
            return
        try:
            size = int(self.headers["Content-Length"])
            if not 0<size<=32000000:
                raise ValueError("Допустимый размер запроса — до 32 МБ.")
            d = json.loads(self.rfile.read(size))
            op = self.path.removeprefix("/api/")
            actions = {"paired": paired, "journal-load": load_file, "journal-check": analyze}
            result = actions[op](d) if op in actions else self.server.lab.action(op,d)
            code = 200
        except (ValueError, KeyError, TypeError, csv.Error, IndexError) as e:
            result,code = {"error":str(e)},400
        self.reply(json.dumps(result).encode(),"application/json",code)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port",type=int,default=8765)
    ap.add_argument("--db",default=str(ROOT/"experiments.sqlite3"))
    ap.add_argument("--no-browser",action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1",args.port),Handler)
    server.lab = Lab(args.db)
    url = f"http://127.0.0.1:{server.server_port}"
    print(url,flush=True)
    if not args.no_browser:
        Timer(.35,webbrowser.open,args=(url,)).start()
    server.serve_forever()

