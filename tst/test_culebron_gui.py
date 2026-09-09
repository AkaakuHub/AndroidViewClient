from unittest.mock import call, Mock, patch

import pytest

from com.dtmilano.android.culebra_gui import calculate_window_scale
from com.dtmilano.android.culebron import Culebron, Operation, Unit


def test_calculate_window_scale_fits_large_image_on_screen():
    scale = calculate_window_scale(1, (2280, 1080), (1920, 1200))

    assert scale == pytest.approx(1728 / 2280)


def test_calculate_window_scale_keeps_requested_scale_when_it_fits():
    assert calculate_window_scale(0.5, (2280, 1080), (1920, 1200)) == 0.5


@pytest.mark.parametrize("image_size,screen_size", [((0, 1080), (1920, 1200)), ((2280, 1080), (0, 1200))])
def test_calculate_window_scale_rejects_invalid_dimensions(image_size, screen_size):
    with pytest.raises(ValueError):
        calculate_window_scale(1, image_size, screen_size)


def test_toast_uses_tk_main_loop():
    culebron = object.__new__(Culebron)
    culebron.message = Mock()
    culebron.hideMessageArea = Mock()
    culebron.window = Mock()

    Culebron.toast(culebron, "Touching point", background="green", timeout=5)

    culebron.window.after.assert_called_once_with(5000, culebron.hideMessageArea)


def test_touch_point_refreshes_without_blocking_gui():
    culebron = object.__new__(Culebron)
    culebron.areEventsDisabled = False
    culebron.isTouchingPoint = True
    culebron.coordinatesUnit = Unit.DIP
    culebron.vc = Mock()
    culebron.vc.uiAutomatorHelper = None
    culebron.device = Mock()
    culebron.device.display = {"density": 2, "orientation": 1}
    culebron.printOperation = Mock()
    culebron.showVignette = Mock()
    culebron.sleep = Mock()
    culebron.refreshAfterDeviceAction = Mock()
    culebron.statusBar = Mock()

    with patch("com.dtmilano.android.culebron.time.sleep", side_effect=AssertionError("blocking sleep")):
        Culebron.touchPoint(culebron, 200, 100)

    culebron.vc.touch.assert_called_once_with(200, 100)
    culebron.printOperation.assert_any_call(None, Operation.TOUCH_POINT, 100.0, 50.0, Unit.DIP, 1)
    culebron.sleep.assert_called_once_with(5, do_actual_sleep_before=False)
    culebron.refreshAfterDeviceAction.assert_called_once_with()


def test_hide_vignette_hides_each_overlay_item():
    culebron = object.__new__(Culebron)
    culebron.canvas = Mock()
    culebron.vignetteId = 1
    culebron.waitMessageShadowId = 2
    culebron.waitMessageId = 3
    culebron.enableEvents = Mock()

    Culebron.hideVignette(culebron)

    culebron.canvas.itemconfigure.assert_has_calls([
        call(1, state='hidden'),
        call(2, state='hidden'),
        call(3, state='hidden'),
    ])
    culebron.enableEvents.assert_called_once_with()
