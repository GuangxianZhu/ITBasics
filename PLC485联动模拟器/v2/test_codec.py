# -*- coding: utf-8 -*-
"""协议框架的单元测试：python test_codec.py"""
from codec import AsciiBccCodec, ModbusRtuCodec, Request, hexs


def roundtrip(c):
    for req, ok, val, err in [
        (Request(1, 'R', '100'), True, 553, None),
        (Request(1, 'R', '101'), True, 0x1F, None),
        (Request(1, 'W', '010'), True, None, None),
        (Request(1, 'W', '002'), False, None, '02'),
    ]:
        if req.op == 'W':
            req.value = 550 if req.param == '010' else 1
        raw = c.encode_request(req)
        back, chk = c.decode_request(raw)
        assert chk and back.op == req.op and back.param == req.param and back.value == req.value, (raw, back)
        rsp = c.encode_response(req, ok, val, err)
        r = c.decode_response(rsp, req)
        assert r.check_ok and r.ok == ok and (r.value == val if req.op == 'R' and ok else True), r
        if not ok:
            assert r.err == err, r
        bad = rsp[:-1] + bytes([rsp[-1] ^ 0x5A])
        assert not c.decode_response(bad, req).check_ok
        c.fields(raw, False)
        c.fields(rsp, True)
        print('  %-26s %-40s → %s' % (c.name, hexs(raw), hexs(rsp)))


def test_modbus_crc_known():
    # 经典例子：01 03 00 00 00 01 → CRC 84 0A
    raw = ModbusRtuCodec().encode_request(Request(1, 'R', '000'))
    assert raw[-2:] == bytes([0x84, 0x0A]), hexs(raw)


if __name__ == '__main__':
    for c in (AsciiBccCodec(), ModbusRtuCodec()):
        roundtrip(c)
    test_modbus_crc_known()
    print('全部通过')
