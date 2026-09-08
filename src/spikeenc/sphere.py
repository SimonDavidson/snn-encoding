"""Reading corpus audio — NIST SPHERE and RIFF WAV, on numpy and scipy alone.

TIMIT ships as NIST SPHERE (`.WAV` files that are not RIFF WAV), and this
machine has no `soundfile`, no `sph2pipe`, no `sox` and no `ffmpeg`. CI has
less: it installs `.[dev]` and nothing more, so anything the corpus loader
needs at import time has to be numpy or scipy. Hence a reader here rather than
a dependency.

**The part that cannot be settled from this side.** SPHERE is a container, and
what is inside it is named by the `sample_coding` header field. Uncompressed
`pcm` is a plain interleaved integer array behind an ASCII header and is read
below in about ten lines. `shorten`-compressed SPHERE — `sample_coding:
pcm,embedded-shorten-v2.00` and its relatives — is an entirely different
format, a Rice-coded linear-prediction codec, and is not read here. Which of
the two arrives with the licence is not something this session can find out
without the data.

So the failure is made loud and specific rather than left to surface as
nonsense audio: an unsupported coding raises `UnsupportedEncoding` naming the
coding string it found and what would decode it. If TIMIT lands compressed,
the answer is `sph2pipe -f wav` or `sox`, neither of which is installed, and
that is a thing to discover from an error message with a name in it rather
than from a filterbank producing noise.

Author:        Simon Davidson & Claude
Created:       2026-09-08
Last modified: 2026-09-08
"""
import numpy as np

SPHERE_MAGIC = b"NIST_1A"
RIFF_MAGIC = b"RIFF"


class UnsupportedEncoding(NotImplementedError):
    """The container was understood and its payload codec was not."""


def read_sphere_header(fh):
    """Parse a NIST SPHERE header from an open binary file at position 0.

    The format is fixed: the first line is `NIST_1A`, the second is the total
    header size in bytes, and the rest are `name -type value` lines terminated
    by `end_head`, padded to that size. Types are `-i` integer, `-r` real and
    `-s<n>` string of `n` bytes.

    Returns `(fields, header_size)`. The size is returned as well as consumed
    because the audio starts at exactly that offset, whatever the parser
    thought it had read — trusting the declared size over the parser's position
    is what keeps a padded or unusually formatted header from shifting every
    sample by a few bytes.
    """
    magic = fh.readline().strip()
    if magic != SPHERE_MAGIC:
        raise ValueError(f"not a NIST SPHERE file: magic {magic!r}")
    try:
        header_size = int(fh.readline().strip())
    except ValueError as exc:
        raise ValueError("SPHERE header size line is not an integer") from exc

    fields = {}
    while True:
        line = fh.readline()
        if not line:
            raise ValueError("SPHERE header ended without 'end_head'")
        text = line.decode("ascii", errors="replace").strip()
        if text == "end_head":
            break
        if not text or text.startswith(";"):
            continue
        parts = text.split(None, 2)
        if len(parts) < 3:
            continue
        name, kind, value = parts
        if kind == "-i":
            fields[name] = int(value)
        elif kind == "-r":
            fields[name] = float(value)
        elif kind.startswith("-s"):
            fields[name] = value
        else:
            fields[name] = value
    return fields, header_size


