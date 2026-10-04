"""
plot_basic.py — первые графики: углы, высота, ускорения.

Запуск:
    python src/plot_basic.py --demo --out figures/demo.png
    python src/plot_basic.py data/00000001.BIN --out figures/week3_basic.png

Что смотреть глазами (это и есть обучение):
  1. Совпадают ли высота барометра и высота по ГНСС? Где расходятся и почему?
  2. Есть ли дрейф барометра на стоянке (первые секунды)?
  3. Как выглядит AccZ в покое? (ожидание: около +9.8 м/с^2 либо -9.8 — проверьте знак!)
  4. Насколько шумнее барометр по сравнению со штатной оценкой фильтра (XKF1/NKF1)?
"""

from __future__ import annotations

import argparse
import os

import matplotlib

matplotlib.use("Agg")  # работа без графического окна: сохраняем в файл
import matplotlib.pyplot as plt  # noqa: E402


def try_ekf_frame(frames: dict):
    """Фильтр ArduPilot пишет оценку в XKF1 (или NKF1 в старых версиях)."""
    for key in ("XKF1", "NKF1", "XKF2", "NKF2"):
        if key in frames and not frames[key].empty:
            return key, frames[key]
    return None, None


def plot_from_log(path: str, out_path: str) -> None:
    from logdata import read_many

    frames = read_many(path, ["BARO", "GPS", "ATT", "IMU", "XKF1", "NKF1"])
    if not frames or all(df.empty for df in frames.values()):
        raise SystemExit("В логе не нашлось нужных записей (BARO/GPS/ATT/IMU/XKF1).")

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    # --- 1. Высота -----------------------------------------------------------
    ax = axes[0]
    baro = frames.get("BARO")
    if baro is not None and not baro.empty:
        alt_col = "Alt" if "Alt" in baro.columns else baro.columns[1]
        ax.plot(baro["t"], baro[alt_col], label="барометр", lw=1, alpha=0.8)
    gps = frames.get("GPS")
    if gps is not None and not gps.empty and "Alt" in gps.columns:
        ax.plot(gps["t"], gps["Alt"], label="ГНСС", lw=1, alpha=0.8)
    ekf_name, ekf = try_ekf_frame(frames)
    if ekf is not None:
        # ЛОВУШКА: система координат NED — "Down" положительна вниз,
        # поэтому высота = -PD. Путаница в знаках — самая частая ошибка новичка.
        for col, sign in (("PD", -1.0), ("Alt", 1.0)):
            if col in ekf.columns:
                ax.plot(ekf["t"], sign * ekf[col], label=f"оценка {ekf_name}.{col} (высота)", lw=1.2)
                break
    ax.set_ylabel("высота, м")
    ax.set_title("Высота: датчики против оценки фильтра")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # --- 2. Углы -------------------------------------------------------------
    ax = axes[1]
    att = frames.get("ATT")
    if att is not None and not att.empty:
        for col in ("Roll", "Pitch", "Yaw"):
            if col in att.columns:
                ax.plot(att["t"], att[col], label=col, lw=1)
    ax.set_ylabel("углы")
    ax.set_title("Ориентация (ATT)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    # --- 3. Вертикальное ускорение ------------------------------------------
    ax = axes[2]
    imu = frames.get("IMU")
    if imu is not None and not imu.empty:
        for col in imu.columns:
            if col.startswith("AccZ"):
                ax.plot(imu["t"], imu[col], label=col, lw=0.8)
    ax.set_xlabel("время, с")
    ax.set_ylabel("ускорение, м/с²")
    ax.set_title("Вертикальное ускорение (IMU)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Сохранено: {out_path}")


def plot_demo(out_path: str) -> None:
    """График по синтетике — можно сделать ещё до сборки SITL."""
    from logdata import demo_dataframe

    df = demo_dataframe()
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)

    axes[0].plot(df["t"], df["h_true"], label="истина", lw=1.5)
    axes[0].plot(df["t"], df["h_baro"], label="барометр (шум + дрейф)", lw=0.8, alpha=0.8)
    axes[0].set_ylabel("высота, м")
    axes[0].set_title("Синтетика: что видит фильтр и что есть на самом деле")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(fontsize=8)

    axes[1].plot(df["t"], df["a_true"], label="истинное ускорение движения", lw=1.2)
    axes[1].plot(df["t"], df["accel_meas"], label="акселерометр (в покое ≈ 9.8: гравитация!)", lw=0.6, alpha=0.7)
    axes[1].set_ylabel("ускорение, м/с²")
    axes[1].axhline(9.81, color="k", ls=":", lw=1, label="g = 9.81")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(fontsize=8)

    axes[2].plot(df["t"], df["v_true"], label="истинная скорость", lw=1.2)
    axes[2].set_xlabel("время, с")
    axes[2].set_ylabel("скорость, м/с")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(fontsize=8)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=120)
    print(f"Сохранено: {out_path}")
    print("Задания:")
    print("  1) Вычтите из accel_meas гравитацию (9.81) и дважды проинтегрируйте —")
    print("     найдите, через сколько секунд ошибка по высоте превысит 5 м.")
    print("     Это и есть причина, по которой нужен фильтр, а не чистая инерция.")
    print("  2) Оцените смещение акселерометра по участку стоянки (первые 5 с).")


def main() -> None:
    p = argparse.ArgumentParser(description="Первые графики из лога ArduPilot (или синтетики)")
    p.add_argument("path", nargs="?", help="путь к .BIN логу")
    p.add_argument("--out", default="figures/basic.png", help="куда сохранить PNG")
    p.add_argument("--demo", action="store_true", help="нарисовать синтетический пример")
    args = p.parse_args()

    if args.demo:
        plot_demo(args.out)
    elif args.path:
        plot_from_log(args.path, args.out)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
