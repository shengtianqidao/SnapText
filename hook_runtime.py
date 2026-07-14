import sys
import os

if getattr(sys, 'frozen', False):
    base = sys._MEIPASS

    paddleocr_dir = os.path.join(base, 'paddleocr')
    if os.path.isdir(paddleocr_dir) and paddleocr_dir not in sys.path:
        sys.path.append(paddleocr_dir)

    cython_dir = os.path.join(base, 'Cython')
    if os.path.isdir(cython_dir):
        import Cython
        Cython.__path__.insert(0, cython_dir)