def read_sphere(path):
    """Read a NIST SPHERE file. Returns `(audio, sample_rate)`.

    `audio` is float64 in [-1, 1), scaled by 2**(8*sample_n_bytes - 1) so the
    scale does not depend on the width the corpus happens to use, and shaped
    `(n_samples,)` for one channel or `(n_channels, n_samples)` for more.
    Deinterleaving multi-channel is done here rather than left to the caller,
    since getting it wrong is silent.
    """
    with open(path, "rb") as fh:
        fields, header_size = read_sphere_header(fh)
        fh.seek(header_size)
        payload = fh.read()

    coding = str(fields.get("sample_coding", "pcm")).lower()
    if coding not in ("pcm", "pcm,embedded-none", "ulaw", "pculaw"):
        raise UnsupportedEncoding(
            f"{path}: sample_coding is {fields.get('sample_coding')!r}, which "
            "this reader does not decode. Compressed SPHERE needs sph2pipe "
            "(`sph2pipe -f wav in.wav out.wav`) or sox; neither is installed "
            "on this machine.")
    if coding in ("ulaw", "pculaw"):
        raise UnsupportedEncoding(
            f"{path}: mu-law SPHERE is not decoded here. TIMIT is linear PCM; "
            "a mu-law file means this is not the corpus that was expected.")

    n_bytes = int(fields.get("sample_n_bytes", 2))
    n_channels = int(fields.get("channel_count", 1))
    rate = int(fields.get("sample_rate", 16000))
    byte_format = str(fields.get("sample_byte_format", "01"))
    if n_bytes not in (1, 2, 4):
        raise UnsupportedEncoding(
            f"{path}: sample_n_bytes {n_bytes} is not 1, 2 or 4")

    # "01" is least-significant byte first. Anything else with more than one
    # byte is big-endian; SPHERE writes "10" for that.
    little = (n_bytes == 1) or byte_format.startswith("0")
    dtype = np.dtype("u1" if n_bytes == 1 else f"i{n_bytes}")
    if n_bytes > 1:
        dtype = dtype.newbyteorder("<" if little else ">")

    n_declared = fields.get("sample_count")
    raw = np.frombuffer(payload, dtype=dtype)
    if n_declared is not None:
        wanted = int(n_declared) * n_channels
        if raw.size < wanted:
            raise ValueError(
                f"{path}: header declares {n_declared} samples on "
                f"{n_channels} channel(s), file holds {raw.size // n_channels}")
        raw = raw[:wanted]

    if n_bytes == 1:                       # SPHERE 8-bit PCM is unsigned
        audio = (raw.astype(np.float64) - 128.0) / 128.0
    else:
        audio = raw.astype(np.float64) / float(2 ** (8 * n_bytes - 1))

    if n_channels > 1:
        audio = audio.reshape(-1, n_channels).T
    return np.ascontiguousarray(audio), rate


def read_wav(path):
    """Read a RIFF WAV file via `scipy.io.wavfile`. Returns `(audio, rate)`.

    Same normalisation and same shape convention as `read_sphere`, so a corpus
    that has been converted to WAV behind our backs reads identically to one
    that has not — which is the whole point, since some TIMIT distributions
    ship converted files under the same `.WAV` extension.
    """
    from scipy.io import wavfile
    rate, data = wavfile.read(path)
    data = np.asarray(data)
    if data.dtype.kind == "f":
        audio = data.astype(np.float64)
    elif data.dtype == np.uint8:
        audio = (data.astype(np.float64) - 128.0) / 128.0
    else:
        audio = data.astype(np.float64) / float(2 ** (8 * data.dtype.itemsize
                                                      - 1))
    if audio.ndim == 2:
        audio = audio.T
    return np.ascontiguousarray(audio), int(rate)


def read_audio(path):
    """Read SPHERE or RIFF WAV, deciding on the file's own magic number.

    The extension is not consulted. TIMIT's SPHERE files are named `.WAV`, and
    a loader that trusted the name would hand a 1024-byte ASCII header to a
    RIFF parser, or the other way round.
    """
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic == RIFF_MAGIC:
        return read_wav(path)
    if magic == SPHERE_MAGIC[:4]:
        return read_sphere(path)
    raise ValueError(
        f"{path}: not RIFF WAV and not NIST SPHERE (first four bytes "
        f"{magic!r}). If this is a FLAC or an MP3 it needs a decoder this "
        "machine does not have.")


def write_sphere(path, audio, sample_rate, sample_n_bytes=2,
                 header_size=1024, extra_fields=None):
    """Write an uncompressed SPHERE file — for tests, and for nothing else.

    The reader above cannot be tested against TIMIT, which is not here and may
    never be licensed. What it can be tested against is a file this function
    wrote, which is only worth something because the header it writes is built
    from the format description rather than from the parser: the two halves are
    written to agree with the *specification*, not with each other.
    """
    audio = np.atleast_2d(np.asarray(audio, dtype=np.float64))
    n_channels, n_samples = audio.shape
    scale = float(2 ** (8 * sample_n_bytes - 1))
    ints = np.clip(np.round(audio * scale), -scale, scale - 1)
    data = ints.T.reshape(-1).astype(f"<i{sample_n_bytes}")

    fields = {
        "sample_count": ("-i", n_samples),
        "sample_n_bytes": ("-i", sample_n_bytes),
        "channel_count": ("-i", n_channels),
        "sample_rate": ("-i", int(sample_rate)),
        "sample_byte_format": ("-s2", "01"),
        "sample_sig_bits": ("-i", 8 * sample_n_bytes),
        "sample_coding": ("-s3", "pcm"),
    }
    for name, (kind, value) in (extra_fields or {}).items():
        fields[name] = (kind, value)

    body = "".join(f"{n} {k} {v}\n" for n, (k, v) in fields.items())
    header = f"NIST_1A\n{header_size:>7}\n{body}end_head\n"
    if len(header) > header_size:
        raise ValueError("header does not fit the declared size")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii").ljust(header_size, b" "))
        fh.write(data.tobytes())
    return path
