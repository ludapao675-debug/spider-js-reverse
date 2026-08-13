import sys
import os

# 将当前案例目录加入 python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fanqie_font_decoder import FanqieFontDecoder

def main():
    """
    番茄小说字体反爬解密 一键复现与测试脚本
    """
    print("=" * 60)
    print("      番茄小说 Web 端通用字体反爬解密 —— 复现脚本")
    print("=" * 60)
    
    # 1. 实例化解密器
    decoder = FanqieFontDecoder()
    
    # 校验映射表库大小
    map_size = len(decoder.mapping)
    print(f"[1] 加载解码映射词表: {map_size} 条 (目标完整 362 条)")
    assert map_size >= 362, f"错误: 映射表数量不足，期望 362 条，实际 {map_size} 条"
    
    # 2. 模拟样本密文解密测试
    print("\n[2] 执行绝密样本无损还原测试...")
    
    sample_cases = [
        {
            "raw": "刺耳\ue4f3蝉鸣混杂\ue444\ue400\ue545彼伏\ue4f3鸣笛\ue488，\ue49e荡\ue3e9\ue4c2流湍急\ue4f3街\ue459\ue47d",
            "expected": "刺耳的蝉鸣混杂着此起彼伏的鸣笛声，回荡在人流湍急的街道上"
        },
        {
            "raw": "炎炎八\ue402。",
            "expected": "炎炎八月。"
        },
        {
            "raw": "黑缎缠\ue541，盲杖\ue3e9肩，左\ue4bc蔬菜，右\ue4bc抗油……",
            "expected": "黑缎缠目，盲杖在肩，左手蔬菜，右手抗油……"
        }
    ]
    
    passed = 0
    for idx, case in enumerate(sample_cases, 1):
        output = decoder.decode_text(case["raw"])
        is_ok = output == case["expected"]
        if is_ok:
            passed += 1
            print(f"  [OK] 样本 {idx} 解码正确: {output}")
        else:
            print(f"  [FAIL] 样本 {idx} 解码差异:")
            print(f"     实际: {output}")
            print(f"     期望: {case['expected']}")
            
    print("-" * 60)
    if passed == len(sample_cases):
        print(f"复现测试通过！全部 {passed}/{len(sample_cases)} 样本 100% 精确匹配还原。")
        return 0
    else:
        print(f"复现测试部分未通过: {passed}/{len(sample_cases)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
