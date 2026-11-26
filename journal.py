"""Импорт журналов смен и проверка баланса в м³."""
import base64
import csv
import io
import re
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile, BadZipFile

from balance import section_balance

ROOT = Path(__file__).resolve().parent
sys.path.extend(str(path) for path in (ROOT/"vendor").glob("*.whl"))
from openpyxl import load_workbook

RATE = "Интегрируйте расход по времени за общий период: м³/с × секунды для каждого интервала, затем сложите объёмы."
COUNTER = "Вычтите начальное показание из конечного за одну смену, предварительно проверив сбросы счётчика."
LABELS = {"ab":"A–B", "bc":"B–C", "ac":"A–C"}


def load_file(data):
    raw = base64.b64decode(data["content"], validate=True)
    extension = Path(data["name"]).suffix.lower()
    if extension == ".xlsx":
        try:
            with ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist()) > 64_000_000:
                    raise ValueError("Распакованная книга превышает 64 МБ.")
            book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            try:
                names = [s.title for s in book.worksheets]
                sheet = data.get("sheet") or names[0]
                ws = book[sheet]
                ws.reset_dimensions()
                rows = extract(enumerate(ws.values,1))
            finally:
                book.close()
        except (BadZipFile, KeyError, IndexError, OSError) as e:
            raise ValueError("Не удалось прочитать книгу Excel.") from e
    elif extension == ".csv":
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251")
        first = next((line for line in text.splitlines() if line.strip()), "")
        try:
            sep = csv.Sniffer().sniff(text[:65536], delimiters=";,\t").delimiter
        except csv.Error:
            sep = ";" if ";" in first else ","
        reader = csv.reader(io.StringIO(text), delimiter=sep, strict=True)
        def records():
            for row in reader:
                yield reader.line_num,row
        rows = extract(records())
        names, sheet = [], ""
    else:
        raise ValueError("Выберите файл .xlsx или .csv.")
    return dict(sheets=names,sheet=sheet,**rows)


def extract(records):
    headers = None
    rows = []
    for line, record in records:
        cells = ["" if x is None else str(x).strip() for x in record]
        while cells and not cells[-1]:
            cells.pop()
        if not cells:
            continue
        if len(cells)>256 or len(rows)>=20000:
            raise ValueError("Для одной проверки выберите до 20 000 строк и 256 столбцов.")
        if headers is None:
            headers = [h or f"Столбец {i+1}" for i,h in enumerate(cells)]
        else:
            if len(cells)>len(headers):
                raise ValueError(f"Строка {line}: значений больше, чем заголовков.")
            rows.append([line,cells+[""]*(len(headers)-len(cells))])
    if not headers or not rows:
        raise ValueError("Нужны строка заголовков и хотя бы одна строка измерений.")
    return dict(headers=headers,rows=rows)


def volume(value, header, unit):
    if not value.strip():
        raise ValueError(f"«{header}»: пустая ячейка.")
    context = (header+" "+value).lower().replace("³","3").replace("^3","3")
    if re.search(r"(?:м3|m3|л|l)\s*/\s*(?:сек(?:унд[аыу]?)?|с|s|ч(?:ас)?|h|мин(?:ут[аыу]?)?)(?!\w)|мгновенн\w* расход",context):
        raise ValueError(f"«{header}»: указан расход. "+RATE)
    if re.search(r"накопительн|показани[ея] сч[её]тчика",context):
        raise ValueError(f"«{header}»: показания счётчика. "+COUNTER)
    if re.search(r"(?<!\w)(?:мл|ml|м2|кг|тонн(?:ы)?|тыс\.?\s*м3|млн\.?\s*м3)(?!\w)",context):
        raise ValueError(f"«{header}»: приведите единицы к литрам или м³.")
    declared = re.findall(r"(?<!\w)(м3|m3|л|литр(?:ы|ов)?)(?!\w)",context)
    if any(("m3" if x in ("m3","м3") else "l")!=unit for x in declared):
        raise ValueError(f"«{header}»: единицы несовместимы с выбранными для журнала.")
    val = re.sub(r"\s*(?:м³|м3|m3|л)$","",value.strip(),flags=re.I)
    val = val.replace("\xa0"," ").replace("\u202f"," ")
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?: \d{3})+)(?:[.,]\d+)?",val) or len(val)>28:
        raise ValueError(f"«{header}»: проверьте число и единицы.")
    return Decimal(val.replace(" ","").replace(",","."))/(1000 if unit=="l" else 1)


