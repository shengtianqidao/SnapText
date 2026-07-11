import numpy as np
from PyQt5.QtGui import QPixmap, QImage


def pil_to_qpixmap(pil_image):
    if pil_image.mode == "RGBA":
        data = pil_image.tobytes("raw", "RGBA")
        qimage = QImage(data, pil_image.width, pil_image.height,
                        4 * pil_image.width, QImage.Format_RGBA8888)
    else:
        pil_image = pil_image.convert("RGB")
        data = pil_image.tobytes("raw", "RGB")
        qimage = QImage(data, pil_image.width, pil_image.height,
                        3 * pil_image.width, QImage.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def qpixmap_to_numpy(pixmap: QPixmap) -> np.ndarray:
    qimage = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
    width = qimage.width()
    height = qimage.height()
    ptr = qimage.bits()
    ptr.setsize(height * width * 3)
    arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 3))
    return arr[:, :, ::-1].copy()