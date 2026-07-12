import logging
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("OCRWorker")

_ocr_engine = None
_engine_ready = False


def get_ocr_engine():
    global _ocr_engine, _engine_ready
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(
            use_angle_cls=True,
            lang="ch",
            show_log=False
        )
        logger.info("PaddleOCR engine initialized, warming up...")
        _warmup(_ocr_engine)
        _engine_ready = True
        logger.info("PaddleOCR engine ready")
    return _ocr_engine


def _warmup(ocr):
    try:
        dummy = np.ones((32, 128, 3), dtype=np.uint8) * 255
        ocr.ocr(dummy, cls=True)
        logger.info("PaddleOCR warmup done")
    except Exception as e:
        logger.warning("PaddleOCR warmup failed (non-fatal): %s", e)


class OCRWorker(QThread):
    result_ready = pyqtSignal(str)
    ocr_failed = pyqtSignal(str)

    def __init__(self, image_array):
        super().__init__()
        self.image_array = image_array

    def run(self):
        try:
            ocr = get_ocr_engine()
            logger.info("OCR engine ready, running inference...")
            result = ocr.ocr(self.image_array, cls=True)
            logger.info("OCR raw result: %s", str(result)[:500])

            lines = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0].strip()
                    if text:
                        lines.append(text)

            final_text = "\n".join(lines)
            self.result_ready.emit(final_text)
            logger.info("OCR completed, %d lines", len(lines))
        except Exception as e:
            err_msg = str(e)
            logger.error("OCR failed: %s", err_msg, exc_info=True)
            self.ocr_failed.emit(err_msg)