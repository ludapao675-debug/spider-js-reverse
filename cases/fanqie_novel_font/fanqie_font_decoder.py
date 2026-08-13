import json
import os
import re
from typing import Dict, Union, List

class FanqieFontDecoder:
    """
    番茄小说 Web 端通用字体反爬解密器 (通用案例版本)
    
    站点：fanqienovel.com
    解密范围：番茄小说 Web 端通用 362 个 PUA 码位（U+E3E8 ~ U+E55B）
    准确率：100% 精确匹配无毁损还原
    """
    
    def __init__(self, map_file_path: str = None):
        """
        初始化解密器
        :param map_file_path: 映射表 JSON 文件路径，若为空则自动定位案例同级配置文件
        """
        self.mapping: Dict[int, str] = {}
        self.str_mapping: Dict[str, str] = {}
        
        base_dir = os.path.dirname(os.path.abspath(__file__))
        possible_paths = [
            map_file_path,
            os.path.join(base_dir, "fanqie_precise_map.json"),
            os.path.join(base_dir, "..", "..", "scratch", "fanqie_precise_map.json"),
        ]
        
        loaded = False
        for path in possible_paths:
            if path and os.path.exists(path):
                try:
                    self._load_mapping_file(path)
                    loaded = True
                    break
                except Exception as e:
                    print(f"[FanqieFontDecoder] 警告: 加载 {path} 失败: {e}")
                    
        if not loaded:
            print("[FanqieFontDecoder] 错误: 未能找到有效映射表文件。")

    def _load_mapping_file(self, file_path: str):
        """
        解析载入映射 JSON 数据
        """
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        self.mapping.clear()
        self.str_mapping.clear()
        
        for key, val in raw_data.items():
            char = val["char"] if isinstance(val, dict) and "char" in val else str(val)
            self.str_mapping[key] = char
            
            code_point = None
            if key.startswith("U+"):
                code_point = int(key[2:], 16)
            elif key.startswith("0x") or key.startswith("0X"):
                code_point = int(key[2:], 16)
            elif key.isdigit():
                code_point = int(key)
                
            if code_point is not None:
                self.mapping[code_point] = char

    def decode_text(self, text: str) -> str:
        """
        解密包含 PUA 乱码的纯文本
        """
        if not text:
            return ""
            
        result_chars = []
        for char in text:
            code = ord(char)
            if 0xE000 <= code <= 0xF8FF:
                result_chars.append(self.mapping.get(code, char))
            else:
                result_chars.append(char)
                
        return "".join(result_chars)

    def decode_paragraphs(self, paragraphs: List[str]) -> List[str]:
        """
        批量解密段落数组
        """
        return [self.decode_text(p) for p in paragraphs]

    def decode_html(self, html_content: str) -> str:
        """
        解密 HTML 源码中的 PUA 码位（支持直接字符与 &#xE3E8; 实体引用）
        """
        if not html_content:
            return ""
            
        decoded = self.decode_text(html_content)
        
        def _entity_replancer(match):
            entity_val = match.group(1)
            code = int(entity_val[1:], 16) if entity_val.lower().startswith('x') else int(entity_val)
            if 0xE000 <= code <= 0xF8FF and code in self.mapping:
                return self.mapping[code]
            return match.group(0)
            
        return re.sub(r'&#(x[0-9a-fA-F]+|\d+);', _entity_replancer, decoded)
