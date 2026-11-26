"""Баланс за одно окно. Модуль получает только показания и пороги."""
import csv
import io
import math
import random

FIELDS = ["t_s", "stable", "A_L", "B_L", "C_L", "take_L"]
NAMES = ["Участок 1", "Участок 2", "A − C"]
WINDOW = 10


def number(value):
    n = float(value)
    if not math.isfinite(n) or n < 0:
        raise ValueError("Ожидалось конечное неотрицательное число.")
    return n


def volumes(raw, mode):
    if mode not in ("counter", "interval"):
        raise ValueError("Неизвестный тип показаний.")
    reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
    if reader.fieldnames != FIELDS:
        raise ValueError("Проверьте заголовок и порядок столбцов CSV.")
    window = []
    previous = None
    for line, row in enumerate(reader, 2):
        try:
            t = number(row["t_s"])
            if previous is not None and abs(t - previous - 1) > 1e-8:
                raise ValueError("Пропуск или нарушение шага времени 1 с.")
            previous = t
            if row["stable"] not in ("0", "1") or None in row:
                raise ValueError("Проверьте флаг stable и число полей.")
            if row["stable"] == "0":
                if window:
                    raise ValueError("Переключение внутри окна. Выделите новый устойчивый интервал.")
                continue
            values = [number(row[k]) for k in FIELDS[2:]]
            if mode == "counter" and window and any(a < b for a,b in zip(values, window[-1])):
                raise ValueError("Сброс счётчика в устойчивом интервале.")
            window.append(values)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Строка {line}. Некорректные данные. {exc}") from exc
    count = WINDOW + (mode == "counter")
    if len(window) != count:
        raise ValueError(f"Для окна 10 с требуется {count} последовательных устойчивых строк. Получено {len(window)}.")
    if mode == "counter":
        return [x-y for x,y in zip(window[-1], window[0])]
    return [sum(col) for col in zip(*window)]


def section_balance(inflow, outflow, withdrawals):
    return inflow - outflow - withdrawals


def residual(v):
    a,b,c,w = v
    return [round(section_balance(a,b,w), 9), round(section_balance(b,c,0), 9), round(a-c, 9)]


def calibrate(runs, mode):
    if len(runs) < 5:
        raise ValueError("Нужно минимум пять отдельных калибровочных прогонов.")
    samples = [residual(volumes(raw, mode)) for raw in runs]
    return [max(map(abs, col)) for col in zip(*samples)]


def diagnose(raw, mode, limits):
    try:
        v = volumes(raw, mode)
    except ValueError as e:
        return dict(status="invalid", reason=str(e), zones=[], base=None)
    r = residual(v)
    zones = [i+1 for i in range(2) if r[i] > limits[i]]
    uncertain = any(r[i] < -limits[i] for i in range(2))
    return dict(status="uncertain" if uncertain else "ok", volumes=v, residual=r,
                zones=zones, base=r[2] > limits[2], limits=limits)


def simulate(kind, rng):
    # Контроль имитирует объём в ёмкости, показания — независимые измерительные каналы.
    take = 0 if kind == 0 else rng.uniform(.22,.40)
    spill = rng.uniform(.13,.32) if kind >= 2 else 0
    a = rng.uniform(2.0, 2.6)
    b = a-take-(spill if kind == 2 else 0)
    c = b-(spill if kind == 3 else 0)
    measured = [max(0,x+rng.uniform(-.018,.018)) for x in [a,b,c,take]]
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(FIELDS)
    for t in range(13):
        w.writerow([t,int(t>=2)]+[f"{10+x*t/10:.6f}" for x in measured])
    return out.getvalue(), [kind, spill if kind == 2 else 0, spill if kind == 3 else 0]

