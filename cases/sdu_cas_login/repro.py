"""
SDU CAS (山东大学统一身份认证) 登录参数本地复现
================================================

目标字段: 表单提交时的 `#rsa`
来源分析 (从零重测, 不依赖旧 case):
  - 页面 login.js?v=3.0 的 login() 中:
        $("#rsa").val(strEnc(u + p + lt, '1', '2', '3'));
        // u=用户名(明文) p=密码(明文) lt=登录票据
   随后 POST /cas/device (设备指纹, 服务器常返 500 仅 UX 网关),
   返回 info=='pass'||'binded' 时才 $("#loginForm")[0].submit()
   提交 POST /cas/login, 报文体为:
        un=<明文> & pd=<明文> & rsa=<密文> & ul=<u长度> & pl=<p长度>
        & lt=<票据> & execution=<e1s1> & _eventId=submit
   注意: 用户名/密码本身以明文提交, 仅 rsa 是 (u+p+lt) 的密文。

算法: strEnc 来自 des.js (Guapo, 2006)。这不是标准 3DES API,
而是"按字符拆 key + 逐 4 字节做三次 DES 串联"的自定义实现:
  1. 每个 key 字符串按 4 字符切片, 每片经 strToBt 变成 64-bit DES 密钥
     (单字符 key '1' => 仅 1 个 64-bit 密钥, 高位 48bit=0, 低 16bit=ord('1'))
  2. 明文按 4 字符分块, 每块 strToBt 成 64-bit, 依次用
     enc(key1) -> enc(key2) -> enc(key3) 做三轮 DES (ECB 风格, 无 IV)
  3. 每块结果 bt64ToHex 拼接成十六进制密文

本文件为 des.js 的逐行 Python 移植, 不依赖任何第三方库, 可直接离线运行。
"""

# ---------------------------------------------------------------------------
# des.js 逐函数移植 (纯整数位运算, 0/1 数组)
# ---------------------------------------------------------------------------

