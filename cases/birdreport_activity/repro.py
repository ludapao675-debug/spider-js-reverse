import json
import time
import uuid
import hashlib
import base64
import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import unpad

# 1. 配置参数
RSA_PUBKEY_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCvxXa98E1uWXnBzXkS2yHUfnBM
6n3PCwLdfIox03T91joBvjtoDqiQ5x3tTOfpHs3LtiqMMEafls6b0YWtgB1dse1W5
m+FpeusVkCOkQxB4SZDH6tuerIknnmB/Hsq5wgEkIvO5Pff9biig6AyoAkdWpSek/
1/B7zYIepYY0lxKQIDAQAB
-----END PUBLIC KEY-----"""

AES_KEY_HEX = "6756696653534952657053656868665752665050485566485667545454484967"
AES_IV_HEX = "53536868555767547048526949655455"

# 2. 规则实现
def sort_ascii_json(data_dict):
    """按键名 ASCII 升序排序并格式化为 JSON 字符串"""
    sorted_dict = {k: data_dict[k] for k in sorted(data_dict.keys())}
    return json.dumps(sorted_dict, separators=(',', ':'))

def rsa_encrypt_long(plaintext_str, pubkey_pem):
    """模拟 JS 的 JSEncrypt.encryptLong 117字节分段加密"""
    rsa_key = RSA.import_key(pubkey_pem)
    cipher = PKCS1_v1_5.new(rsa_key)
    
    hex_result = ""
    for i in range(0, len(plaintext_str), 117):
        chunk = plaintext_str[i:i+117].encode('utf-8')
        enc_chunk = cipher.encrypt(chunk)
        hex_result += enc_chunk.hex()
        
    raw_bytes = bytes.fromhex(hex_result)
    return base64.b64encode(raw_bytes).decode('utf-8')

def md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def decrypt_response(encrypted_b64):
    """AES-CBC 解密响应体"""
    key = bytes.fromhex(AES_KEY_HEX)
    iv = bytes.fromhex(AES_IV_HEX)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    missing_padding = len(encrypted_b64) % 4
    if missing_padding:
        encrypted_b64 += '=' * (4 - missing_padding)
    raw_data = base64.b64decode(encrypted_b64)
    decrypted_bytes = unpad(cipher.decrypt(raw_data), AES.block_size)
    return decrypted_bytes.decode('utf-8')

def get_activity_data(page=1, limit=20):
    url = "https://api.birdreport.cn/front/activity/search"
    
    payload_dict = {
        "page": str(page),
        "limit": str(limit),
        "mode": "0"
    }
    
    sorted_json_str = sort_ascii_json(payload_dict)
    timestamp = int(time.time() * 1000)
    request_id = str(uuid.uuid4())
    
    encrypted_payload = rsa_encrypt_long(sorted_json_str, RSA_PUBKEY_PEM)
    sign = md5(sorted_json_str + request_id + str(timestamp))
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "*/*",
        "Origin": "https://www.birdreport.cn",
        "Referer": "https://www.birdreport.cn/",
        "timestamp": str(timestamp),
        "requestId": request_id,
        "sign": sign
    }
    
    response = requests.post(url, data=encrypted_payload, headers=headers)
    print(f"HTTP Status: {response.status_code}")
    res_json = response.json()
    
    if res_json.get("code") == 200 and "data" in res_json:
        decrypted_str = decrypt_response(res_json["data"])
        decrypted_data = json.loads(decrypted_str)
        print("解密成功！响应数据预览：")
        print(json.dumps(decrypted_data[:2] if isinstance(decrypted_data, list) else decrypted_data, ensure_ascii=False, indent=2))
        return decrypted_data
    else:
        print("请求结果:", res_json)
        return res_json

def test_captured():
    url = "https://api.birdreport.cn/front/activity/search"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "timestamp": "1784770694000",
        "requestId": "93c2c4a6900d8942b9983399d3086cda",
        "sign": "229d02fa30492227ad05424119fcc337"
    }
    payload = "Vu07VLWU5RSnP7ab2OPnJ6rsrgnxuZHy5q9cyq0gF6Gbrlc3u02hanaBOCS5FNzM9Xj39m5fphroBJWASi22NWqnFCMTvgdL1mQ+q2DzRxtRDnfjLSJgX8EbYYNEjCBsoKlrz5K2kWeIGZtfPP4VxFp/Xi3j9mXGsTuJIuwY6GY="
    
    resp = requests.post(url, data=payload, headers=headers)
    print(f"Captured HTTP Status: {resp.status_code}")
    res_json = resp.json()
    if res_json.get("code") == 200 and "data" in res_json:
        decrypted_str = decrypt_response(res_json["data"])
        decrypted_data = json.loads(decrypted_str)
        print("Captured 重放并解密成功！！！样例数据：")
        print(json.dumps(decrypted_data[:1] if isinstance(decrypted_data, list) else decrypted_data, ensure_ascii=False, indent=2))

def test_decrypt_real_data():
    captured_data_b64 = "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"
    decrypted = decrypt_response(captured_data_b64)
    res_obj = json.loads(decrypted)
    print("真实响应解密验证成功！！！示例条目：")
    print(json.dumps(res_obj[:2] if isinstance(res_obj, list) else res_obj, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    get_activity_data()
