"""
logdata.py — чтение логов ArduPilot (.BIN) и превращение их в pandas DataFrame.

Это учебная заготовка: прочитайте код построчно и объясните себе каждую строку.
Задачи на улучшение (по мере прохождения недель):
  * добавить кэширование распарсенного лога (повторный парсинг одного файла не нужен);
  * добавить проверку единиц (углы: градусы или радианы? — проверить эмпирически);
  * научиться выгружать несколько сообщений в один DataFrame по времени (см. merge_asof).

Запуск:
    python src/logdata.py <лог.BIN> --list                 # какие записи есть в логе
    python src/logdata.py <лог.BIN> --msg BARO             # первые строки записи BARO
    python src/logdata.py <лог.BIN> --msg BARO --csv out.csv
    python src/logdata.py --demo                           # синтетические данные (если лога ещё нет)
"""

from __future__ import annotations

import argparse
import sys

import pandas as pd


# ---------------------------------------------------------------------------
# Чтение реального лога
# ---------------------------------------------------------------------------
def open_log(path: str):
    """Открыть .BIN лог ArduPilot. Возвращает объект-читалку pymavlink."""
    try:
        from pymavlink import mavutil
    except ImportError as exc:  # подсказка новичку
        raise SystemExit(
            "Нет pymavlink. Установите:  pip install pymavlink\n"
            "либо активируйте окружение:  source ~/projects/uavenv/bin/activate"
        ) from exc

    return mavutil.mavlink_connection(path)


def list_message_types(path: str, verbose: bool = True) -> dict[str, int]:
    """Сколько сообщений каждого типа в логе. Полезно, чтобы понять, что вообще есть."""
    log = open_log(path)
    counts: dict[str, int] = {}
    while True:
        msg = log.recv_match(blocking=False)
        if msg is None:
            break
        name = msg.get_type()
        counts[name] = counts.get(name, 0) + 1

    if verbose:
        if not counts:
            print("Сообщений не найдено. Это точно .BIN-лог ArduPilot?")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"{name:>10}  {n}")
    return counts


def read_message(path: str, msg_type: str, max_samples: int | None = None) -> pd.DataFrame:
    """
    Прочитать один тип сообщений в DataFrame.

    Возвращает колонки из сообщения + 't' (время в секундах от начала лога).
    Пример: read_message('00000001.BIN', 'BARO') -> колонки TimeUS, Alt, Press, Temp, t
    """
    log = open_log(path)
    rows: list[dict] = []
    while True:
        msg = log.recv_match(type=[msg_type], blocking=False)
        if msg is None:
            break
        d = msg.to_dict()
        d.pop("mavpackettype", None)
        rows.append(d)
        if max_samples is not None and len(rows) >= max_samples:
            break

    if not rows:
        raise SystemExit(
            f"В логе нет записей типа '{msg_type}'.\n"
            f"Посмотрите список доступных:  python src/logdata.py {path} --list"
        )

    df = pd.DataFrame(rows)

    # Единое время в секундах. TimeUS — микросекунды, начиная с запуска автопилота.
    if "TimeUS" in df.columns:
        df["t"] = df["TimeUS"].astype(float) / 1e6
        df = df.sort_values("t").reset_index(drop=True)
    elif "TimeMS" in df.columns:
        df["t"] = df["TimeMS"].astype(float) / 1e3
        df = df.sort_values("t").reset_index(drop=True)
    return df


def read_many(path: str, msg_types: list[str]) -> dict[str, pd.DataFrame]:
    """Прочитать сразу несколько типов сообщений одним проходом (быстрее, чем по одному)."""
    wanted = set(msg_types)
    log = open_log(path)
    buckets: dict[str, list[dict]] = {t: [] for t in msg_types}
    while True:
        msg = log.recv_match(type=list(wanted), blocking=False)
        if msg is None:
            break
        name = msg.get_type()
        d = msg.to_dict()
        d.pop("mavpackettype", None)
        buckets[name].append(d)

    out: dict[str, pd.DataFrame] = {}
    for name, rows in buckets.items():
        df = pd.DataFrame(rows)
        if not df.empty and "TimeUS" in df.columns:
            df["t"] = df["TimeUS"].astype(float) / 1e6
            df = df.sort_values("t").reset_index(drop=True)
        out[name] = df
    return out