def _str_to_bt(s):
    """把 <=4 字符的字符串变成 64-bit (int 数组)。不足 4 字符用 0 填充。"""
    leng = len(s)
    bt = [0] * 64
    if leng < 4:
        for i in range(leng):
            k = ord(s[i])
            for j in range(16):
                pow_ = 2 ** (15 - j)
                bt[16 * i + j] = (k // pow_) % 2
        for p in range(leng, 4):
            k = 0
            for q in range(16):
                pow_ = 2 ** (15 - q)
                bt[16 * p + q] = (k // pow_) % 2
    else:
        for i in range(4):
            k = ord(s[i])
            for j in range(16):
                pow_ = 2 ** (15 - j)
                bt[16 * i + j] = (k // pow_) % 2
    return bt


def _bt64_to_hex(byte_data):
    """64-bit 数组 -> 16 位十六进制串。"""
    hexs = ""
    for i in range(16):
        chunk = byte_data[i * 4:i * 4 + 4]
        hexs += format(int("".join(str(b) for b in chunk), 2), "X")
    return hexs


def _hex_to_bt64(hexs):
    """16 位十六进制串 -> 64-bit 数组。"""
    binary = ""
    for i in range(16):
        binary += format(int(hexs[i], 16), "04b")
    return [int(c) for c in binary]


def _get_key_bytes(key):
    """key 按 4 字符切片, 每片 strToBt 成一个 64-bit 密钥。"""
    key_bytes = []
    leng = len(key)
    iterator = leng // 4
    remainder = leng % 4
    for i in range(iterator):
        key_bytes.append(_str_to_bt(key[i * 4:i * 4 + 4]))
    if remainder > 0:
        key_bytes.append(_str_to_bt(key[iterator * 4:leng]))
    return key_bytes


# S-Box 表 (与 des.js 完全一致)
_S1 = [[14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7],
       [0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8],
       [4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0],
       [15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13]]
_S2 = [[15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10],
       [3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5],
       [0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15],
       [13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9]]
_S3 = [[10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8],
       [13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1],
       [13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7],
       [1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12]]
_S4 = [[7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15],
       [13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9],
       [10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4],
       [3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14]]
_S5 = [[2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9],
       [14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6],
       [4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14],
       [11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3]]
_S6 = [[12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11],
       [10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8],
       [9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6],
       [4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13]]
_S7 = [[4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1],
       [13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6],
       [1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2],
       [6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12]]
_S8 = [[13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7],
       [1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2],
       [7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8],
       [2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11]]
_S_BOXES = [_S1, _S2, _S3, _S4, _S5, _S6, _S7, _S8]

_PBOX = [15, 6, 19, 20, 28, 11, 27, 16, 0, 14, 22, 25, 4, 17, 30, 9,
         1, 7, 23, 13, 31, 26, 2, 8, 18, 12, 29, 5, 21, 10, 3, 24]

_FP = [39, 7, 47, 15, 55, 23, 63, 31, 38, 6, 46, 14, 54, 22, 62, 30,
       37, 5, 45, 13, 53, 21, 61, 29, 36, 4, 44, 12, 52, 20, 60, 28,
       35, 3, 43, 11, 51, 19, 59, 27, 34, 2, 42, 10, 50, 18, 58, 26,
       33, 1, 41, 9, 49, 17, 57, 25, 32, 0, 40, 8, 48, 16, 56, 24]


def _xor(b1, b2):
    return [b1[i] ^ b2[i] for i in range(len(b1))]


def _s_box_permute(expand_byte):
    s_box_byte = [0] * 32
    for m in range(8):
        i = expand_byte[m * 6 + 0] * 2 + expand_byte[m * 6 + 5]
        j = (expand_byte[m * 6 + 1] * 8 +
             expand_byte[m * 6 + 2] * 4 +
             expand_byte[m * 6 + 3] * 2 +
             expand_byte[m * 6 + 4])
        val = _S_BOXES[m][i][j]
        binary = format(val, "04b")
        s_box_byte[m * 4 + 0] = int(binary[0])
        s_box_byte[m * 4 + 1] = int(binary[1])
        s_box_byte[m * 4 + 2] = int(binary[2])
        s_box_byte[m * 4 + 3] = int(binary[3])
    return s_box_byte


def _p_permute(s_box_byte):
    return [s_box_byte[src] for src in _PBOX]


def _init_permute(original):
    ip = [0] * 64
    for i in range(4):
        m = 1 + 2 * i
        n = 0 + 2 * i
        for j in range(8):
            k = 7 - j
            ip[i * 8 + k] = original[j * 8 + m]
            ip[i * 8 + k + 32] = original[j * 8 + n]
    return ip


def _expand_permute(right):
    ep = [0] * 48
    for i in range(8):
        if i == 0:
            ep[i * 6 + 0] = right[31]
        else:
            ep[i * 6 + 0] = right[i * 4 - 1]
        ep[i * 6 + 1] = right[i * 4 + 0]
        ep[i * 6 + 2] = right[i * 4 + 1]
        ep[i * 6 + 3] = right[i * 4 + 2]
        ep[i * 6 + 4] = right[i * 4 + 3]
        if i == 7:
            ep[i * 6 + 5] = right[0]
        else:
            ep[i * 6 + 5] = right[i * 4 + 4]
    return ep


def _finally_permute(end):
    return [end[src] for src in _FP]


def _generate_keys(key_byte):
    key = [0] * 56
    keys = [[0] * 48 for _ in range(16)]
    loop = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]
    for i in range(7):
        for j in range(8):
            k = 7 - j
            key[i * 8 + j] = key_byte[8 * k + i]
    for i in range(16):
        temp_left = 0
        temp_right = 0
        for _ in range(loop[i]):
            temp_left = key[0]
            temp_right = key[28]
            for k in range(27):
                key[k] = key[k + 1]
                key[28 + k] = key[29 + k]
            key[27] = temp_left
            key[55] = temp_right
        temp_key = [
            key[13], key[16], key[10], key[23], key[0], key[4], key[2], key[27],
            key[14], key[5], key[20], key[9], key[22], key[18], key[11], key[3],
            key[25], key[7], key[15], key[6], key[26], key[19], key[12], key[1],
            key[40], key[51], key[30], key[36], key[46], key[54], key[29], key[39],
            key[50], key[44], key[32], key[47], key[43], key[48], key[38], key[55],
            key[33], key[52], key[45], key[41], key[49], key[35], key[28], key[31],
        ]
        keys[i] = temp_key
    return keys


def _enc(data_byte, key_byte):
    keys = _generate_keys(key_byte)
    ip = _init_permute(data_byte)
    ip_left = ip[0:32]
    ip_right = ip[32:64]
    for i in range(16):
        temp_left = ip_left[:]
        ip_left = ip_right[:]
        key = keys[i]
        temp_right = _xor(
            _p_permute(_s_box_permute(_xor(_expand_permute(ip_right), key))),
            temp_left,
        )
        ip_right = temp_right
    final_data = ip_right + ip_left
    return _finally_permute(final_data)


def _dec(data_byte, key_byte):
    keys = _generate_keys(key_byte)
    ip = _init_permute(data_byte)
    ip_left = ip[0:32]
    ip_right = ip[32:64]
    for i in range(15, -1, -1):
        temp_left = ip_left[:]
        ip_left = ip_right[:]
        key = keys[i]
        temp_right = _xor(
            _p_permute(_s_box_permute(_xor(_expand_permute(ip_right), key))),
            temp_left,
        )
        ip_right = temp_right
    final_data = ip_right + ip_left
    return _finally_permute(final_data)


def _enc_chain(bt, first_kb, second_kb, third_kb):
    temp = bt
    for x in range(len(first_kb)):
        temp = _enc(temp, first_kb[x])
    for y in range(len(second_kb)):
        temp = _enc(temp, second_kb[y])
    for z in range(len(third_kb)):
        temp = _enc(temp, third_kb[z])
    return temp


def _byte_to_string(byte_data):
    s = ""
    for i in range(4):
        count = 0
        for j in range(16):
            pow_ = 2 ** (15 - j)
            count += byte_data[16 * i + j] * pow_
        if count != 0:
            s += chr(count)
    return s


def str_enc(data, first_key="1", second_key="2", third_key="3"):
    """等价 des.js 的 strEnc: 对 data 做三次 DES 串联, 输出十六进制密文。"""
    leng = len(data)
    enc_data = ""
    first_kb = _get_key_bytes(first_key) if first_key else []
    second_kb = _get_key_bytes(second_key) if second_key else []
    third_kb = _get_key_bytes(third_key) if third_key else []
    if leng > 0:
        if leng < 4:
            bt = _str_to_bt(data)
            enc_byte = _enc_chain(bt, first_kb, second_kb, third_kb)
            enc_data = _bt64_to_hex(enc_byte)
        else:
            iterator = leng // 4
            remainder = leng % 4
            for i in range(iterator):
                temp_byte = _str_to_bt(data[i * 4:i * 4 + 4])
                enc_byte = _enc_chain(temp_byte, first_kb, second_kb, third_kb)
                enc_data += _bt64_to_hex(enc_byte)
            if remainder > 0:
                temp_byte = _str_to_bt(data[iterator * 4:leng])
                enc_byte = _enc_chain(temp_byte, first_kb, second_kb, third_kb)
                enc_data += _bt64_to_hex(enc_byte)
    return enc_data


def str_dec(data, first_key="1", second_key="2", third_key="3"):
    """等价 des.js 的 strDec: 十六进制密文 -> 原文。"""
    first_kb = _get_key_bytes(first_key) if first_key else []
    second_kb = _get_key_bytes(second_key) if second_key else []
    third_kb = _get_key_bytes(third_key) if third_key else []
    iterator = len(data) // 16
    dec_str = ""
    for i in range(iterator):
        str_byte = _hex_to_bt64(data[i * 16:i * 16 + 16])
        temp = str_byte
        for x in range(len(third_kb) - 1, -1, -1):
            temp = _dec(temp, third_kb[x])
        for y in range(len(second_kb) - 1, -1, -1):
            temp = _dec(temp, second_kb[y])
        for z in range(len(first_kb) - 1, -1, -1):
            temp = _dec(temp, first_kb[z])
        dec_str += _byte_to_string(temp)
    return dec_str


# ---------------------------------------------------------------------------
# SDU CAS 登录请求构造
# ---------------------------------------------------------------------------

def build_login_form(username, password, lt, execution="e1s1"):
    """构造 POST /cas/login 的表单字段 (application/x-www-form-urlencoded)。

    返回 dict。注意: un/pd 为明文, rsa 为 (u+p+lt) 的三次 DES 密文。
    """
    rsa = str_enc(username + password + lt, "1", "2", "3")
    return {
        "un": username,
        "pd": password,
        "rsa": rsa,
        "ul": str(len(username)),
        "pl": str(len(password)),
        "lt": lt,
        "execution": execution,
        "_eventId": "submit",
    }


# ---------------------------------------------------------------------------
# 自验证: 与浏览器实测样本对照
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # 来自浏览器实时调用 strEnc 的对照样本 (page_run_js 直接读取)
    LIVE = {
        "test": ("test", "D8D35E5019288C41"),
        "login": (
            "testuser2026TestPass@2026LT-15032-LXgE3DgkJjVpMvPVBrenqLCaPTEK3B-cas",
            "D8D35E5019288C41EB6D16D13160C8DCC052CA90C48D9C76C0A5C6CA237A670E"
            "7D6B982EC91FCCA42B11E22B27621867B241A05DC47982363486A4B40E4F011C"
            "340252CBB0F2E1A322034BE890C541F44959BA30141251D7191ED287ED01906F"
            "F9F3527C14F227860DE28EB25BA3193499F94081B0024048E533B410911962A1"
            "8AB35967D5AA0BA7",
        ),
    }

    ok = True
    for name, (plain, expect) in LIVE.items():
        got = str_enc(plain, "1", "2", "3")
        match = got == expect
        ok = ok and match
        rt = str_dec(got, "1", "2", "3")
        print(f"[{'OK' if match else 'FAIL'}] strEnc({name!r}) len={len(got)}")
        print(f"      expect={expect}")
        print(f"      got   ={got}")
        print(f"      round-trip ok={rt == plain}")

    print("\n=== ALL MATCH ===" if ok else "\n=== MISMATCH ===")

    # 演示: 构造一次登录表单
    form = build_login_form(
        "testuser2026",
        "TestPass@2026",
        "LT-15032-LXgE3DgkJjVpMvPVBrenqLCaPTEK3B-cas",
        "e1s1",
    )
    print("\n登录表单字段:")
    for k, v in form.items():
        print(f"  {k} = {v}")
