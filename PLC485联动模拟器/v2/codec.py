# -*- coding: utf-8 -*-
"""
② 帧编解码 Codec —— 拿到手册后照着「帧格式」改这里

引擎只认这几个接口，换协议 = 换一个 Codec 类：
  encode_request(req)              主站(PLC)：请求 → 字节
  decode_request(raw)              从站(温水器)：字节 → 请求
  encode_response(req, ok, ...)    从站：结果 → 字节
  decode_response(raw, req)        主站：字节 → 结果
  fields(raw, is_response)         逐字段拆开（详情面板用）
  silent_on_bad_frame              校验错时从站是回 NAK 还是不吭声

这里放了两个实现：
  AsciiBccCodec  虚构协议 v2（ASCII + BCC，参数号式，接近日本厂家常见风格）
  ModbusRtuCodec Modbus RTU（二进制 + CRC16）—— 证明同一个引擎两种协议都能跑
"""
from command_table import PARAMS

STX, ETX, ACK, NAK = 0x02, 0x03, 0x06, 0x15


class Request:
    def __init__(self, addr, op, param, value=None):
        self.addr = addr      # 站号 int
        self.op = op          # 'R' 读 / 'W' 写
        self.param = param    # 参数号 str，如 '010'
        self.value = value    # 写入的原始整数

    def __repr__(self):
        return 'Request(%d,%s,%s,%r)' % (self.addr, self.op, self.param, self.value)


class Response:
    def __init__(self, ok, value=None, err=None, check_ok=True):
        self.ok = ok              # True=ACK  False=NAK/异常
        self.value = value        # 读到的原始整数
        self.err = err            # 错误码 '01'~'06'
        self.check_ok = check_ok  # 校验是否通过 / 帧是否对得上

    def __repr__(self):
        return 'Response(ok=%s,value=%r,err=%r,check=%s)' % (self.ok, self.value, self.err, self.check_ok)


def hexs(bs):
    return ' '.join('%02X' % b for b in bs)


# ============================================================
#  虚构协议 v2
# ============================================================
class AsciiBccCodec:
    """
    请求: STX | 站号(2) | R/W(1) | 参数号(3) | [数据(width)] | ETX | BCC
    响应: STX | 站号(2) | R/W(1) | 参数号(3) | ACK/NAK(1) | [数据 或 错误码(2)] | ETX | BCC
    BCC = 站号 ~ ETX 的 XOR；除 STX/ETX/ACK/NAK/BCC 外全是 ASCII
    """
    name = '虚构协议 v2（ASCII+BCC）'
    silent_on_bad_frame = False

    @staticmethod
    def bcc(body):
        x = 0
        for b in body:
            x ^= b
        return x

    def _fmt(self, p, v):
        return ('%0*X' if p.fmt == 'hex' else '%0*d') % (p.width, v)

    def _val(self, p, s):
        return int(s, 16 if p.fmt == 'hex' else 10)

    def _wrap(self, body):
        body = body + bytes([ETX])
        return bytes([STX]) + body + bytes([self.bcc(body)])

    def encode_request(self, req):
        body = ('%02d%s%s' % (req.addr, req.op, req.param)).encode()
        if req.op == 'W':
            body += self._fmt(PARAMS[req.param], req.value).encode()
        return self._wrap(body)

    def decode_request(self, raw):
        """返回 (Request 或 None, 校验OK?)"""
        if len(raw) < 9 or raw[0] != STX or raw[-2] != ETX:
            return None, False
        ok = raw[-1] == self.bcc(raw[1:-1])
        try:
            addr = int(raw[1:3].decode())
            op = chr(raw[3])
            param = raw[4:7].decode()
            data = raw[7:-2].decode()
            p = PARAMS.get(param)
            val = self._val(p, data) if (op == 'W' and p and data) else None
        except Exception:
            return None, False
        return Request(addr, op, param, val), ok

    def encode_response(self, req, ok, value=None, err=None):
        body = ('%02d%s%s' % (req.addr, req.op, req.param)).encode()
        body += bytes([ACK if ok else NAK])
        if ok and req.op == 'R':
            body += self._fmt(PARAMS[req.param], value).encode()
        elif not ok:
            body += (err or '01').encode()
        return self._wrap(body)

    def decode_response(self, raw, req):
        if len(raw) < 10 or raw[0] != STX or raw[-2] != ETX:
            return Response(False, err='01', check_ok=False)
        if raw[-1] != self.bcc(raw[1:-1]):
            return Response(False, err='01', check_ok=False)
        head = ('%02d%s%s' % (req.addr, req.op, req.param)).encode()
        if raw[1:7] != head:
            return Response(False, err='01', check_ok=False)
        data = raw[8:-2].decode()
        if raw[7] == ACK:
            v = self._val(PARAMS[req.param], data) if req.op == 'R' else None
            return Response(True, value=v)
        return Response(False, err=data)

    def fields(self, raw, is_response):
        out = [('STX', hexs(raw[0:1]), '帧头')]
        if len(raw) < 9:
            return out + [('?', hexs(raw[1:]), '帧太短')]
        out.append(('站号', hexs(raw[1:3]), "'%s'" % raw[1:3].decode(errors='replace')))
        op = chr(raw[3])
        out.append(('读写', hexs(raw[3:4]), "'%s' %s" % (op, '读' if op == 'R' else '写')))
        pc = raw[4:7].decode(errors='replace')
        p = PARAMS.get(pc)
        out.append(('参数', hexs(raw[4:7]), "'%s' %s" % (pc, p.name if p else '?')))
        if is_response:
            a = raw[7]
            out.append(('结果', hexs(raw[7:8]), 'ACK 正常' if a == ACK else 'NAK 拒绝'))
            data = raw[8:-2]
            ds = data.decode(errors='replace')
            if a != ACK:
                from command_table import NAK as N
                meaning = "'%s' %s" % (ds, N.get(ds, '?'))
            elif ds and p:
                meaning = "'%s' %s" % (ds, p.describe(self._val(p, ds)))
            else:
                meaning = '(无)'
        else:
            data = raw[7:-2]
            ds = data.decode(errors='replace')
            meaning = "'%s' %s" % (ds, p.describe(self._val(p, ds))) if (ds and p) else '(无)'
        out.append(('数据', hexs(data) or '-', meaning))
        out.append(('ETX', hexs(raw[-2:-1]), '帧尾'))
        calc = self.bcc(raw[1:-1])
        out.append(('BCC', hexs(raw[-1:]), 'XOR 计算=%02X %s' % (calc, '✓' if calc == raw[-1] else '× 不符')))
        return out