def display(n):
    return format(n,"f").rstrip("0").rstrip(".") if "." in format(n,"f") else str(n)


def analyze(d):
    headers,rows,m = d["headers"],d["rows"],d["mapping"]
    if m["kind"]!="volume":
        raise ValueError(RATE if m["kind"]=="rate" else COUNTER)
    unit = m["unit"]
    if unit not in ("l","m3"):
        raise ValueError("Выберите единицы.")
    points = m["points"]
    segments = [("ab","a","b"),("bc","b","c")] if points["b"] is not None else [("ac","a","c")]
    cols = [points[k] for k in ("period","a","c")]
    if points["b"] is not None:
        cols.append(points["b"])
    for zone,_,_ in segments:
        take = m["takes"][zone]
        if not take["columns"] and not take["none"]:
            raise ValueError(f"{LABELS[zone]}: выберите отборы или явно укажите, что их не было.")
        if take["columns"] and take["none"]:
            raise ValueError("Проверьте выбор отборов.")
        cols.extend(take["columns"])
    if any(type(i)!=int or not 0<=i<len(headers) for i in cols) or len(cols)!=len(set(cols)):
        raise ValueError("Выберите разные столбцы для периода, замеров и отборов.")
    periods = defaultdict(list)
    for line,cells in rows:
        periods[cells[points["period"]].strip()].append(line)
    results,over,unclear = [],set(),set()
    for line,cells in rows:
        period = cells[points["period"]].strip()
        key = period or ("?",line)
        for zone,start,end in segments:
            ids = [points[start],points[end],*m["takes"][zone]["columns"]]
            audit = [f"{headers[i]} [{i+1}] = {cells[i] or 'пусто'}" for i in ids]
            if len(ids)==2:
                audit.append("Отборов не было (указано пользователем)")
            residual,limit,formula = None,None,""
            spec = m["limits"][zone]
            lim_col = spec["column"]
            raw_limit = spec["value"] if lim_col is None else cells[lim_col]
            audit.append("Допуск ("+("ввод" if lim_col is None else headers[lim_col])+"): "+(raw_limit or "не указан"))
            try:
                if not period:
                    raise ValueError("Не указан период.")
                if len(periods[period])>1:
                    raise ValueError("Дубликат смены в строках "+", ".join(map(str,periods[period]))+".")
                unit_col = m.get("unitColumn")
                if unit_col is not None:
                    actual = cells[unit_col].strip().lower()
                    accepted = {"m3": ("м³","м3","м^3","m³","m3"), "l": ("л","l","литры","литров")}
                    if actual not in accepted[unit]:
                        raise ValueError(f"«{headers[unit_col]}»: единицы строки ({actual or 'пусто'}) несовместимы с выбранными.")
                vals = [volume(cells[i],headers[i],unit) for i in ids]
                residual = section_balance(vals[0],vals[1],sum(vals[2:]))
                formula = " − ".join(display(v) for v in (vals if len(vals)>2 else vals+[Decimal(0)]))+" = "+display(residual)+" м³"
                if raw_limit.strip():
                    limit = volume(raw_limit, "Допуск" if lim_col is None else headers[lim_col],unit)
                status = ("Допуск не указан" if limit is None else
                          "Превышен допуск" if abs(residual)>limit else "В пределах допуска")
                why = ("Положительный остаток — необъяснённое расхождение. Проверьте полноту записей об отборах."
                       if residual>0 else "Проверьте возможный приток, границы периодов и записи замеров."
                       if residual<0 else "Вход, выход и зарегистрированные отборы сходятся.")
            except ValueError as exc:
                status,why = "Уточнить данные",str(exc)
            if status=="Превышен допуск":
                over.add(key)
            if status in ("Допуск не указан","Уточнить данные"):
                unclear.add(key)
            results.append(dict(line=line,period=period,zone=LABELS[zone],status=status,
                                residual=display(residual) if residual is not None else "",
                                limit=display(limit) if limit is not None else "",
                                formula=formula,why=why,audit=audit))
    return dict(results=results,checked=sum(bool(k) for k in periods),over=len(over),unclear=len(unclear))


