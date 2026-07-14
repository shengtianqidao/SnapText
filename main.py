import sys
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QIcon
from PyQt5.QtCore import Qt, QRect
from core.main_window import MainWindow

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")


def create_app_icon() -> QIcon:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icon = QIcon()
    for size in sizes:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)

        margin = size * 0.08
        radius = size * 0.18
        body_rect = QRect(
            int(margin), int(margin),
            int(size - 2 * margin), int(size - 2 * margin)
        )

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(30, 120, 255))
        p.drawRoundedRect(body_rect, int(radius), int(radius))

        cx = size * 0.42
        cy = size * 0.40
        r = size * 0.16
        pen_w = max(1, int(size * 0.055))
        p.setPen(QPen(QColor(255, 255, 255), pen_w))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(int(cx - r), int(cy - r), int(2 * r), int(2 * r))

        handle_x = cx + r * 0.7
        handle_y = cy + r * 0.7
        handle_len = size * 0.14
        angle = 0.785
        dx = handle_len * 0.707
        dy = handle_len * 0.707
        p.drawLine(
            int(handle_x), int(handle_y),
            int(handle_x + dx), int(handle_y + dy)
        )

        font_size = max(6, int(size * 0.22))
        font = QFont("Arial", font_size)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        text_rect = QRect(0, int(size * 0.62), size, int(size * 0.35))
        p.drawText(text_rect, Qt.AlignCenter, "T")

        p.end()
        icon.addPixmap(pixmap)

    return icon


def _hide_console():
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def main():
    _hide_console()
    app = QApplication(sys.argv)
    app.setApplicationName("SnapText")
    icon = create_app_icon()
    app.setWindowIcon(icon)
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()