#!/usr/bin/env python3
import argparse
import io
import logging
import re
import struct
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import numpy as np
import PIL.Image
import PIL.ImageOps
import pytesseract
from ass_parser import AssEvent, AssFile, write_ass

logger = logging.getLogger(__file__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output-ass", type=Path, required=True)
    parser.add_argument("-O", "--output-dir", type=Path)
    parser.add_argument("--invert", action="store_true")
    return parser.parse_args()


@dataclass
class Color:
    red: int
    green: int
    blue: int

    def __str__(self) -> str:
        return f"{self.red:02X}{self.green:02X}{self.blue:02X}"


@dataclass
class SubsIndexItem:
    timestamp: timedelta
    file_pos: int


@dataclass
class SubsIndex:
    width: int | None = None
    height: int | None = None
    origin_x: int | None = None
    origin_y: int | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    alpha: float | None = None
    smooth: bool | None = None
    fade_in: int | None = None
    fade_out: int | None = None
    # align: ... = None
    time_offset: int | None = None
    forced_subs: bool | None = None
    palette: list[Color] | None = field(default_factory=list)
    lang_idx: int | None = None
    items: list[SubsIndexItem] | None = field(default_factory=list)


def vobsub_bool(value: str) -> bool:
    value = value.strip()
    if value == "ON":
        return True
    if value == "OFF":
        return False
    raise ValueError(f"unknown boolean value: {value}")


def vobsub_int(value: str) -> bool:
    value = value.strip()
    return int(value)


def vobsub_float(value: str) -> bool:
    value = value.strip()
    if value.endswith("%"):
        return float(value[:-1]) / 100
    raise ValueError(f"unknown float value: {value}")


def vobsub_color(value: str) -> Color:
    value = value.strip()
    match = re.match(
        r"([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})", value, flags=re.I
    )
    if not match:
        raise ValueError(f"unknown color value: {value}")
    return Color(
        red=int(match.group(1), 16),
        green=int(match.group(2), 16),
        blue=int(match.group(3), 16),
    )


def analyze_idx(path: Path) -> SubsIndex:
    idx = SubsIndex()

    for line in path.read_text().splitlines():
        line = line.strip()
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key == "size":
            parts = value.split("x")
            idx.width = vobsub_int(parts[0])
            idx.height = vobsub_int(parts[1])

        elif key == "org":
            parts = value.split(",")
            idx.origin_x = vobsub_int(parts[0])
            idx.origin_y = vobsub_int(parts[1])

        elif key == "scale":
            parts = value.split(",")
            idx.scale_x = vobsub_float(parts[0])
            idx.scale_y = vobsub_float(parts[1])

        elif key == "alpha":
            idx.alpha = vobsub_float(value)

        elif key == "smooth":
            idx.smooth = vobsub_bool(value)

        elif key == "fadein/out":
            parts = value.split(",")
            idx.fade_in = vobsub_int(parts[0])
            idx.fade_out = vobsub_int(parts[1])

        elif key == "time offset":
            idx.time_offset = vobsub_int(value)

        elif key == "forced subs":
            idx.forced_subs = vobsub_bool(value)

        elif key == "palette":
            parts = value.split(",")
            idx.palette = list(map(vobsub_color, parts))

        elif key == "langidx":
            idx.lang_idx = vobsub_int(value)

        elif key == "timestamp":
            match = re.match(
                r"(\d{2}):(\d{2}):(\d{2}):(\d{3}), filepos: ([0-9a-f]+)",
                value,
                flags=re.I,
            )
            if not match:
                raise ValueError(f"invalid idx item: {value}")
            idx.items.append(
                SubsIndexItem(
                    timestamp=timedelta(
                        hours=int(match.group(1)),
                        minutes=int(match.group(2)),
                        seconds=int(match.group(3)),
                        milliseconds=int(match.group(4)),
                    ),
                    file_pos=int(match.group(5), 16),
                )
            )

    return idx


class IoWrapper:
    def __init__(self, handle):
        self.handle = handle
        self.base_offset = handle.tell()
        handle.seek(0, io.SEEK_END)
        self._size = handle.tell()
        handle.seek(self.base_offset)

    def tell(self) -> int:
        return self.handle.tell() - self.base_offset

    def size(self) -> int:
        return self._size

    def seek(self, pos: int) -> None:
        self.handle.seek(self.base_offset + pos)

    def skip(self, pos: int) -> None:
        self.handle.seek(pos, io.SEEK_CUR)

    def read(self, num: int) -> bytes:
        return self.handle.read(num)

    def read_u32(self) -> int:
        return struct.unpack(">I", self.handle.read(4))[0]

    def read_u16(self) -> int:
        return struct.unpack(">H", self.handle.read(2))[0]

    def read_u8(self) -> int:
        return struct.unpack(">B", self.handle.read(1))[0]


def decode_vobsub_line(
    src: bytes,
    src_ofs: int,
    src_len: int,
    trg: bytes,
    trg_ofs: int,
    width: int,
    max_pixels: int,
) -> None:
    nibbles = [0] * (src_len * 2)

    for i in range(src_len):
        b = src[src_ofs + i] & 0xFF
        nibbles[2 * i] = b >> 4
        nibbles[2 * i + 1] = b & 0x0F

    index = 0
    sum_pixels = 0
    x = 0

    while index < len(nibbles) and sum_pixels < max_pixels:
        tmp = nibbles[index] & 0xFF
        index += 1
        if tmp == 0:
            # three or four nibble code
            tmp = nibbles[index] & 0xFF
            index += 1
            if (tmp & 0xC) != 0:
                # three byte code
                length = tmp << 2
                tmp = nibbles[index] & 0xFF
                index += 1
                length |= tmp >> 2
            else:
                # line feed or four nibble code
                length = tmp << 6
                tmp = nibbles[index] & 0xFF
                index += 1
                length |= tmp << 2
                tmp = nibbles[index] & 0xFF
                index += 1
                length |= tmp >> 2
                if length == 0:
                    # line feed
                    length = width - x
                    if length <= 0 or sum_pixels >= max_pixels:
                        length = 0
                        # handle line feed
                        trg_ofs += 2 * width
                        # lines are interlaced!
                        sum_pixels = ((trg_ofs / width) / 2) * width
                        x = 0
                    if (index & 1) == 1:
                        index += 1
        else:
            # one or two nibble code
            length = tmp >> 2
            if length == 0:
                # two nibble code
                length = tmp << 2
                tmp = nibbles[index] & 0xFF
                index += 1
                length |= tmp >> 2

        col = tmp & 0x3
        sum_pixels += length

        for i in range(length):
            trg[trg_ofs + x] = col
            x += 1
            if x >= width:
                trg_ofs += 2 * width  # lines are interlaced!
                x = 0
                if (index & 1) == 1:
                    index += 1


def decode_vobsub_picture(
    idx: SubsIndex, handle: IoWrapper, invert: bool
) -> tuple[PIL.Image.Image, int]:
    ofs = handle.tell()
    ctrl_ofs = -1
    next_ofs = 0
    ctrl_ofs_rel = 0
    rle_size = 0
    rle_buffer_found = 0
    ctrl_size = -1
    ctrl_header_copied = 0
    ctrl_header = None
    length = 0
    pack_header_size = 0
    first_pack_found = False
    rle_fragments = []

    while ofs < handle.size() and (
        ctrl_header_copied < ctrl_size or ctrl_size == -1
    ):
        start_ofs = ofs
        handle.seek(ofs)
        assert handle.read_u32() == 0x000001BA
        ofs += 13
        handle.seek(ofs)
        stuff_ofs = handle.read_u8() & 7
        ofs += 1 + stuff_ofs
        handle.seek(ofs)
        assert handle.read_u32() == 0x000001BD
        ofs += 4
        handle.seek(ofs)
        length = handle.read_u16()
        next_ofs = ofs + 2 + length
        ofs += 2
        pack_header_size = ofs - start_ofs
        ofs += 1
        handle.seek(ofs)
        first_pack = handle.read_u8() & 0x80 == 0x80
        ofs += 1
        handle.seek(ofs)
        pts_length = handle.read_u8()
        ofs += 1 + pts_length  # skip PTS and stream ID
        handle.seek(ofs)
        # packet_stream_id = handle.read_u8() - 0x20
        ofs += 1

        # if packet_stream_id != stream_id:
        #     # packet doesn't belong to stream -> skip
        #     if next_ofs % 0x800 != 0:
        #         ofs = (next_ofs / 0x800 + 1) * 0x800
        #         logger.warning(
        #             "Offset to next fragment is invalid. Fixed to: {ofs:08x}"
        #         )
        #     else:
        #         ofs = next_ofs
        #     ctrl_ofs += 0x800
        #     continue

        header_size = ofs - start_ofs

        if first_pack and pts_length >= 5:
            handle.seek(ofs)
            size = handle.read_u16()
            ofs += 2
            handle.seek(ofs)
            ctrl_ofs_rel = handle.read_u16()
            rle_size = ctrl_ofs_rel - 2
            # calculate size of RLE buffer
            ctrl_size = size - ctrl_ofs_rel - 2
            # calculate size of control header
            assert ctrl_size >= 0, "Invalid control buffer size"
            ctrl_header = io.BytesIO()
            ctrl_ofs = (
                ctrl_ofs_rel + ofs
            )  # might have to be corrected for multiple packets
            ofs += 2
            header_size = ofs - start_ofs
            first_pack_found = True
        else:
            if first_pack_found:
                ctrl_ofs += (
                    header_size  # fix absolute offset by adding header bytes
                )
            else:
                logger.warning(
                    f"Invalid fragment skipped at ofs {start_ofs:08x}"
                )

        # check if control header is (partly) in this packet
        diff = next_ofs - ctrl_ofs - ctrl_header_copied
        if diff < 0:
            diff = 0
        copied = ctrl_header_copied
        for i in range(diff):
            if ctrl_header_copied < ctrl_size:
                handle.seek(ctrl_ofs + i + copied)
                ctrl_header.write(bytes([handle.read_u8()]))
                ctrl_header_copied += 1

        rle_fragments.append(
            [ofs, length - header_size - diff + pack_header_size]
        )
        rle_buffer_found += rle_fragments[-1][1]

        if ctrl_header_copied != ctrl_size and (next_ofs % 0x800 != 0):
            ofs = (next_ofs / 0x800 + 1) * 0x800
            logger.warning(
                f"Offset to next fragment is invalid. Fixed to: {ofs:08x}"
            )
            rle_buffer_found += ofs - next_ofs
        else:
            ofs = next_ofs

    if ctrl_header_copied != ctrl_size:
        logger.warning("Control buffer size inconsistent")
        # fill rest of buffer with break command to avoid wrong detection of
        # forced caption (0x00)
        for i in range(ctrl_size - ctrl_header_copied):
            ctrl_header.write(bytes([0xFF]))

    if rle_buffer_found != rle_size:
        logger.warning("RLE buffer size inconsistent")

    pal = [0, 0, 0, 0]
    alpha = [0, 0, 0, 0]
    alpha_sum = 0
    alpha_update = [0, 0, 0, 0]
    alpha_update_sum = 0
    delay = -1
    col_alpha_update = False

    ctrl_header.seek(0)
    ctrl_header_handle = IoWrapper(ctrl_header)

    # parse control header
    index = 0
    end_seq_ofs = ctrl_header_handle.read_u16() - ctrl_ofs_rel - 2
    if end_seq_ofs < 0 or end_seq_ofs > ctrl_size:
        logger.warning("Invalid end sequence offset -> no end time (1)")
        end_seq_ofs = ctrl_size
    index += 2

    while index < end_seq_ofs:
        ctrl_header_handle.seek(index)
        cmd = ctrl_header_handle.read_u8()
        index += 1
        if cmd == 0:  # forced (?)
            pass

        elif cmd == 1:  # start display
            pass

        elif cmd == 3:  # palette info
            ctrl_header_handle.seek(index)
            tmp = ctrl_header_handle.read_u8()
            index += 1
            pal[3] = tmp >> 4
            pal[2] = tmp & 0x0F
            ctrl_header_handle.seek(index)
            tmp = ctrl_header_handle.read_u8()
            index += 1
            pal[1] = tmp >> 4
            pal[0] = tmp & 0x0F
            logger.debug(f"Palette: {pal}")

        elif cmd == 4:  # alpha info
            ctrl_header_handle.seek(index)
            tmp = ctrl_header_handle.read_u8()
            index += 1
            alpha[3] = tmp >> 4
            alpha[2] = tmp & 0x0F
            ctrl_header_handle.seek(index)
            tmp = ctrl_header_handle.read_u8()
            index += 1
            alpha[1] = tmp >> 4
            alpha[0] = tmp & 0x0F
            for i in range(4):
                alpha_sum += alpha[i] & 0xFF
            logger.debug(f"Alpha: {alpha}")

        elif cmd == 5:  # coordinates
            ctrl_header_handle.seek(index)
            tmp_a = ctrl_header_handle.read_u8()
            tmp_b = ctrl_header_handle.read_u8()
            tmp_c = ctrl_header_handle.read_u8()
            tmp_d = ctrl_header_handle.read_u8()
            tmp_e = ctrl_header_handle.read_u8()
            tmp_f = ctrl_header_handle.read_u8()
            x_ofs = (tmp_a << 4) | (tmp_b >> 4)
            width = (((tmp_b & 0xF) << 8) | tmp_c) - x_ofs + 1
            y_ofs = (tmp_d << 4) | (tmp_e >> 4)
            height = (((tmp_e & 0xF) << 8) | tmp_f) - y_ofs + 1
            logger.debug(f"Area info: {x_ofs},{y_ofs} {width}x{height}")
            index += 6

        elif cmd == 6:  # offset to RLE buffer
            ctrl_header_handle.seek(index)
            even_ofs = ctrl_header_handle.read_u16() - 4
            odd_ofs = ctrl_header_handle.read_u16() - 4
            index += 4
            logger.debug(f"RLE ofs: {even_ofs:08x}, {odd_ofs:08x}")

        elif cmd == 7:  # color/alpha update
            col_alpha_update = True
            # int len = ToolBox.getWord(ctrl_header, index);
            #  ignore the details for now, but just get alpha and palette info
            alpha_update_sum = 0
            ctrl_header_handle.seek(index + 10)
            tmp = ctrl_header_handle.read_u8()
            alpha_update[3] = tmp >> 4
            alpha_update[2] = tmp & 0x0F
            tmp = ctrl_header_handle.read_u8()
            alpha_update[1] = tmp >> 4
            alpha_update[0] = tmp & 0x0F
            for i in range(4):
                alpha_update_sum += alpha_update[i] & 0xFF
            # only use more opaque colors
            if alpha_update_sum > alpha_sum:
                alpha_sum = alpha_update_sum
                alpha_update = alpha[:]
                # take over frame palette
                ctrl_header_handle.seek(index + 8)
                tmp = ctrl_header_handle.read_u8()
                pal[3] = tmp >> 4
                pal[2] = tmp & 0x0F
                tmp = ctrl_header_handle.read_u8()
                pal[1] = tmp >> 4
                pal[0] = tmp & 0x0F
            # search end sequence
            index = end_seq_ofs
            ctrl_header_handle.seek(index)
            delay = ctrl_header_handle.read_u16() * 1024
            end_seq_ofs = ctrl_header_handle.read_u16() - ctrl_ofs_rel - 2
            if end_seq_ofs < 0 or end_seq_ofs > ctrl_size:
                logger.warning(
                    "Invalid end sequence offset -> no end time (2)"
                )
                end_seq_ofs = ctrl_size
            index += 4

        elif cmd == 0xFF:
            break

        else:
            logger.warning("Unknown control sequence {cmd} skipped")

    if end_seq_ofs != ctrl_size:
        ctrl_seq_count = 1
        index = -1
        next_index = end_seq_ofs
        while next_index != index:
            index = next_index
            ctrl_header_handle.seek(index)
            delay = ctrl_header_handle.read_u16() * 10
            ctrl_header_handle.seek(index + 2)
            next_index = ctrl_header_handle.read_u16() - ctrl_ofs_rel - 2
            ctrl_seq_count += 1
        if ctrl_seq_count > 2:
            logger.warning(
                "Control sequence(s) ignored - result may be erratic"
            )
    else:
        logger.warning("Duration information not found")

    if col_alpha_update:
        logger.warning(
            "Palette update/alpha fading detected - result may be erratic"
        )

    if alpha_sum == 0:
        logger.warning("Invisible caption due to zero alpha")

    if width > idx.width or height > idx.height:
        logger.warning(
            f"Subpicture too large: {width}x{height} > {idx.width}x{idx.height}"
        )

    # copy buffer(s)
    if odd_ofs > even_ofs:
        size_even = odd_ofs - even_ofs
        size_odd = rle_size - odd_ofs
    else:
        size_odd = even_ofs - odd_ofs
        size_even = rle_size - even_ofs

    assert size_even > 0 and size_odd > 0, "Corrupt buffer offset information"

    # copy buffers
    rle_buffer_handle = io.BytesIO()
    for ofs, size in rle_fragments:
        handle.seek(ofs)
        rle_buffer_handle.write(handle.read(size))
    rle_buffer_handle.seek(0)
    rle_buffer = rle_buffer_handle.read()

    decoded_pixels = np.zeros(width * height, dtype="b")

    # decode even lines
    decode_vobsub_line(
        rle_buffer,
        even_ofs,
        size_even,
        decoded_pixels,
        0,
        width,
        width * (height // 2 + (height & 1)),
    )

    # decode odd lines
    decode_vobsub_line(
        rle_buffer,
        odd_ofs,
        size_odd,
        decoded_pixels,
        width,
        width,
        (height // 2) * width,
    )

    if invert:
        pal[1], pal[3] = pal[3], pal[1]

    palmap_r = np.array([idx.palette[pal[c]].red for c in range(4)])
    palmap_g = np.array([idx.palette[pal[c]].green for c in range(4)])
    palmap_b = np.array([idx.palette[pal[c]].blue for c in range(4)])
    palmap_a = np.array([((alpha[c] * 0xFF) // 0xF) for c in range(4)])

    if palmap_a[0] == 0:
        palmap_r[0] = palmap_r[3]
        palmap_g[0] = palmap_g[3]
        palmap_b[0] = palmap_b[3]

    final_pixels = np.zeros(4 * width * height, dtype="b")
    final_pixels[::4] = palmap_r[decoded_pixels]
    final_pixels[1::4] = palmap_g[decoded_pixels]
    final_pixels[2::4] = palmap_b[decoded_pixels]
    final_pixels[3::4] = palmap_a[decoded_pixels]

    image = PIL.Image.frombytes(
        mode="RGBA", size=(width, height), data=bytes(final_pixels)
    )
    return image, delay


def main() -> None:
    args = parse_args()

    if args.source.suffix == ".idx":
        idx_path = args.source
        sub_path = idx_path.with_suffix(".sub")
    elif args.source.suffix == ".sub":
        sub_path = args.source
        idx_path = sub_path.with_suffix(".idx")

    for path in [idx_path, sub_path]:
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist")

    idx = analyze_idx(idx_path)

    with sub_path.open("rb") as sub_file_handle:
        ass_file = AssFile()
        for i, item in enumerate(idx.items):
            print(item.timestamp)

            sub_file_handle.seek(item.file_pos)
            image, delay = decode_vobsub_picture(
                idx, IoWrapper(sub_file_handle), invert=args.invert
            )
            if args.output_dir:
                image_path = (
                    args.output_dir.expanduser()
                    / f"{sub_path.stem}-{i+1:04d}.png"
                )
                image_path.parent.mkdir(exist_ok=True, parents=True)
                image.save(image_path)
            text = pytesseract.image_to_string(image)

            ass_file.events.append(
                AssEvent(
                    start=item.timestamp.total_seconds() * 1000,
                    end=item.timestamp.total_seconds() * 1000 + delay,
                    text=text.replace("\n", r"\N"),
                )
            )

            print(text)
            print(flush=True)

    with args.output_ass.open("w") as handle:
        write_ass(ass_file, handle)


if __name__ == "__main__":
    main()
