# -*- coding: utf-8 -*-
"""Set .text writable by patching the section header byte directly.

pefile's write() refuses this path, so the header field is edited in place:
section headers start at e_lfanew + 4 + 20 + SizeOfOptionalHeader, each 40 bytes,
and Characteristics is at +36 inside one.
"""
import struct
import sys

exe = sys.argv[1]
data = bytearray(open(exe, 'rb').read())

e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
assert data[e_lfanew:e_lfanew + 4] == b'PE\0\0'
nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
sec0 = e_lfanew + 24 + opt_size

IMAGE_SCN_MEM_WRITE = 0x80000000
done = []
for i in range(nsec):
    off = sec0 + 40 * i
    name = data[off:off + 8].rstrip(b'\x00').decode(errors='replace')
    chars = struct.unpack_from('<I', data, off + 36)[0]
    if name == '.text' and not (chars & IMAGE_SCN_MEM_WRITE):
        struct.pack_into('<I', data, off + 36, chars | IMAGE_SCN_MEM_WRITE)
        done.append('%s %08X -> %08X' % (name, chars, chars | IMAGE_SCN_MEM_WRITE))

open(exe, 'wb').write(data)
print('text writable:', done or 'already')
