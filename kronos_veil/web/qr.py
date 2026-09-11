"""Pure-Python QR Code SVG generator for Kronos Veil.

Zero-dependency QR Code generator (Version 3-L, 29x29 matrix, up to 53 bytes),
ideal for mobile pairing with local LAN URLs (e.g., http://192.168.1.100:8989).
"""

from __future__ import annotations

import logging
from typing import List, Tuple

logger = logging.getLogger("KronosVeil.QR")

# Precompute Galois Field GF(256) tables (primitive polynomial 0x11d)
GF_EXP = [0] * 512
GF_LOG = [0] * 256
_val = 1
for _i in range(255):
    GF_EXP[_i] = _val
    GF_EXP[_i + 255] = _val
    GF_LOG[_val] = _i
    _val = (_val << 1) ^ (0x11D if (_val & 0x80) else 0)


def gf_mul(x: int, y: int) -> int:
    if x == 0 or y == 0:
        return 0
    return GF_EXP[GF_LOG[x] + GF_LOG[y]]


def rs_encode(data: bytes, nsym: int) -> bytes:
    """Generate Reed-Solomon error correction codewords."""
    # Generator polynomial of degree nsym
    gen = [1]
    for i in range(nsym):
        # Multiply gen by (x - a^i)
        next_gen = [0] * (len(gen) + 1)
        root = GF_EXP[i]
        for j, coef in enumerate(gen):
            next_gen[j] ^= gf_mul(coef, root)
            next_gen[j + 1] ^= coef
        gen = next_gen

    msg_poly = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = msg_poly[i]
        if coef != 0:
            for j in range(1, len(gen)):
                msg_poly[i + j] ^= gf_mul(gen[j], coef)

    return bytes(msg_poly[-nsym:])


