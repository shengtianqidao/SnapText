import logging
from PyQt5.QtWidgets import QApplication


logger = logging.getLogger("Clipboard")


def copy_text_to_clipboard(text: str):
    clipboard = QApplication.clipboard()
    clipboard.setText(text)
    logger.info("Text copied, length: %d", len(text))


def copy_pixmap_to_clipboard(pixmap):
    clipboard = QApplication.clipboard()
    clipboard.setPixmap(pixmap)
    logger.info("Image copied to clipboard")