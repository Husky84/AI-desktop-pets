"""Read-only verification of PNG deliverables and the PSD container."""
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image, ImageChops

root = Path(__file__).resolve().parent.parent
actions = ('idle', 'walk', 'wave', 'sleep')
report = {'frame_size': [320, 320], 'actions': {}, 'live2d_status': 'unrigged_parts_board'}
for action in actions:
    paths = sorted((root / 'frames' / action).glob('*.png'))
    assert len(paths) == 8, (action, len(paths))
    hashes = []
    with Image.open(root / 'strips' / f'{action}_strip.png') as strip:
        assert strip.size == (2560, 320)
        for index, path in enumerate(paths):
            with Image.open(path) as image:
                assert image.size == (320, 320) and image.mode == 'RGBA', path
                alpha = image.getchannel('A')
                bbox = alpha.getbbox()
                assert bbox and bbox[0] > 0 and bbox[1] > 0 and bbox[2] < 320 and bbox[3] < 320, (path, bbox)
                assert alpha.getextrema() == (0, 255), path
                assert alpha.histogram()[0] > 10000, path
                tile = strip.crop((index * 320, 0, (index + 1) * 320, 320))
                assert ImageChops.difference(image, tile).getbbox() is None, path
                hashes.append(hashlib.sha256(image.tobytes()).hexdigest())
    assert len(set(hashes)) == 8, (action, 'duplicate frame')
    report['actions'][action] = {'frames': 8, 'unique_frames': 8, 'rgba': True, 'transparent_margin': True, 'strip_matches': True}

psd_path = root / 'live2d_preparation' / 'parts_board_DRAFT.psd'
data = psd_path.read_bytes()
assert data[:4] == b'8BPS' and struct.unpack_from('>H', data, 4)[0] == 1
channels, height, width, depth, color_mode = struct.unpack_from('>HIIHH', data, 12)
assert (channels, height, width, depth, color_mode) == (4, 1254, 1254, 8, 3)
offset = 26
for _ in range(2):
    size = struct.unpack_from('>I', data, offset)[0]
    offset += 4 + size
mask_size = struct.unpack_from('>I', data, offset)[0]
mask_start = offset + 4
info_size = struct.unpack_from('>I', data, mask_start)[0]
count = struct.unpack_from('>h', data, mask_start + 4)[0]
assert count == -16, count
position = mask_start + 6
layer_names, channel_total = [], 0
for _ in range(abs(count)):
    top, left, bottom, right, n_channels = struct.unpack_from('>iiiiH', data, position)
    position += 18
    assert n_channels == 4 and 0 <= top < bottom <= height and 0 <= left < right <= width
    for _ in range(n_channels):
        channel, size = struct.unpack_from('>hI', data, position)
        position += 6
        assert size == 2 + (right - left) * (bottom - top)
        channel_total += size
    assert data[position:position + 8] == b'8BIMnorm'
    position += 12
    extra_size = struct.unpack_from('>I', data, position)[0]
    extra_start = position + 4
    name_start = extra_start + 8
    name_length = data[name_start]
    layer_names.append(data[name_start + 1:name_start + 1 + name_length].decode('ascii'))
    position = extra_start + extra_size
assert position + channel_total <= mask_start + 4 + info_size
assert len(set(layer_names)) == 16
with Image.open(psd_path) as psd, Image.open(root / 'live2d_preparation' / 'parts_atlas.png') as atlas:
    assert psd.size == atlas.size
    merged = psd.convert('RGBA')
    assert ImageChops.difference(merged, atlas.convert('RGBA')).getbbox() is None
assert len(list((root / 'live2d_preparation' / 'parts').glob('*.png'))) == 16
assert not list(root.rglob('*.moc3')) and not list(root.rglob('*.cmo3'))
report['psd'] = {'size': [width, height], 'layers': 16, 'names': layer_names, 'merged_alpha': True, 'composite_matches_atlas': True, 'cubism_import_tested': False}
report['png_frames'] = 32
print(json.dumps(report, ensure_ascii=False, indent=2))