# ---------------------------------------------------------------------------
# Синтетические данные — чтобы начать работу, пока SITL ещё не собран
# ---------------------------------------------------------------------------
def demo_dataframe(duration_s: float = 60.0, dt: float = 0.01, seed: int = 0) -> pd.DataFrame:
    """
    Имитация вертикального канала реального дрона — с ГРАВИТАЦИЕЙ и с дрейфом датчиков.

    Что заложено в модель (разберите каждую строку — это и есть половина задачи):
      * профиль: стоянка -> разгон вверх -> равномерный подъём -> торможение ->
        висение -> спуск -> торможение -> посадка;
      * акселерометр измеряет УДЕЛЬНУЮ СИЛУ, а не ускорение:
            f = a + g        (g = +9.81 м/с^2, ось направлена вверх)
        Поэтому в покое исправный акселерометр показывает ≈ +9.8 м/с^2.
        Чтобы получить ускорение движения, нужно вычесть g: а = f - g.
        В NED-координатах (как в ArduPilot) знак оси Z будет обратным — это
        классическая ловушка, из-за которой фильтр "улетает".
      * у акселерометра есть смещение (bias) и шум — интегрирование одного лишь
        акселерометра всегда даёт квадратично растущую ошибку;
      * барометр шумный и медленно дрейфует.

    Возвращает DataFrame с колонками:
        t, h_true, v_true, a_true, accel_meas (удельная сила), h_baro
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    G = 9.81
    n = int(duration_s / dt)
    t = np.arange(n) * dt

    # --- истинный профиль движения (ускорение по вертикали, м/с^2) ---
    def true_accel(tt: float) -> float:
        if tt < 5:
            return 0.0        # стоим на земле
        if tt < 8:
            return +1.0       # разгон вверх
        if tt < 18:
            return 0.0        # равномерный подъём
        if tt < 21:
            return -1.0       # торможение до висения
        if tt < 31:
            return 0.0        # висение
        if tt < 34:
            return -1.0       # начало спуска
        if tt < 44:
            return 0.0        # снижение с постоянной скоростью
        if tt < 47:
            return +1.0       # торможение перед посадкой
        return 0.0            # на земле

    a_true = np.array([true_accel(x) for x in t])
    v_true = np.cumsum(a_true) * dt
    h_true = np.cumsum(v_true) * dt
    h_true = np.clip(h_true, 0.0, None)      # ниже земли не бывает
    v_true[h_true <= 0.0] = 0.0

    # --- датчики ---
    acc_bias = 0.05                                  # смещение акселерометра, м/с^2
    accel_meas = a_true + G + acc_bias + rng.normal(0, 0.15, n)   # удельная сила
    baro_drift = 0.02 * t                            # медленный дрейф барометра, м
    baro_meas = h_true + baro_drift + rng.normal(0, 0.30, n)

    return pd.DataFrame(
        {
            "t": t,
            "h_true": h_true,
            "v_true": v_true,
            "a_true": a_true,
            "accel_meas": accel_meas,     # в покое ≈ +9.86; вычесть G (9.81) -> a
            "h_baro": baro_meas,
        }
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description="Чтение логов ArduPilot / синтетика для проекта kalman-lab")
    p.add_argument("path", nargs="?", help="путь к .BIN логу ArduPilot")
    p.add_argument("--list", action="store_true", help="показать типы сообщений и их количество")
    p.add_argument("--msg", help="тип сообщения для выгрузки, например BARO или ATT")
    p.add_argument("--csv", help="сохранить выбранное сообщение в CSV")
    p.add_argument("--demo", action="store_true", help="показать синтетический пример (лог не нужен)")
    args = p.parse_args()

    if args.demo:
        df = demo_dataframe()
        print(df.head(10).to_string(index=False))
        print(f"\nСтрок: {len(df)}. Колонки: {list(df.columns)}")
        return

    if not args.path:
        p.print_help()
        sys.exit(1)

    if args.list:
        list_message_types(args.path)
        return

    if args.msg:
        df = read_message(args.path, args.msg)
        print(df.head(10).to_string(index=False))
        print(f"\nСтрок: {len(df)}. Длительность: {df['t'].max():.1f} с")
        if args.csv:
            df.to_csv(args.csv, index=False)
            print(f"Сохранено в {args.csv}")
        return

    p.print_help()


if __name__ == "__main__":
    main()
