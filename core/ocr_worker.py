import logging
import sys
import os
import types
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("OCRWorker")

_ocr_engine = None
_engine_ready = False


_frozen_paths_fixed = False


def _fix_frozen_paths():
    global _frozen_paths_fixed
    if _frozen_paths_fixed:
        return
    _frozen_paths_fixed = True

    if not getattr(sys, 'frozen', False):
        return
    base = sys._MEIPASS
    paddleocr_dir = os.path.join(base, 'paddleocr')
    if not os.path.isdir(paddleocr_dir):
        return

    if paddleocr_dir not in sys.path:
        sys.path.append(paddleocr_dir)

    import importlib.util

    _pdir = paddleocr_dir

    class _PaddleOCRFileFixer:
        def find_spec(self, fullname, path, target=None):
            if not fullname.startswith('paddleocr.'):
                return None
            sub_name = fullname[len('paddleocr.'):]
            sub_path = os.path.join(_pdir, sub_name.replace('.', os.sep))
            py_path = sub_path + '.py'
            if os.path.isfile(py_path):
                return importlib.util.spec_from_file_location(
                    fullname, py_path
                )
            init_path = os.path.join(sub_path, '__init__.py')
            if os.path.isfile(init_path):
                return importlib.util.spec_from_file_location(
                    fullname, init_path,
                    submodule_search_locations=[sub_path]
                )
            return None

    sys.meta_path.insert(0, _PaddleOCRFileFixer())

    import paddleocr
    paddleocr.__path__ = [paddleocr_dir]
    paddleocr.__file__ = os.path.join(paddleocr_dir, '__init__.py')

    try:
        _fix_submodule_files(paddleocr, paddleocr_dir)
    except Exception as e:
        logger.warning("Submodule file fix skipped (non-fatal): %s", e)

    cython_dir = os.path.join(base, 'Cython')
    if os.path.isdir(cython_dir):
        import Cython
        Cython.__path__.insert(0, cython_dir)
    logger.info("Frozen paths fixed: paddleocr_dir=%s", paddleocr_dir)


def _fix_submodule_files(package, pkg_dir):
    pkg_name = package.__name__
    for root, _dirs, files in os.walk(pkg_dir):
        for f in files:
            if not f.endswith('.py'):
                continue
            try:
                full_path = os.path.join(root, f)
                rel = os.path.relpath(full_path, pkg_dir)
                parts = rel[:-3].replace(os.sep, '.')
                if parts.endswith('.__init__'):
                    parts = parts[:-9]
                mod_name = pkg_name + '.' + parts if parts else pkg_name
                if mod_name not in sys.modules:
                    continue
                mod = sys.modules[mod_name]
                if not isinstance(mod, types.ModuleType):
                    continue
                mod.__file__ = full_path
                if hasattr(mod, '__path__') and isinstance(mod.__path__, list):
                    mod_dir = os.path.dirname(full_path)
                    if mod_dir not in mod.__path__:
                        mod.__path__.insert(0, mod_dir)
            except Exception as e:
                logger.debug("Skip submodule fix for %s: %s", f, e)


def get_ocr_engine():
    global _ocr_engine, _engine_ready
    if _ocr_engine is None:
        _fix_frozen_paths()
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