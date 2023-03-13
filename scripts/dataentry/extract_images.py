import os
import sys
from pathlib import Path

from PIL import Image

from math import log
import fitz
from tqdm import tqdm

PATH_TO_PROCEEDINGS = Path(r"demo_proceedings\proceedings\final")


def get_histogram_dispersion(histogram):
    log2 = lambda x: log(x) / log(2)

    total = len(histogram)
    counts = {}
    for item in histogram:
        counts.setdefault(item, 0)
        counts[item] += 1

    ent = 0
    for i in counts:
        p = float(counts[i]) / total
        ent -= p * log2(p)
    return -ent * log2(1 / ent)


os.system("rm out/*")
os.system("mkdir out")

for pdf_path in tqdm(list(PATH_TO_PROCEEDINGS.iterdir())):
    paper_id = pdf_path.name
    pdf_path = pdf_path / f"{pdf_path.name}_Paper.pdf"
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        best = -sys.maxsize - 1
        for img in doc.getPageImageList(i):
            xref = img[0]
            pix = fitz.Pixmap(doc, xref)
            try:
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            except:
                continue

            disp = get_histogram_dispersion(img.histogram())
            if disp > best:
                best = disp
                name = Path("out") / f"demo.{paper_id}.png"
                img = img.convert("RGBA")

                img.save(name, "png")

            pix = None