def generate_qr_matrix(text: str) -> List[List[int]]:
    """Build a standard QR Code matrix (Version 3-L, 29x29, holds up to 53 bytes)."""
    size = 29
    matrix = [[None] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def set_module(r: int, c: int, val: int, is_reserved: bool = True):
        matrix[r][c] = val
        if is_reserved:
            reserved[r][c] = True

    # 1. Finder Patterns (7x7) at Top-Left, Top-Right, Bottom-Left
    def place_finder(start_r: int, start_c: int):
        for r in range(start_r, start_r + 7):
            for c in range(start_c, start_c + 7):
                dr = r - start_r
                dc = c - start_c
                if dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4):
                    set_module(r, c, 1)
                else:
                    set_module(r, c, 0)
        # Separators
        for r in range(start_r - 1, start_r + 8):
            for c in range(start_c - 1, start_c + 8):
                if 0 <= r < size and 0 <= c < size and not reserved[r][c]:
                    set_module(r, c, 0)

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    # 2. Alignment Pattern at (20, 20) for Version 3 (29x29)
    align_r, align_c = 20, 20
    for r in range(align_r - 2, align_r + 3):
        for c in range(align_c - 2, align_c + 3):
            dr = abs(r - align_r)
            dc = abs(c - align_c)
            if dr == 2 or dc == 2 or (dr == 0 and dc == 0):
                set_module(r, c, 1)
            else:
                set_module(r, c, 0)

    # 3. Timing Patterns
    for i in range(8, size - 8):
        bit = 1 if (i % 2 == 0) else 0
        if not reserved[6][i]:
            set_module(6, i, bit)
        if not reserved[i][6]:
            set_module(i, 6, bit)

    # Dark module
    set_module(size - 8, 8, 1)

    # Reserve format info areas
    for i in range(9):
        if not reserved[8][i]:
            set_module(8, i, 0)
        if not reserved[i][8]:
            set_module(i, 8, 0)
    for i in range(size - 8, size):
        if not reserved[8][i]:
            set_module(8, i, 0)
        if not reserved[i][8]:
            set_module(i, 8, 0)

    # 4. Data bitstream encoding (Byte Mode)
    data_bytes = text.encode("utf-8")[:53]
    bitstream = []

    # Mode: 0100 (Byte mode)
    bitstream.extend([0, 1, 0, 0])
    # Char count: 8 bits
    bitstream.extend([(len(data_bytes) >> (7 - b)) & 1 for b in range(8)])
    # Data bits
    for b in data_bytes:
        bitstream.extend([(b >> (7 - bit)) & 1 for bit in range(8)])

    # Terminator (up to 4 zeroes)
    capacity_bits = 55 * 8  # V3-L has 55 data codewords (440 bits)
    pad_needed = min(4, capacity_bits - len(bitstream))
    bitstream.extend([0] * pad_needed)

    # Pad to byte boundary
    while len(bitstream) % 8 != 0:
        bitstream.append(0)

    # Pad with 0xEC and 0x11 alternately
    pad_bytes = [0xEC, 0x11]
    idx = 0
    while len(bitstream) < capacity_bits:
        b = pad_bytes[idx % 2]
        bitstream.extend([(b >> (7 - bit)) & 1 for bit in range(8)])
        idx += 1

    # Convert bitstream to codewords
    data_codewords = bytearray()
    for i in range(0, len(bitstream), 8):
        byte_val = 0
        for bit in bitstream[i:i + 8]:
            byte_val = (byte_val << 1) | bit
        data_codewords.append(byte_val)

    # Reed-Solomon Error Correction (15 EC codewords for V3-L)
    ec_codewords = rs_encode(bytes(data_codewords), 15)
    all_codewords = bytes(data_codewords) + ec_codewords

    # Convert all codewords to bit array
    full_bits = []
    for b in all_codewords:
        full_bits.extend([(b >> (7 - bit)) & 1 for bit in range(8)])

    # 5. Interleave bits into matrix in 2-column zig-zag fashion
    bit_idx = 0
    right = size - 1
    upward = True

    while right > 0:
        if right == 6:  # Skip vertical timing column
            right -= 1

        rows = range(size - 1, -1, -1) if upward else range(size)
        for r in rows:
            for c in (right, right - 1):
                if not reserved[r][c]:
                    b = full_bits[bit_idx] if bit_idx < len(full_bits) else 0
                    bit_idx += 1
                    # Apply Mask Pattern 0: (row + col) % 2 == 0
                    masked_b = b ^ (1 if ((r + c) % 2 == 0) else 0)
                    matrix[r][c] = masked_b
        right -= 2
        upward = not upward

    # 6. Format info bits (ECC L + Mask 0 -> 0x77C4)
    format_bits = 0x77C4
    for i in range(15):
        bit = (format_bits >> (14 - i)) & 1
        # Place around top-left
        if i < 6:
            matrix[8][i] = bit
        elif i < 8:
            matrix[8][i + 1] = bit
        elif i == 8:
            matrix[7][8] = bit
        else:
            matrix[14 - i][8] = bit

        # Place around top-right and bottom-left
        if i < 8:
            matrix[size - 1 - i][8] = bit
        else:
            matrix[8][size - 15 + i] = bit

    return matrix


def generate_qr_svg(text: str, fill_color: str = "#00e5ff", bg_color: str = "#0b0f19") -> str:
    """Generate a high-contrast scalable SVG string for the given URL/text."""
    try:
        matrix = generate_qr_matrix(text)
        size = len(matrix)
        scale = 6
        margin = 2
        total_dim = (size + 2 * margin) * scale

        rects: List[str] = []
        for r in range(size):
            for c in range(size):
                if matrix[r][c] == 1:
                    x = (c + margin) * scale
                    y = (r + margin) * scale
                    rects.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}" fill="{fill_color}" />')

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_dim} {total_dim}" '
            f'width="{total_dim}" height="{total_dim}">'
            f'<rect width="{total_dim}" height="{total_dim}" fill="{bg_color}" rx="8"/>'
            + "".join(rects)
            + "</svg>"
        )
        return svg
    except Exception as exc:
        logger.warning("QR generation error: %s", exc)
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180"><text x="10" y="90" fill="#fff">{text}</text></svg>'
