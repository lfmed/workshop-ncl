"""Contraste WCAG 2.x entre pares de cores. Uso: python contraste_wcag.py"""
import itertools


def lum(h):
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


CORES = {"preto": "#000000", "branco": "#FFFFFF", "lilas": "#CC99FE", "verde_agua": "#67FFCC", "lima": "#DBED1F",
         "azul_noite": "#0E2233", "grafite": "#464646",
         "lilas_escuro": "#6B2FC0", "verde_escuro": "#00795A", "lima_escuro": "#5E6600"}
if __name__ == "__main__":
    for fundo in ("preto", "branco", "azul_noite"):
        print(f"--- sobre {fundo} ({CORES[fundo]})")
        for k, v in CORES.items():
            if k != fundo:
                r = ratio(v, CORES[fundo])
                print(f"  {k:13s} {v}  {r:5.2f}  {'AA texto' if r >= 4.5 else 'AA grande/UI' if r >= 3 else 'NAO usar p/ texto'}")
    for a in ("verde_agua", "lima", "lilas"):
        print(f"preto sobre {a}: {ratio('#000000', CORES[a]):.2f}")
