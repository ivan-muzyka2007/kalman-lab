"""
check_env.py — проверка окружения перед началом работы.

Запуск:
    source ~/projects/uavenv/bin/activate
    python src/check_env.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def ok(msg: str) -> None:
    print(f"  [ok]   {msg}")


def warn(msg: str) -> None:
    print(f"  [!]    {msg}")


def bad(msg: str) -> None:
    print(f"  [нет]  {msg}")


def main() -> None:
    print("\n=== Проверка окружения kalman-lab ===\n")

    # 1. Система
    print("Система:")
    print(f"  Python {sys.version.split()[0]}  ({platform.system()})")
    in_wsl = "microsoft" in platform.uname().release.lower() or "microsoft" in platform.version().lower()
    ok("WSL обнаружен — вы внутри Linux-подсистемы Windows") if in_wsl else warn(
        "Похоже, это не WSL. Если вы в Ubuntu-VM — это нормально."
    )
    home = Path.home()
    if str(home).startswith("/mnt/"):
        bad(f"Домашний каталог на Windows-диске: {home}. Проекты нужно держать в /home/<user> "
            f"(на /mnt/... сборка идёт в разы медленнее).")
    else:
        ok(f"Домашний каталог в Linux-файловой системе: {home}")

    # 2. Библиотеки Python
    print("\nБиблиотеки Python:")
    for mod in ("numpy", "scipy", "matplotlib", "pandas", "pymavlink"):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            ok(f"{mod} {ver}")
        except ImportError:
            bad(f"{mod} не установлен  ->  pip install {mod}")

    # 3. Инструменты
    print("\nИнструменты командной строки:")
    for tool in ("git", "g++", "cmake", "make", "python3"):
        path = shutil.which(tool)
        ok(f"{tool}: {path}") if path else bad(f"{tool} не найден  ->  sudo apt install {tool}")

    print("\nSITL / ArduPilot:")
    arp = Path.home() / "ardupilot"
    if arp.exists():
        ok(f"Репозиторий ArduPilot: {arp}")
        binary = arp / "build" / "sitl" / "bin" / "arducopter"
        ok("Сборка SITL найдена: build/sitl/bin/arducopter") if binary.exists() else warn(
            "SITL ещё не собран. Выполните:  cd ~/ardupilot && ./waf configure --board sitl && ./waf copter"
        )
    else:
        warn("Каталог ~/ardupilot не найден. Клонируйте репозиторий (см. план, часть C.4).")

    sim = shutil.which("sim_vehicle.py")
    ok(f"sim_vehicle.py: {sim}") if sim else warn(
        "sim_vehicle.py не найден в PATH. Откройте новый терминал, выполните '. ~/.profile' "
        "или перезапустите WSL (wsl --shutdown в PowerShell)."
    )

    # 4. Демо-прогон (проверяем, что numpy+pandas действительно работают вместе)
    print("\nПробный расчёт:")
    try:
        import numpy as np  # noqa: F401

        sys.path.insert(0, str(Path(__file__).parent))
        from logdata import demo_dataframe

        df = demo_dataframe(duration_s=10.0)
        print(f"  [ok]   синтетические данные: {len(df)} строк, колонки {list(df.columns)}")
    except Exception as exc:  # noqa: BLE001
        bad(f"демо-расчёт не удался: {exc}")

    # 5. git-настройки
    print("\ngit:")
    try:
        name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip()
        email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True).stdout.strip()
        ok(f"user.name = {name}") if name else warn('не настроено: git config --global user.name "Ваше Имя"')
        ok(f"user.email = {email}") if email else warn('не настроено: git config --global user.email "ваш@email"')
    except Exception:  # noqa: BLE001
        warn("не удалось проверить настройки git")

    print("\n=== Что дальше ===")
    print("  * нет лога?  ->  python src/plot_basic.py --demo --out figures/demo.png")
    print("  * есть лог?  ->  python src/logdata.py <лог.BIN> --list  (посмотреть записи)")
    print("  * запишите результат проверки в learn-log.md\n")


if __name__ == "__main__":
    main()
