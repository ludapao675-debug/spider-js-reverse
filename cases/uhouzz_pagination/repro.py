import time
import requests
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64

def aes_cbc_encrypt(text, key, iv):
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    encrypted_bytes = cipher.encrypt(pad(text.encode('utf-8'), AES.block_size))
    return base64.b64encode(encrypted_bytes).decode('utf-8')

def aes_cbc_decrypt(encrypted_b64, key, iv):
    cipher = AES.new(key.encode('utf-8'), AES.MODE_CBC, iv.encode('utf-8'))
    decrypted_bytes = unpad(cipher.decrypt(base64.b64decode(encrypted_b64)), AES.block_size)
    return decrypted_bytes.decode('utf-8')

def fetch_uhouzz_apartments(page=3):
    app_id = "63"
    device_id = "562FDA61-5303-4D1F-B5DF-18F6EBC28977"
    platform = "pc"
    timestamp = str(int(time.time() * 1000))
    
    secret_key = "1xPJA7iD2SrhkJnA"
    iv_key = "uhomescomleitian"
    
    # 构造签名原文
    raw_str = f"app_id={app_id}&device_id={device_id}&api_version=1&platform={platform}&_time={timestamp}"
    
    # 生成签名
    signature = aes_cbc_encrypt(raw_str, secret_key, iv_key)
    
    url = "https://www.uhouzz.com/house4.6/api/houseSearch/listing"
    headers = {
        "X-Client-Signature": signature,
        "X-Client-Appid": app_id,
        "X-Client-Deviceid": device_id,
        "X-Request-Timestamp": timestamp,
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        "Origin": "https://www.uhouzz.com",
        "Referer": f"https://www.uhouzz.com/us/los-angeles/apartments?params_string=pga{page}"
    }
    
    payload = f"country_unique_name=us&city_unique_name=los-angeles&school_unique_name=&neighborhood_unique_name=&property_type=&params_string=pga{page}&page_size=12&type_id=3"
    
    print(f"[*] Sending request for page {page}...")
    r = requests.post(url, headers=headers, data=payload)
    resp_json = r.json()
    
    if resp_json.get("error_code") == 0:
        encrypted_data = resp_json.get("data")
        if encrypted_data:
            decrypted_data = aes_cbc_decrypt(encrypted_data, secret_key, iv_key)
            data_json = json.loads(decrypted_data)
            print("[+] Success! Decrypted data preview:")
            print(json.dumps(data_json, ensure_ascii=False, indent=2)[:500] + "...")
            return data_json
        else:
            print("[-] No encrypted data found in response.")
    else:
        print("[-] API returned error:", resp_json)

if __name__ == "__main__":
    fetch_uhouzz_apartments(2)
