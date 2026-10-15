"""Halve a Radiance .hdr (new-style RLE RGBE) with 2x2 box averaging in linear light.
usage: python3 scripts/downscale-hdr.py in.hdr out.hdr
Used for public/hdri (the studio environment that lights the 3D steel)."""
import sys, numpy as np

def read_hdr(path):
    data = open(path, 'rb').read()
    head_end = data.index(b'\n\n') + 2
    line_end = data.index(b'\n', head_end)
    _, h, _, w = data[head_end:line_end].split()
    h, w = int(h), int(w)
    p = line_end + 1
    img = np.zeros((h, w, 4), np.uint8)
    for y in range(h):
        assert data[p] == 2 and data[p + 1] == 2, 'expects new-style RLE'
        p += 4
        for c in range(4):
            x = 0
            while x < w:
                n = data[p]; p += 1
                if n > 128:
                    n -= 128; img[y, x:x + n, c] = data[p]; p += 1
                else:
                    img[y, x:x + n, c] = np.frombuffer(data[p:p + n], np.uint8); p += n
                x += n
    e = img[..., 3].astype(np.float32)
    scale = np.where(img[..., 3] > 0, np.ldexp(1.0, (e - 136).astype(np.int32)), 0.0)
    return img[..., :3].astype(np.float32) * scale[..., None]

def encode_rgbe(rgb):
    m = rgb.max(axis=-1)
    out = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    nz = m > 1e-32
    mant, ex = np.frexp(m[nz])
    f = mant * 256.0 / m[nz]
    out[nz, :3] = np.clip(rgb[nz] * f[:, None], 0, 255).astype(np.uint8)
    out[nz, 3] = (ex + 128).astype(np.uint8)
    return out

def rle(row):
    out = bytearray(); i = 0; n = len(row)
    while i < n:
        run = 1
        while i + run < n and run < 127 and row[i + run] == row[i]: run += 1
        if run >= 4:
            out += bytes([128 + run, row[i]]); i += run; continue
        j = i
        while j < n and j - i < 128:
            if j + 3 < n and row[j] == row[j + 1] == row[j + 2] == row[j + 3]: break
            j += 1
        out += bytes([j - i]) + bytes(row[i:j]); i = j
    return out

def write_hdr(path, rgb):
    h, w = rgb.shape[:2]
    px = encode_rgbe(rgb)
    out = bytearray(b'#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n' + f'-Y {h} +X {w}\n'.encode())
    for y in range(h):
        out += bytes([2, 2, w >> 8, w & 255])
        for c in range(4): out += rle(px[y, :, c])
    open(path, 'wb').write(out)

src = read_hdr(sys.argv[1])
h, w = src.shape[:2]
half = src.reshape(h // 2, 2, w // 2, 2, 3).mean(axis=(1, 3))
write_hdr(sys.argv[2], half)
print(sys.argv[2], half.shape[1], 'x', half.shape[0])
