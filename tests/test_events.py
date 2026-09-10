from fbot.events import RawEvent, encode, decode


def test_roundtrip_preserves_raw_bytes_exactly():
    raw = b'{"stream":"btcusdt@aggTrade","data":{"e":"aggTrade","E":1,"p":"1.10","q":"0.001000"}}'
    ev = RawEvent(seq=7, recv_ns=1789025312145000123, mono_ns=42, cat="market", stream="btcusdt@aggTrade", raw=raw)
    line = encode(ev)
    assert line.endswith(b"\n")
    back = decode(line)
    assert back == ev
    assert back.raw is not raw or back.raw == raw  # içerik aynı


def test_encode_header_field_order_is_fixed():
    ev = RawEvent(1, 2, 3, "ctrl", "connect", b'{"k":1}')
    assert encode(ev) == b'{"q":1,"r":2,"m":3,"c":"ctrl","s":"connect","d":{"k":1}}\n'


def test_decode_rejects_malformed():
    import pytest
    with pytest.raises(ValueError):
        decode(b'{"q":1}\n')


def test_stream_name_from_combined_frame():
    from fbot.events import stream_of
    assert stream_of(b'{"stream":"ethusdt@depth@100ms","data":{}}') == "ethusdt@depth@100ms"
    assert stream_of(b'{"result":null,"id":1}') is None
