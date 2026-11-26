"""Локальное хранилище. Контроль читается только на этапе раскрытия."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from random import SystemRandom
from balance import calibrate, diagnose, number, simulate, volumes

rng = SystemRandom()
KINDS = ["Нормальный поток", "Только штатный отбор", "Слив на участке 1", "Слив на участке 2"]


class Lab:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS series(id INTEGER PRIMARY KEY, source TEXT, limits TEXT, n INTEGER);
                CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, sid INTEGER, raw TEXT, mode TEXT,
                    forecast TEXT, opened INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS controls(rid INTEGER PRIMARY KEY, truth TEXT);
                CREATE TABLE IF NOT EXISTS deck(sid INTEGER, pos INTEGER, kind INTEGER, PRIMARY KEY(sid,pos));
            """)

    def action(self, op, d):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            if op == "state":
                return self.state(db, d.get("sid"))
            if op == "series":
                src = d["source"]
                if src not in ("sim","real"):
                    raise ValueError("Выберите источник.")
                runs = [simulate(0,rng)[0] for _ in range(16)] if src=="sim" else d["files"]
                limits = calibrate(runs,"counter" if src=="sim" else d["mode"])
                sid = db.execute("INSERT INTO series(source,limits,n) VALUES(?,?,?)",
                                 (src,json.dumps(limits),len(runs))).lastrowid
                if src=="sim":
                    deck = [0]*5+[1]*5+[2]*10+[3]*10
                    rng.shuffle(deck)
                    db.executemany("INSERT INTO deck VALUES(?,?,?)",[(sid,i,k) for i,k in enumerate(deck)])
                return self.state(db,sid)
            sid = int(d["sid"])
            series = db.execute("SELECT * FROM series WHERE id=?",(sid,)).fetchone()
            if not series:
                raise ValueError("Выберите серию.")
            current = db.execute("SELECT * FROM runs WHERE sid=? ORDER BY id DESC LIMIT 1",(sid,)).fetchone()
            if op == "load":
                if current and not current["opened"]:
                    raise ValueError("Завершите текущий опыт.")
                mode = d.get("mode","counter")
                truth = None
                if series["source"]=="sim":
                    idx = db.execute("SELECT count(*) FROM runs WHERE sid=?",(sid,)).fetchone()[0]
                    pick = db.execute("SELECT kind FROM deck WHERE sid=? AND pos=?",(sid,idx)).fetchone()
                    if not pick:
                        raise ValueError("Все 30 опытов завершены. Откройте новую серию.")
                    raw, truth = simulate(pick[0],rng)
                    mode = "counter"
                else:
                    raw = d["raw"]
                rid = db.execute("INSERT INTO runs(sid,raw,mode) VALUES(?,?,?)",(sid,raw,mode)).lastrowid
                if truth is not None:
                    db.execute("INSERT INTO controls VALUES(?,?)",(rid,json.dumps(truth)))
            elif current and current["id"] == d.get("rid"):
                rid = current["id"]
                if op=="predict" and not current["forecast"]:
                    pred = diagnose(current["raw"],current["mode"],json.loads(series["limits"]))
                    db.execute("UPDATE runs SET forecast=? WHERE id=?",(json.dumps(pred),rid))
                elif op=="reveal" and current["forecast"] and not current["opened"]:
                    if series["source"]=="real":
                        k = int(d["kind"])
                        x,y = number(d["x"]),number(d["y"])
                        if k not in range(4) or (x>0)!=(k==2) or (y>0)!=(k==3):
                            raise ValueError("Объёмы ёмкостей должны соответствовать выбранному сценарию.")
                        db.execute("INSERT INTO controls VALUES(?,?)",(rid,json.dumps([k,x,y])))
                    db.execute("UPDATE runs SET opened=1 WHERE id=?",(rid,))
                else:
                    raise ValueError("Этап уже завершён или прогноз ещё не сохранён.")
            else:
                raise ValueError("Обновите страницу и проверьте номер опыта.")
            return self.state(db,sid)

    def state(self, db, sid):
        catalog = [dict(r) for r in db.execute("SELECT id,source FROM series ORDER BY id DESC")]
        if not catalog:
            return dict(catalog=[])
        sid = int(sid or catalog[0]["id"])
        s = dict(db.execute("SELECT * FROM series WHERE id=?",(sid,)).fetchone())
        s["limits"] = json.loads(s["limits"])
        rows = db.execute("SELECT * FROM runs WHERE sid=? ORDER BY id",(sid,)).fetchall()
        log = []
        for r in rows:
            if r["opened"]:
                truth = json.loads(db.execute("SELECT truth FROM controls WHERE rid=?",(r["id"],)).fetchone()[0])
                log.append(dict(id=r["id"], p=json.loads(r["forecast"]), truth=truth))
        cur = None
        if rows:
            r = rows[-1]
            try:
                v = volumes(r["raw"],r["mode"])
            except ValueError:
                v = None
            cur = dict(id=r["id"],opened=r["opened"],volumes=v,p=json.loads(r["forecast"] or "null"))
        return dict(catalog=catalog, series=s, current=cur, log=log)
