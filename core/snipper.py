import logging
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen, QRegion
from PIL import ImageGrab

logger = logging.getLogger("Snipper")


class Snipper(QWidget):
    def __init__(self, main_window):
        super().__init__(None)
        self.main_window = main_window
        self.start_pos = QPoint()
        self.end_pos = QPoint()
        self.is_selecting = False
        self._init_ui()
        self._capture_screen()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        screen = QApplication.primaryScreen()
        self.setGeometry(screen.geometry())

    def _capture_screen(self):
        screen = QApplication.primaryScreen()
        geo = screen.geometry()
        self.screen_pixmap = screen.grabWindow(
            0, 0, 0, geo.width(), geo.height()
        )
        logger.info("Screen captured: %dx%d", geo.width(), geo.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.screen_pixmap)

        overlay_color = QColor(0, 0, 0, 100)

        if self.is_selecting:
            selection = self._normalized_rect()
            full_region = QRegion(self.rect())
            sel_region = QRegion(selection)
            overlay_region = full_region.subtracted(sel_region)

            painter.setClipRegion(overlay_region)
            painter.fillRect(self.rect(), overlay_color)
            painter.setClipping(False)

            pen = QPen(QColor(30, 120, 255), 2)
            painter.setPen(pen)
            painter.drawRect(selection)
        else:
            painter.fillRect(self.rect(), overlay_color)

    def _normalized_rect(self) -> QRect:
        return QRect(self.start_pos, self.end_pos).normalized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.is_selecting = True
        elif event.button() == Qt.RightButton:
            self._cancel()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.end_pos = event.pos()
            self.is_selecting = False
            selection = self._normalized_rect()
            if selection.width() > 5 and selection.height() > 5:
                self._finish(selection)
            else:
                self._cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._cancel()

    def _finish(self, rect: QRect):
        self.hide()
        screen_geo = QApplication.primaryScreen().geometry()
        offset = screen_geo.topLeft()
        abs_x = rect.x() + offset.x()
        abs_y = rect.y() + offset.y()

        img = ImageGrab.grab(bbox=(
            abs_x, abs_y,
            abs_x + rect.width(),
            abs_y + rect.height()
        ))

        logger.info("Region captured: %dx%d at (%d,%d)",
                     rect.width(), rect.height(), abs_x, abs_y)

        self.main_window.load_image(img)
        self.close()

    def _cancel(self):
        logger.info("Snipper cancelled")
        if self.main_window and hasattr(self.main_window, "on_snip_cancelled"):
            self.main_window.on_snip_cancelled()
        self.close()