# ============================================================
#  Modbus RTU（示例：同一个引擎换协议）
# ============================================================
class ModbusRtuCodec:
    """
    读: 站号 | 03 | 寄存器(2) | 个数(2)=1 | CRC16(2, 低字节在前)
    写: 站号 | 06 | 寄存器(2) | 数值(2)            | CRC16
    读响应: 站号 | 03 | 字节数=2 | 数值(2) | CRC
    写响应: 原样回显
    异常:   站号 | 功能码|0x80 | 异常码 | CRC
    CRC 错 → 从站不回（Modbus 规定），主站只能超时
    参数号直接当寄存器地址（'010' → 10）
    """
    name = 'Modbus RTU（二进制+CRC16）'
    silent_on_bad_frame = True

    @staticmethod
    def crc16(data):
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc

    def _wrap(self, body):
        c = self.crc16(body)
        return bytes(body) + bytes([c & 0xFF, c >> 8])

    def _crc_ok(self, raw):
        return len(raw) >= 4 and self.crc16(raw[:-2]) == (raw[-2] | raw[-1] << 8)

    def encode_request(self, req):
        reg = int(req.param)
        if req.op == 'R':
            return self._wrap([req.addr, 0x03, reg >> 8, reg & 0xFF, 0, 1])
        v = req.value & 0xFFFF
        return self._wrap([req.addr, 0x06, reg >> 8, reg & 0xFF, v >> 8, v & 0xFF])

    def decode_request(self, raw):
        if len(raw) != 8:
            return None, False
        ok = self._crc_ok(raw)
        fc = raw[1]
        reg = '%03d' % (raw[2] << 8 | raw[3])
        if fc == 0x03:
            return Request(raw[0], 'R', reg), ok
        if fc == 0x06:
            return Request(raw[0], 'W', reg, raw[4] << 8 | raw[5]), ok
        return None, ok

    def encode_response(self, req, ok, value=None, err=None):
        fc = 0x03 if req.op == 'R' else 0x06
        if not ok:
            return self._wrap([req.addr, fc | 0x80, int(err or '01')])
        if req.op == 'R':
            return self._wrap([req.addr, 0x03, 2, value >> 8 & 0xFF, value & 0xFF])
        return self.encode_request(req)  # 写响应 = 回显

    def decode_response(self, raw, req):
        if not self._crc_ok(raw) or raw[0] != req.addr:
            return Response(False, err='01', check_ok=False)
        fc = 0x03 if req.op == 'R' else 0x06
        if raw[1] == fc | 0x80:
            return Response(False, err='%02d' % raw[2])
        if raw[1] != fc:
            return Response(False, err='01', check_ok=False)
        if req.op == 'R':
            return Response(True, value=raw[3] << 8 | raw[4])
        return Response(True)

    def fields(self, raw, is_response):
        from command_table import NAK as N
        if len(raw) < 4:
            return [('?', hexs(raw), '帧太短')]
        out = [('站号', hexs(raw[0:1]), str(raw[0]))]
        fc = raw[1]
        names = {0x03: '读保持寄存器', 0x06: '写单个寄存器'}
        if fc & 0x80:
            out.append(('功能码', hexs(raw[1:2]), '异常响应 (%02X|80)' % (fc & 0x7F)))
            out.append(('异常码', hexs(raw[2:3]), '%02d %s' % (raw[2], N.get('%02d' % raw[2], '?'))))
        elif fc == 0x03 and is_response:
            out.append(('功能码', hexs(raw[1:2]), names[fc]))
            out.append(('字节数', hexs(raw[2:3]), str(raw[2])))
            out.append(('数值', hexs(raw[3:5]), str(raw[3] << 8 | raw[4])))
        else:
            reg = raw[2] << 8 | raw[3]
            p = PARAMS.get('%03d' % reg)
            out.append(('功能码', hexs(raw[1:2]), names.get(fc, '?')))
            out.append(('寄存器', hexs(raw[2:4]), '%d %s' % (reg, p.name if p else '?')))
            v = raw[4] << 8 | raw[5]
            out.append(('个数' if fc == 0x03 else '数值', hexs(raw[4:6]),
                        str(v) if fc == 0x03 or not p else p.describe(v)))
        calc = self.crc16(raw[:-2])
        got = raw[-2] | raw[-1] << 8
        out.append(('CRC', hexs(raw[-2:]), '计算=%04X %s' % (calc, '✓' if calc == got else '× 不符')))
        return out


CODECS = [AsciiBccCodec(), ModbusRtuCodec()]
