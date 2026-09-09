MAX_WINDOW_SCREEN_RATIO = 0.9


def calculate_window_scale(requested_scale, image_size, screen_size):
    image_width, image_height = image_size
    screen_width, screen_height = screen_size
    if requested_scale <= 0:
        raise ValueError("requested_scale must be greater than zero")
    if min(image_width, image_height, screen_width, screen_height) <= 0:
        raise ValueError("image and screen dimensions must be greater than zero")

    width_scale = screen_width * MAX_WINDOW_SCREEN_RATIO / image_width
    height_scale = screen_height * MAX_WINDOW_SCREEN_RATIO / image_height
    return min(requested_scale, width_scale, height_scale)
