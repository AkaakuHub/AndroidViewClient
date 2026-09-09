from com.dtmilano.android.device_event_recorder import (
    Gesture,
    TouchDevice,
    TouchEventParser,
    build_replay_actions,
    describe_gesture,
    find_active_touch_device,
    render_replay_script,
    transform_touch_position,
)


DEVICE = TouchDevice(
    path="/dev/input/event1",
    raw_width=32768,
    raw_height=32768,
    surface_width=1080,
    surface_height=2280,
    orientation=1,
)


def test_find_active_touch_device():
    dumpsys = """    1: virtio_input_multi_touch_1
      Path: /dev/input/event1
      Enabled: true
Input Reader State:
  Device 5: virtio_input_multi_touch_1
    Touch Input Mapper (mode - direct):
      Raw Touch Axes:
        X: min=0, max=32767
        Y: min=0, max=32767
      Viewport INTERNAL: isActive=[1]
      RawSurfaceWidth: 1080px
      RawSurfaceHeight: 2280px
      SurfaceOrientation: 1
"""

    assert find_active_touch_device(dumpsys) == DEVICE


def test_transform_touch_position_for_landscape_rotation():
    assert transform_touch_position(0, 0, DEVICE) == (2279, 0)
    assert transform_touch_position(32767, 32767, DEVICE) == (0, 1079)


def test_touch_event_parser_builds_gesture():
    parser = TouchEventParser(DEVICE)
    lines = [
        "[ 10.000000] EV_ABS ABS_MT_TRACKING_ID 00000001",
        "[ 10.000100] EV_ABS ABS_MT_POSITION_X 00000000",
        "[ 10.000200] EV_ABS ABS_MT_POSITION_Y 00000000",
        "[ 10.000300] EV_SYN SYN_REPORT 00000000",
        "[ 10.100000] EV_ABS ABS_MT_POSITION_X 00007fff",
        "[ 10.100100] EV_ABS ABS_MT_POSITION_Y 00007fff",
        "[ 10.200000] EV_ABS ABS_MT_TRACKING_ID ffffffff",
        "[ 10.200100] EV_SYN SYN_REPORT 00000000",
    ]

    gestures = [gesture for line in lines if (gesture := parser.feed(line))]

    assert gestures == [Gesture(10.0, 10.2001, (2279, 0), (0, 1079))]


def test_build_replay_actions_preserves_start_timing_and_gestures():
    gestures = [
        Gesture(10.0, 10.1, (100, 200), (105, 205)),
        Gesture(11.0, 11.8, (300, 400), (500, 600)),
    ]

    assert build_replay_actions(gestures) == [
        (0, "tap", 100, 200),
        (1.0, "swipe", 300, 400, 500, 600, 800),
    ]


def test_describe_gesture():
    assert describe_gesture(1, Gesture(10.0, 10.1, (100, 200), (105, 205))) == "記録1: タップ(100, 200)"
    assert describe_gesture(2, Gesture(10.0, 10.8, (100, 200), (105, 205))) == "記録2: 長押し(100, 200)・800ms"
    assert describe_gesture(3, Gesture(10.0, 10.8, (100, 200), (500, 600))) == (
        "記録3: スワイプ(100, 200)→(500, 600)・800ms"
    )


def test_render_replay_script_is_valid_python():
    source = render_replay_script([(0, "tap", 100, 200)])

    compile(source, "recording.py", "exec")
    assert 'print(f"再生開始: {action_count}操作", flush=True)' in source
    assert "タップ x={values[0]}, y={values[1]}" in source
    assert "スワイプ ({values[0]}, {values[1]})→({values[2]}, {values[3]})・{values[4]}ms" in source
    assert 'print(f"再生完了: {action_count}操作", flush=True)' in source
