"""0.12.9 optimization guards: the XMP head-read ladder and the
pyexiv2-free main process. Run as a file.
"""
import os
import sys
import tempfile

FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def jpeg_with_xmp_at(offset_pad, rating='4'):
    xmp = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
           'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description rdf:about="" '
           'xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
           f'xmp:Rating="{rating}"/></rdf:RDF></x:xmpmeta>').encode()
    seg = (b'\xff\xe1' + (len(xmp) + 2 + 29).to_bytes(2, 'big')
           + b'http://ns.adobe.com/xap/1.0/\x00' + xmp)
    pad = b''
    remaining = offset_pad
    while remaining > 0:            # COM segments push the XMP deeper
        chunk = min(65533, remaining)
        pad += b'\xff\xfe' + (chunk + 2).to_bytes(2, 'big') + b'x' * chunk
        remaining -= chunk
    return (b'\xff\xd8' + pad + seg
            + os.urandom(5 * 1024 * 1024) + b'\xff\xd9')


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cammello import culling, iptc

    # The ladder must find the XMP on every rung AND behind the last one -
    # the speed win is worthless if any placement stops being read. The
    # rung-2 case is the exact spot where the first version of the ladder
    # broke (termination condition inverted), so it stays tested forever.
    with tempfile.TemporaryDirectory() as tmp:
        for name, off in (('rung 1', 40 * 1024),
                          ('rung 2', 1024 * 1024),
                          ('beyond the ladder', 6 * 1024 * 1024)):
            p = os.path.join(tmp, 't.jpg')
            open(p, 'wb').write(jpeg_with_xmp_at(off))
            rating, _ = culling._read_rating_label_text(p)
            check(f'XMP found on {name}', rating == '4', str(rating))
        p = os.path.join(tmp, 'plain.jpg')
        open(p, 'wb').write(b'\xff\xd8' + os.urandom(1024 * 1024) + b'\xff\xd9')
        rating, _ = culling._read_rating_label_text(p)
        check('file without XMP reads as unrated', rating is None)

    # The ladder rungs stay ascending (a refactor that reorders them would
    # silently re-read the whole head every time).
    check('ladder rungs ascend',
          list(culling._XMP_HEAD_LADDER)
          == sorted(set(culling._XMP_HEAD_LADDER)),
          str(culling._XMP_HEAD_LADDER))

    # The GUI process must not have the native library loaded: the feature
    # gate answers from module PRESENCE, all real exiv2 work lives in the
    # helper process (0.12.6 architecture).
    check('pyexiv2 is not imported into this process',
          'pyexiv2' not in sys.modules, str('pyexiv2' in sys.modules))
    check('the IPTC feature gate still answers', iptc.available() in (True, False))
    check('gate did not import the library either',
          'pyexiv2' not in sys.modules)

    print('\n' + ('ALL PERF GUARDS PASSED' if not FAILURES
                   else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
