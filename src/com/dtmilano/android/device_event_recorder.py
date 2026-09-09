import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import re
import subprocess
import sys
import threading


@dataclass(frozen=True)
class TouchDevice:
    path: str
    raw_width: int
    raw_height: int
    surface_width: int
    surface_height: int
    orientation: int


@dataclass(frozen=True)
class Gesture:
    started_at: float
    ended_at: float
    start: tuple[int, int]
    end: tuple[int, int]

    @property
    def duration_ms(self):
        return max(1, round((self.ended_at - self.started_at) * 1000))

    @property
    def distance(self):
        return math.dist(self.start, self.end)


def find_active_touch_device(dumpsys_input):
    inventory, reader_state = dumpsys_input.split("Input Reader State:", 1)
    paths = {}
    inventory_pattern = re.compile(
        r"^    \d+: (?P<name>.+?)\n(?P<body>.*?)(?=^    \d+: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in inventory_pattern.finditer(inventory):
        path = re.search(r"^      Path: (?P<path>/dev/input/event\d+)$", match.group("body"), re.MULTILINE)
        if path:
            name = match.group("name").split(" (aka ", 1)[0]
            paths[name] = path.group("path")

    device_pattern = re.compile(
        r"^  Device \d+: (?P<name>.+?)\n(?P<body>.*?)(?=^  Device \d+: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    for match in device_pattern.finditer(reader_state):
        body = match.group("body")
        if "Touch Input Mapper (mode - direct)" not in body or "isActive=[1]" not in body:
            continue
        raw_axes = re.search(
            r"Raw Touch Axes:.*?X: min=\d+, max=(\d+).*?Y: min=\d+, max=(\d+)",
            body,
            re.DOTALL,
        )
        surface = re.search(
            r"RawSurfaceWidth: (\d+)px.*?RawSurfaceHeight: (\d+)px.*?SurfaceOrientation: (\d+)",
            body,
            re.DOTALL,
        )
        path = paths.get(match.group("name"))
        if path and raw_axes and surface:
            return TouchDevice(
                path=path,
                raw_width=int(raw_axes.group(1)) + 1,
                raw_height=int(raw_axes.group(2)) + 1,
                surface_width=int(surface.group(1)),
                surface_height=int(surface.group(2)),
                orientation=int(surface.group(3)),
            )
    raise RuntimeError("使用中のタッチ入力デバイスを特定できません")


def transform_touch_position(raw_x, raw_y, device):
    portrait_x = round(raw_x * (device.surface_width - 1) / (device.raw_width - 1))
    portrait_y = round(raw_y * (device.surface_height - 1) / (device.raw_height - 1))
    if device.orientation == 0:
        return portrait_x, portrait_y
    if device.orientation == 1:
        return device.surface_height - 1 - portrait_y, portrait_x
    if device.orientation == 2:
        return device.surface_width - 1 - portrait_x, device.surface_height - 1 - portrait_y
    if device.orientation == 3:
        return portrait_y, device.surface_width - 1 - portrait_x
    raise ValueError(f"未対応の画面方向です: {device.orientation}")


class TouchEventParser:
    EVENT_PATTERN = re.compile(
        r"\[\s*(?P<timestamp>\d+\.\d+)\]\s+"
        r"(?:/dev/input/event\d+:\s+)?"
        r"(?P<event_type>EV_\w+)\s+(?P<code>\w+)\s+(?P<value>[0-9a-fA-F]+)"
    )

    def __init__(self, device):
        self.device = device
        self.active = False
        self.pending_end = False
        self.started_at = None
        self.raw_x = None
        self.raw_y = None
        self.start = None

    def feed(self, line):
        match = self.EVENT_PATTERN.search(line)
        if not match:
            return None
        timestamp = float(match.group("timestamp"))
        event_type = match.group("event_type")
        code = match.group("code")
        value = int(match.group("value"), 16)

        if event_type == "EV_ABS" and code == "ABS_MT_TRACKING_ID":
            if value == 0xFFFFFFFF:
                self.pending_end = self.active
            else:
                self.active = True
                self.pending_end = False
                self.started_at = timestamp
                self.raw_x = None
                self.raw_y = None
                self.start = None
            return None
        if event_type == "EV_ABS" and code == "ABS_MT_POSITION_X":
            self.raw_x = value
            return None
        if event_type == "EV_ABS" and code == "ABS_MT_POSITION_Y":
            self.raw_y = value
            return None
        if event_type != "EV_SYN" or code != "SYN_REPORT":
            return None
        if self.active and self.start is None and self.raw_x is not None and self.raw_y is not None:
            self.start = transform_touch_position(self.raw_x, self.raw_y, self.device)
        if not self.pending_end or self.start is None or self.raw_x is None or self.raw_y is None:
            return None

        gesture = Gesture(
            started_at=self.started_at,
            ended_at=timestamp,
            start=self.start,
            end=transform_touch_position(self.raw_x, self.raw_y, self.device),
        )
        self.active = False
        self.pending_end = False
        self.started_at = None
        self.start = None
        return gesture


def build_replay_actions(gestures):
    actions = []
    previous_end = None
    for gesture in gestures:
        delay = 0 if previous_end is None else max(0, gesture.started_at - previous_end)
        if gesture.distance <= 20 and gesture.duration_ms < 500:
            actions.append((delay, "tap", *gesture.start))
        else:
            actions.append((delay, "swipe", *gesture.start, *gesture.end, gesture.duration_ms))
        previous_end = gesture.ended_at
    return actions


def render_replay_script(actions):
    return f'''#!/usr/bin/env python3
import argparse
import subprocess
import time

ACTIONS = {actions!r}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--serial")
    args = parser.parse_args()
    adb = ["adb"]
    if args.serial:
        adb.extend(["-s", args.serial])
    for action in ACTIONS:
        delay, kind, *values = action
        time.sleep(delay)
        if kind == "tap":
            command = ["input", "tap", *(str(value) for value in values)]
        else:
            command = ["input", "swipe", *(str(value) for value in values)]
        subprocess.run([*adb, "shell", *command], check=True)


if __name__ == "__main__":
    main()
'''


def adb_command(serial, *arguments):
    command = ["adb"]
    if serial:
        command.extend(["-s", serial])
    command.extend(arguments)
    return command


def record(output, serial=None):
    dumpsys = subprocess.run(
        adb_command(serial, "shell", "dumpsys", "input"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    device = find_active_touch_device(dumpsys)
    command = adb_command(serial, "exec-out", "su", "0", "getevent", "-lt", device.path)
    parser = TouchEventParser(device)
    gestures = []
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def collect_gestures():
        for line in process.stdout:
            gesture = parser.feed(line)
            if gesture:
                gestures.append(gesture)
                print(f"記録済み: {len(gestures)}操作", file=sys.stderr)

    reader = threading.Thread(target=collect_gestures)
    reader.start()
    print(f"記録を開始しました。エミュレーターを直接操作してください: {device.path}", file=sys.stderr)
    print("終了して保存するにはEnterを押してください。", file=sys.stderr)
    try:
        input()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait()
        reader.join()

    output.write_text(render_replay_script(build_replay_actions(gestures)))
    output.chmod(output.stat().st_mode | 0o100)
    print(f"{len(gestures)}操作を{output}へ保存しました。", file=sys.stderr)


def main():
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("output", type=Path)
    argument_parser.add_argument("-s", "--serial")
    arguments = argument_parser.parse_args()
    record(arguments.output, arguments.serial)


if __name__ == "__main__":
    main()
