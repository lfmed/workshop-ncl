"""Extrai as cores vetoriais (preenchimento/traço) e de texto de um PDF, com área aproximada coberta.
Uso: python -I extrair_cores_pdf.py <arquivo.pdf>"""
import collections
import sys

import fitz  # pymupdf

doc = fitz.open(sys.argv[1])
fill, texto, paginas = collections.Counter(), collections.Counter(), collections.defaultdict(set)
hexa = lambda c: "#%02X%02X%02X" % tuple(round(v * 255) for v in c[:3]) if c and len(c) >= 3 else None
for i, p in enumerate(doc):
    for d in p.get_drawings():
        for k in ("fill", "color"):
            h = hexa(d.get(k))
            if h:
                area = d["rect"].width * d["rect"].height if k == "fill" else 1
                fill[h] += area
                paginas[h].add(i + 1)
    for b in p.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                h = "#%06X" % s["color"]
                texto[(h, s["font"])] += len(s["text"].strip())
tot = sum(fill.values())
print("== Cores de forma (por area) ==")
for h, a in fill.most_common(20):
    print(f"{h}  {100*a/tot:5.1f}%  paginas={len(paginas[h])}")
print("== Cores/fontes de texto (por caracteres) ==")
for (h, f), n in texto.most_common(15):
    print(f"{h}  {f:35s} {n}")
