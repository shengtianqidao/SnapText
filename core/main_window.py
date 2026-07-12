import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTextEdit, QSplitter, QButtonGroup,
    QColorDialog, QSpinBox, QLabel, QListWidget, QListWidgetItem,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QRect, QPoint, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap, QFont
from PyQt5.QtWidgets import QApplication
from core.snipper import Snipper
from core.ocr_worker import OCRWorker
from utils.clipboard import copy_text_to_clipboard, copy_pixmap_to_clipboard
from utils.image_utils import pil_to_qpixmap, qpixmap_to_numpy

logger = logging.getLogger("MainWindow")

TOOL_PEN = "pen"
TOOL_ERASER = "eraser"
TOOL_MOSAIC = "mosaic"


class Stroke:
    def __init__(self, color=QColor(255, 0, 0), width=3):
        self.points = []
        self.color = color
        self.width = width


class MosaicRect:
    def __init__(self, rect: QRect, block_size=10):
        self.rect = rect
        self.block_size = block_size


class Canvas(QWidget):
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self.strokes = []
        self.mosaic_rects = []
        self.current_stroke = None
        self.current_tool = TOOL_PEN
        self.pen_color = QColor(255, 0, 0)
        self.pen_width = 3
        self.eraser_radius = 15
        self.mosaic_start = QPoint()
        self.mosaic_current = QPoint()
        self.is_drawing = False
        self.display_scale = 1.0
        self.display_offset = QPoint(0, 0)
        self.display_size = QSize(0, 0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setMinimumSize(100, 100)

    def _recalc_scale(self):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        padding = 10
        avail_w = w - 2 * padding
        avail_h = h - 2 * padding
        if avail_w <= 0 or avail_h <= 0:
            return
        scale = min(
            avail_w / max(self.original_pixmap.width(), 1),
            avail_h / max(self.original_pixmap.height(), 1),
            1.0
        )
        self.display_scale = scale
        self.display_size = QSize(
            int(self.original_pixmap.width() * scale),
            int(self.original_pixmap.height() * scale)
        )
        self.display_offset = QPoint(
            (w - self.display_size.width()) // 2,
            (h - self.display_size.height()) // 2
        )

    def resizeEvent(self, event):
        self._recalc_scale()
        self.update()

    def _to_image_pos(self, pos: QPoint) -> QPoint:
        local = pos - self.display_offset
        return QPoint(
            int(local.x() / self.display_scale),
            int(local.y() / self.display_scale)
        )

    def _to_display_pos(self, pos: QPoint) -> QPoint:
        return QPoint(
            int(pos.x() * self.display_scale) + self.display_offset.x(),
            int(pos.y() * self.display_scale) + self.display_offset.y()
        )

    def paintEvent(self, event):
        self._recalc_scale()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(45, 45, 45))
        painter.drawPixmap(
            self.display_offset.x(), self.display_offset.y(),
            self.display_size.width(), self.display_size.height(),
            self.original_pixmap
        )
        for mr in self.mosaic_rects:
            self._draw_mosaic_visual(painter, mr)
        if self.current_tool == TOOL_MOSAIC and self.is_drawing:
            img_rect = QRect(self.mosaic_start, self.mosaic_current).normalized()
            display_rect = QRect(
                self._to_display_pos(img_rect.topLeft()),
                self._to_display_pos(img_rect.bottomRight())
            )
            painter.setPen(QPen(QColor(0, 0, 0, 128), 1, Qt.DashLine))
            painter.setBrush(QColor(128, 128, 128, 60))
            painter.drawRect(display_rect)
        for stroke in self.strokes:
            self._draw_stroke(painter, stroke)
        if self.current_stroke and len(self.current_stroke.points) > 1:
            self._draw_stroke(painter, self.current_stroke)

    def _draw_stroke(self, painter: QPainter, stroke: Stroke):
        if len(stroke.points) < 2:
            return
        pen = QPen(stroke.color, max(1, stroke.width * self.display_scale))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for i in range(1, len(stroke.points)):
            p1 = self._to_display_pos(stroke.points[i - 1])
            p2 = self._to_display_pos(stroke.points[i])
            painter.drawLine(p1, p2)

    def _draw_mosaic_visual(self, painter: QPainter, mr: MosaicRect):
        img_rect = mr.rect
        display_rect = QRect(
            self._to_display_pos(img_rect.topLeft()),
            self._to_display_pos(img_rect.bottomRight())
        )
        block_size = mr.block_size
        scaled_block = max(2, int(block_size * self.display_scale))
        sub_pix = self.original_pixmap.copy(img_rect)
        sub_img = sub_pix.toImage()
        for y in range(0, display_rect.height(), scaled_block):
            for x in range(0, display_rect.width(), scaled_block):
                src_x = min(int(x / self.display_scale + block_size / 2),
                            sub_img.width() - 1)
                src_y = min(int(y / self.display_scale + block_size / 2),
                            sub_img.height() - 1)
                color = sub_img.pixelColor(src_x, src_y)
                painter.fillRect(
                    display_rect.x() + x, display_rect.y() + y,
                    scaled_block, scaled_block, color
                )

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        img_pos = self._to_image_pos(event.pos())
        self.is_drawing = True
        if self.current_tool == TOOL_PEN:
            self.current_stroke = Stroke(self.pen_color, self.pen_width)
            self.current_stroke.points.append(img_pos)
        elif self.current_tool == TOOL_ERASER:
            self._erase_at(img_pos)
        elif self.current_tool == TOOL_MOSAIC:
            self.mosaic_start = img_pos
            self.mosaic_current = img_pos

    def mouseMoveEvent(self, event):
        if not self.is_drawing:
            return
        img_pos = self._to_image_pos(event.pos())
        if self.current_tool == TOOL_PEN and self.current_stroke:
            self.current_stroke.points.append(img_pos)
            self.update()
        elif self.current_tool == TOOL_ERASER:
            self._erase_at(img_pos)
        elif self.current_tool == TOOL_MOSAIC:
            self.mosaic_current = img_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        img_pos = self._to_image_pos(event.pos())
        if self.current_tool == TOOL_PEN and self.current_stroke:
            self.current_stroke.points.append(img_pos)
            self.strokes.append(self.current_stroke)
            self.current_stroke = None
        elif self.current_tool == TOOL_MOSAIC:
            rect = QRect(self.mosaic_start, img_pos).normalized()
            if rect.width() > 3 and rect.height() > 3:
                self.mosaic_rects.append(MosaicRect(rect))
        self.is_drawing = False
        self.update()

    def _erase_at(self, pos: QPoint):
        radius = self.eraser_radius
        stroke_to_remove = []
        for i, stroke in enumerate(self.strokes):
            for pt in stroke.points:
                dx = pt.x() - pos.x()
                dy = pt.y() - pos.y()
                if dx * dx + dy * dy <= radius * radius:
                    stroke_to_remove.append(i)
                    break
        for i in reversed(stroke_to_remove):
            self.strokes.pop(i)
        mosaic_to_remove = []
        for i, mr in enumerate(self.mosaic_rects):
            if mr.rect.contains(pos):
                mosaic_to_remove.append(i)
        for i in reversed(mosaic_to_remove):
            self.mosaic_rects.pop(i)
        if stroke_to_remove or mosaic_to_remove:
            self.update()

    def get_merged_pixmap(self) -> QPixmap:
        result = QPixmap(self.original_pixmap.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, self.original_pixmap)
        for mr in self.mosaic_rects:
            self._apply_mosaic_to_painter(painter, mr)
        for stroke in self.strokes:
            if len(stroke.points) < 2:
                continue
            pen = QPen(stroke.color, stroke.width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            for i in range(1, len(stroke.points)):
                painter.drawLine(stroke.points[i - 1], stroke.points[i])
        painter.end()
        return result

    def _apply_mosaic_to_painter(self, painter: QPainter, mr: MosaicRect):
        block_size = mr.block_size
        sub_img = self.original_pixmap.copy(mr.rect).toImage()
        for y in range(0, mr.rect.height(), block_size):
            for x in range(0, mr.rect.width(), block_size):
                src_x = min(x + block_size // 2, sub_img.width() - 1)
                src_y = min(y + block_size // 2, sub_img.height() - 1)
                color = sub_img.pixelColor(src_x, src_y)
                bw = min(block_size, mr.rect.width() - x)
                bh = min(block_size, mr.rect.height() - y)
                painter.fillRect(mr.rect.x() + x, mr.rect.y() + y, bw, bh, color)

    def set_tool(self, tool: str):
        self.current_tool = tool
        if tool == TOOL_ERASER:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.CrossCursor)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.snipper = None
        self.ocr_worker = None
        self.canvas = None
        self.history = []
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("SnapText")
        self.resize(1100, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.btn_snip = QPushButton("Start Snip")
        self.btn_snip.setFixedSize(120, 34)
        self.btn_snip.clicked.connect(self._start_snip)

        sep1 = QLabel("|")
        sep1.setFixedWidth(10)
        sep1.setAlignment(Qt.AlignCenter)

        self.btn_pen = QPushButton("Pen")
        self.btn_pen.setCheckable(True)
        self.btn_pen.setChecked(True)
        self.btn_pen.setFixedSize(70, 34)

        self.btn_eraser = QPushButton("Eraser")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.setFixedSize(70, 34)

        self.btn_mosaic = QPushButton("Mosaic")
        self.btn_mosaic.setCheckable(True)
        self.btn_mosaic.setFixedSize(70, 34)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.btn_pen, 0)
        self.tool_group.addButton(self.btn_eraser, 1)
        self.tool_group.addButton(self.btn_mosaic, 2)

        self.btn_color = QPushButton("Color")
        self.btn_color.setFixedSize(70, 34)
        self._update_color_btn()

        width_label = QLabel("W:")
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 20)
        self.spin_width.setValue(3)
        self.spin_width.setFixedWidth(55)

        toolbar.addWidget(self.btn_snip)
        toolbar.addWidget(sep1)
        toolbar.addWidget(self.btn_pen)
        toolbar.addWidget(self.btn_eraser)
        toolbar.addWidget(self.btn_mosaic)
        toolbar.addWidget(self.btn_color)
        toolbar.addWidget(width_label)
        toolbar.addWidget(self.spin_width)
        toolbar.addStretch()

        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Horizontal)

        left_panel = QVBoxLayout()
        left_panel.setSpacing(4)

        self.canvas_container = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas_container)
        self.canvas_layout.setContentsMargins(0, 0, 0, 0)

        self.placeholder_label = QLabel("Click \"Start Snip\" to capture a screen region")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("color: #888; font-size: 14px;")
        self.canvas_layout.addWidget(self.placeholder_label)

        left_panel.addWidget(self.canvas_container, 1)

        left_btns = QHBoxLayout()
        left_btns.setSpacing(10)

        self.btn_ocr = QPushButton("OCR")
        self.btn_ocr.setFixedSize(120, 36)
        self.btn_ocr.setEnabled(False)

        self.btn_copy_img = QPushButton("Copy Image")
        self.btn_copy_img.setFixedSize(120, 36)
        self.btn_copy_img.setEnabled(False)

        left_btns.addStretch()
        left_btns.addWidget(self.btn_ocr)
        left_btns.addWidget(self.btn_copy_img)
        left_btns.addStretch()

        left_panel.addLayout(left_btns)

        left_widget = QWidget()
        left_widget.setLayout(left_panel)
        splitter.addWidget(left_widget)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)

        result_label = QLabel("OCR Result")
        result_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        right_panel.addWidget(result_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("OCR results will appear here...")
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setReadOnly(False)

        right_panel.addWidget(self.text_edit, 1)

        right_btns = QHBoxLayout()
        right_btns.setSpacing(10)

        self.btn_copy_text = QPushButton("Copy Text")
        self.btn_copy_text.setFixedSize(120, 34)
        self.btn_copy_text.clicked.connect(self._copy_text)

        right_btns.addStretch()
        right_btns.addWidget(self.btn_copy_text)
        right_btns.addStretch()

        right_panel.addLayout(right_btns)

        history_label = QLabel("History")
        history_label.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 4px;")
        right_panel.addWidget(history_label)

        self.history_list = QListWidget()
        self.history_list.setMaximumHeight(180)
        self.history_list.itemClicked.connect(self._on_history_clicked)
        right_panel.addWidget(self.history_list)

        right_widget = QWidget()
        right_widget.setLayout(right_panel)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([660, 440])

        root.addWidget(splitter, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            "color: #666; font-size: 12px; padding: 2px 4px;"
            "border-top: 1px solid #ddd;"
        )
        root.addWidget(self.status_label)

        self.tool_group.buttonClicked[int].connect(self._on_tool_changed)
        self.btn_color.clicked.connect(self._pick_color)
        self.spin_width.valueChanged.connect(self._on_width_changed)
        self.btn_ocr.clicked.connect(self._do_ocr)
        self.btn_copy_img.clicked.connect(self._copy_image)

    def _start_snip(self):
        logger.info("Snipper started")
        self.hide()
        QApplication.processEvents()
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(150, self._show_snipper)

    def _show_snipper(self):
        self.snipper = Snipper(self)
        self.snipper.show()

    def load_image(self, pil_image):
        self.show()
        pixmap = pil_to_qpixmap(pil_image)
        if self.placeholder_label:
            self.canvas_layout.removeWidget(self.placeholder_label)
            self.placeholder_label.deleteLater()
            self.placeholder_label = None
        if self.canvas:
            self.canvas_layout.removeWidget(self.canvas)
            self.canvas.deleteLater()
        self.canvas = Canvas(pixmap, self.canvas_container)
        self.canvas_layout.addWidget(self.canvas)
        self.btn_ocr.setEnabled(True)
        self.btn_copy_img.setEnabled(True)
        self._update_color_btn()
        self._show_status("Image loaded %dx%d - click OCR to recognize" % (pixmap.width(), pixmap.height()))
        logger.info("Image loaded: %dx%d", pixmap.width(), pixmap.height())

    def on_snip_cancelled(self):
        self.show()
        logger.info("Snip cancelled, window restored")

    def _on_tool_changed(self, idx):
        if not self.canvas:
            return
        tools = [TOOL_PEN, TOOL_ERASER, TOOL_MOSAIC]
        self.canvas.set_tool(tools[idx])
        logger.info("Tool changed to: %s", tools[idx])

    def _pick_color(self):
        if not self.canvas:
            return
        color = QColorDialog.getColor(self.canvas.pen_color, self)
        if color.isValid():
            self.canvas.pen_color = color
            self._update_color_btn()

    def _update_color_btn(self):
        if self.canvas:
            self.btn_color.setStyleSheet(
                "background-color: %s;" % self.canvas.pen_color.name()
            )
        else:
            self.btn_color.setStyleSheet("background-color: #ff0000;")

    def _on_width_changed(self, val):
        if self.canvas:
            self.canvas.pen_width = val

    def _do_ocr(self):
        if not self.canvas:
            return
        if self.ocr_worker and self.ocr_worker.isRunning():
            return
        if self.ocr_worker:
            try:
                self.ocr_worker.result_ready.disconnect(self._on_ocr_result)
                self.ocr_worker.ocr_failed.disconnect(self._on_ocr_error)
                self.ocr_worker.finished.disconnect(self._on_ocr_finished)
            except TypeError:
                pass
        self.btn_ocr.setEnabled(False)
        self.btn_ocr.setText("Recognizing...")
        merged = self.canvas.get_merged_pixmap()
        img_array = qpixmap_to_numpy(merged)
        logger.info("OCR image array shape: %s dtype: %s", img_array.shape, img_array.dtype)
        self.ocr_worker = OCRWorker(img_array)
        self.ocr_worker.result_ready.connect(self._on_ocr_result, Qt.QueuedConnection)
        self.ocr_worker.ocr_failed.connect(self._on_ocr_error, Qt.QueuedConnection)
        self.ocr_worker.finished.connect(self._on_ocr_finished, Qt.QueuedConnection)
        self.ocr_worker.start()
        logger.info("OCR started")

    def _on_ocr_result(self, text: str):
        if text.strip():
            copy_text_to_clipboard(text)
            self.text_edit.setPlainText(text)
            self._add_history(text)
            self._show_status("OCR done - text copied to clipboard")
            logger.info("OCR result received, length: %d", len(text))
        else:
            self.text_edit.setPlainText("")
            self._show_status("No text recognized in this region")
            logger.info("OCR completed but no text found")

    def _on_ocr_error(self, err_msg: str):
        self.text_edit.setPlainText("")
        self._show_status("OCR failed: " + err_msg[:80])
        logger.error("OCR error shown to user: %s", err_msg[:80])

    def _on_ocr_finished(self):
        self.btn_ocr.setEnabled(True)
        self.btn_ocr.setText("OCR")

    def _show_status(self, msg: str):
        self.status_label.setText(msg)
        logger.info("Status: %s", msg)

    def _copy_text(self):
        text = self.text_edit.toPlainText()
        if text:
            copy_text_to_clipboard(text)
            self._show_status("Text copied to clipboard")
            logger.info("Text copied from editor, length: %d", len(text))
        else:
            self._show_status("No text to copy")

    def _copy_image(self):
        if not self.canvas:
            return
        merged = self.canvas.get_merged_pixmap()
        copy_pixmap_to_clipboard(merged)
        self._show_status("Image copied to clipboard")
        logger.info("Image copied to clipboard")

    def _add_history(self, text: str):
        preview = text.replace("\n", " ")[:60]
        if len(text.replace("\n", " ")) > 60:
            preview += "..."
        item = QListWidgetItem(preview)
        item.setData(Qt.UserRole, text)
        self.history.insert(0, text)
        self.history_list.insertItem(0, item)
        if self.history_list.count() > 50:
            self.history.pop()
            self.history_list.takeItem(self.history_list.count() - 1)
        logger.info("History added, total: %d", self.history_list.count())

    def _on_history_clicked(self, item: QListWidgetItem):
        text = item.data(Qt.UserRole)
        self.text_edit.setPlainText(text)
        logger.info("History item loaded, length: %d", len(text))