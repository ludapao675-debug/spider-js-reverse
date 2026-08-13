import base64, random

def _pkcs1_pad2(data: bytes, key_size: int) -> int:
    if key_size < len(data) + 11:
        raise ValueError('密钥太短')
    buf = bytearray(key_size); i = len(data) - 1
    while i >= 0 and key_size > 0:
        buf[key_size-1] = data[i]; key_size -= 1; i -= 1
    key_size -= 1; buf[key_size] = 0
    while key_size > 2:
        key_size -= 1; buf[key_size] = random.randint(1, 254)
    key_size -= 1; buf[key_size] = 2
    key_size -= 1; buf[key_size] = 0
    return int.from_bytes(bytes(buf), 'big')

def rsa_encrypt_steam(password: str, mod_hex: str, exp_hex: str) -> str:
    n = int(mod_hex, 16); e = int(exp_hex, 16)
    key_size = (n.bit_length() + 7) >> 3
    data = password.encode('latin-1') if all(ord(c) < 256 for c in password) else password.encode('utf-8')
    m = _pkcs1_pad2(data, key_size)
    c = pow(m, e, n)
    h = format(c, 'x')
    if len(h) & 1: h = '0' + h
    return base64.b64encode(bytes.fromhex(h)).decode('ascii')


# ============================================================================
# Steam 线上登录已升级为 IAuthenticationService WebAPI + protobuf 传输
# （BeginAuthSessionViaCredentials），不再走经典 /login/getrsakey/ 表单 POST。
# 下面按实测拦截的 protobuf 字段号，构造 input_protobuf_encoded 请求体。
# 实证来源：listener 请求 25880.320 / 25880.355（信任点击）解析结果。
# ============================================================================

def _encode_varint(value: int) -> bytes:
    """编码一个 protobuf varint。"""
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _bytes_field(field_no: int, data: bytes) -> bytes:
    """构造 wire_type=2（length-delimited）字段。"""
    return _encode_varint((field_no << 3) | 2) + _encode_varint(len(data)) + data


def _varint_field(field_no: int, value: int) -> bytes:
    """构造 wire_type=0（varint）字段。"""
    return _encode_varint((field_no << 3) | 0) + _encode_varint(value)


# 实测两次拦截（合成点击 / 信任点击）均出现的协议常量，保持原值以兼容线上结构
_PROTO_CONSTANTS = {
    5: 1,    # 登录方式枚举（密码登录 = 1）
    7: 1,    # 保留标志位
    11: 6,   # 设备/客户端类型枚举
}

# field#9（UA）在真实捕获样本里并非纯 UA，而是 115 字节：
#   b'\n' + 标准 Chrome UA + b'\x10\x02'
# 末尾两字节 \x10\x02 是 Steam 客户端序列化时写入的固有后缀，
# 缺少它（或把它当作独立 field#2）服务端会返回 400 Invalid input_protobuf_encoded。
FIELD9_BYTES = (b"\noMozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               b"(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36\x10\x02")


def build_begin_auth_protobuf(account_name: str,
                               encrypted_password_b64: str,
                               encryption_timestamp: int,
                               user_agent: str = '',
                               platform: str = 'Store') -> bytes:
    """拼装 BeginAuthSessionViaCredentials 的 protobuf 请求体（input_protobuf_encoded 解码前的原始字节）。

    :param account_name: 账号（实测对应 field#2 = 'test_reverse_probe'）
    :param encrypted_password_b64: RSA PKCS#1 v1.5 密文的 base64（rsa_encrypt_steam 的输出，对应 field#3）
    :param encryption_timestamp: GetPasswordRSAPublicKey 响应返回的 timestamp（field#3），对应请求 field#4（varint）
    :param user_agent: 保留参数（field#9 已硬编码为真实捕获的 115 字节结构，含 \\n 前缀与 \\x10\\x02 后缀）
    :param platform: 平台标识，实测为 'Store'（field#8）
    :return: protobuf 编码后的字节
    """
    parts = [
        _bytes_field(2, account_name.encode('utf-8')),
        _bytes_field(3, encrypted_password_b64.encode('ascii')),   # field#3 = base64 RSA 密文（344 字节）
        _varint_field(4, int(encryption_timestamp)),
        _bytes_field(8, platform.encode('utf-8')),
        _bytes_field(9, FIELD9_BYTES),                              # field#9 = UA（含 \n 前缀 + \x10\x02 后缀）
    ]
    for fno, val in _PROTO_CONSTANTS.items():
        parts.append(_varint_field(fno, val))
    return b''.join(parts)


def build_begin_auth_request_body(account_name: str,
                                   encrypted_password_b64: str,
                                   encryption_timestamp: int,
                                   user_agent: str,
                                   platform: str = 'Store') -> str:
    """返回可直接放入 POST body 的 input_protobuf_encoded（base64 字符串）。"""
    return base64.b64encode(
        build_begin_auth_protobuf(account_name, encrypted_password_b64,
                                  encryption_timestamp, user_agent, platform)
    ).decode('ascii')


def build_steam_webapi_login(account_name: str,
                             password: str,
                             mod_hex: str,
                             exp_hex: str,
                             encryption_timestamp: int,
                             user_agent: str,
                             platform: str = 'Store') -> str:
    """一站式：RSA 加密密码 → 拼装 WebAPI protobuf → 返回 input_protobuf_encoded。

    注意：mod_hex/exp_hex/encryption_timestamp 三者均来自 BeginAuthSession 握手响应，
    沙箱探针页未建立有效会话时取不到真实值，本地复现需以 (mod_hex, exp_hex, timestamp) 为输入。
    """
    cipher_b64 = rsa_encrypt_steam(password, mod_hex, exp_hex)
    return build_begin_auth_request_body(account_name, cipher_b64,
                                          encryption_timestamp, user_agent, platform)
