#!/usr/bin/env python3
"""
提取 "Core 2026 / Brethren of Ash" 战役中的所有 Card 资源
包含正面和独立卡背（UniqueBack=True）
- 正面: {id}.png / {id}_{nickname}.png
- 卡背: {id}b.png / {id}b_{nickname}_back.png
"""

import json
import os
import re
from pathlib import Path
from PIL import Image
from urllib.parse import urlparse
import requests

# 配置路径
BASE_JSON_PATH = Path(__file__).parent / 'data' / 'base.json'
TTS_IMAGES_DIR = Path('/home/tk/.local/share/Tabletop Simulator/Mods/Images/')
SAVE_DIR_ID = Path('./extracted_cards/brethren_by_id')
SAVE_DIR_FULL = Path('./extracted_cards/brethren_by_name')

# 创建保存目录
SAVE_DIR_ID.mkdir(parents=True, exist_ok=True)
SAVE_DIR_FULL.mkdir(parents=True, exist_ok=True)

# 用于缓存已加载的图片
cached_images = {}

def url_to_filename(url: str) -> str:
    """将 URL 转换为 TTS 本地文件名格式"""
    filename = url.replace('https://', 'https').replace('http://', 'http')
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    if len(filename) > 200:
        filename = filename[:200]
    return filename

def get_local_image_path(face_url: str) -> Path | None:
    """获取本地图片路径"""
    base_name = url_to_filename(face_url)
    
    for ext in ['.png', '.jpg', '.jpeg', '.webp']:
        path = TTS_IMAGES_DIR / (base_name + ext)
        if path.exists():
            return path
    
    if 'steamusercontent' in face_url:
        match = re.search(r'/ugc/(\d+)', face_url)
        if match:
            ugc_id = match.group(1)
            for f in TTS_IMAGES_DIR.iterdir():
                if ugc_id in f.name and f.is_file():
                    return f
    
    return None

def download_image(url: str, save_path: Path) -> bool:
    """下载图片"""
    try:
        print(f"  下载图片: {url[:60]}...")
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            save_path.write_bytes(response.content)
            return True
    except Exception as e:
        print(f"  下载出错: {e}")
    return False

def load_image(image_url: str) -> Image.Image | None:
    """加载图片（本地或下载）"""
    if image_url in cached_images:
        return cached_images[image_url]
    
    local_path = get_local_image_path(image_url)
    
    if local_path:
        img = Image.open(local_path)
        cached_images[image_url] = img
        return img
    else:
        print(f"  本地未找到，尝试下载...")
        parsed = urlparse(image_url)
        ext = Path(parsed.path).suffix or '.png'
        temp_path = SAVE_DIR_ID / f"temp_dl_{hash(image_url) % 10000}{ext}"
        
        if download_image(image_url, temp_path):
            img = Image.open(temp_path)
            cached_images[image_url] = img
            return img
    
    return None

def split_deck_image(img: Image.Image, num_width: int, num_height: int) -> list[Image.Image]:
    """分割卡组图片为单张卡片"""
    width, height = img.size
    card_width = width // num_width
    card_height = height // num_height
    
    cards = []
    for row in range(num_height):
        for col in range(num_width):
            left = col * card_width
            upper = row * card_height
            right = left + card_width
            lower = upper + card_height
            card = img.crop((left, upper, right, lower))
            cards.append(card)
    
    return cards

def get_card_index(card_id: int) -> int:
    """获取卡片在卡组中的索引（后两位数字）"""
    return card_id % 100

def parse_gmnotes(gmnotes: str) -> dict:
    """解析 GMNotes JSON"""
    if not gmnotes:
        return {}
    try:
        formatted = gmnotes.strip()
        return json.loads(formatted)
    except:
        try:
            formatted = gmnotes.replace('\n', '').replace('  ', ' ').strip()
            return json.loads(formatted)
        except:
            return {}

def is_core_2026_card(gmnotes_dict: dict) -> bool:
    """检查卡片是否属于 Core 2026 战役"""
    cycle = gmnotes_dict.get('cycle', '')
    return 'Core 2026' in cycle or 'Core2026' in cycle

def find_all_core_2026_cards(data: dict) -> list[dict]:
    """找到所有属于 Core 2026 的 Card 对象"""
    cards = []
    seen_ids = set()
    
    def search_recursive(obj, path=''):
        if isinstance(obj, dict):
            name = obj.get('Name', '')
            
            if name in ['Card', 'CardCustom']:
                gmnotes = obj.get('GMNotes', '')
                note_json = parse_gmnotes(gmnotes)
                
                if is_core_2026_card(note_json):
                    card_id = obj.get('CardID', 0)
                    nickname = obj.get('Nickname', 'Unknown')
                    custom_deck = obj.get('CustomDeck', {})
                    card_code = note_json.get('id', '')
                    
                    if custom_deck and card_code:
                        key = f"{card_code}_{card_id}"
                        if key not in seen_ids:
                            seen_ids.add(key)
                            
                            # 提取卡组信息
                            deck_id, deck_info = list(custom_deck.items())[0]
                            
                            cards.append({
                                'card_id': card_id,
                                'nickname': nickname,
                                'card_code': card_code,
                                'custom_deck': custom_deck,
                                'deck_info': deck_info,
                                'deck_id': deck_id,
                                'gmnotes': note_json,
                                'path': path
                            })
            
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    search_recursive(value, f"{path}.{key}")
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                search_recursive(item, f"{path}[{i}]")
    
    search_recursive(data.get('ObjectStates', []))
    return cards

def process_cards(cards: list[dict]):
    """处理所有卡片，提取并保存图片（正面+卡背）"""
    total_front = 0
    total_back = 0
    
    for card in cards:
        card_code = card['card_code']
        nickname = card['nickname']
        card_id = card['card_id']
        deck_info = card['deck_info']
        
        face_url = deck_info['FaceURL']
        back_url = deck_info['BackURL']
        num_width = deck_info['NumWidth']
        num_height = deck_info['NumHeight']
        unique_back = deck_info.get('UniqueBack', False)
        
        card_idx = get_card_index(card_id)
        safe_nickname = re.sub(r'[^\w\s-]', '', nickname).strip().replace(' ', '_')
        
        # ===== 处理正面 =====
        front_img = load_image(face_url)
        if not front_img:
            print(f"  ✗ {card_code} ({nickname}) 正面图片加载失败")
            continue
        
        # 分割正面图片
        try:
            front_images = split_deck_image(front_img, num_width, num_height)
            if card_idx < len(front_images):
                front_card_img = front_images[card_idx]
                
                # 保存正面
                path_front_id = SAVE_DIR_ID / f"{card_code}.png"
                path_front_full = SAVE_DIR_FULL / f"{card_code}_{safe_nickname}.png"
                front_card_img.save(path_front_id, 'PNG')
                front_card_img.save(path_front_full, 'PNG')
                total_front += 1
                
                # 显示进度
                print(f"  ✓ {card_code} ({nickname}) 正面")
            else:
                print(f"  ✗ {card_code} ({nickname}) 正面索引 {card_idx} 超出范围")
                continue
        except Exception as e:
            print(f"  ✗ {card_code} ({nickname}) 正面处理失败: {e}")
            continue
        
        # ===== 处理卡背（如果 UniqueBack=True）=====
        if unique_back and back_url:
            back_img = load_image(back_url)
            if not back_img:
                print(f"    ⚠ 卡背图片加载失败")
                continue
            
            try:
                back_images = split_deck_image(back_img, num_width, num_height)
                if card_idx < len(back_images):
                    back_card_img = back_images[card_idx]
                    
                    # 保存卡背，使用 {id}b 命名
                    path_back_id = SAVE_DIR_ID / f"{card_code}b.png"
                    path_back_full = SAVE_DIR_FULL / f"{card_code}b_{safe_nickname}_back.png"
                    back_card_img.save(path_back_id, 'PNG')
                    back_card_img.save(path_back_full, 'PNG')
                    total_back += 1
                    
                    print(f"    ↳ 卡背已保存 ({card_code}b.png)")
                else:
                    print(f"    ⚠ 卡背索引 {card_idx} 超出范围")
            except Exception as e:
                print(f"    ⚠ 卡背处理失败: {e}")
    
    return total_front, total_back

def main():
    print("=" * 70)
    print("提取 Core 2026 / Brethren of Ash - 所有 Card 资源（含卡背）")
    print("=" * 70)
    
    # 加载 base.json
    print(f"\n加载 {BASE_JSON_PATH}...")
    with open(BASE_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 找到所有 Core 2026 卡片
    print("\n搜索所有 cycle='Core 2026' 的卡片...")
    cards = find_all_core_2026_cards(data)
    print(f"找到 {len(cards)} 张唯一卡片")
    
    # 统计 UniqueBack 数量
    unique_back_count = sum(1 for c in cards if c['deck_info'].get('UniqueBack'))
    print(f"其中 {unique_back_count} 张有独立卡背（UniqueBack=True）")
    
    # 显示部分卡片
    print("\n卡片预览 (前 20 张):")
    for card in cards[:20]:
        has_back = "↳" if card['deck_info'].get('UniqueBack') else " "
        print(f"  {has_back} {card['card_code']}: {card['nickname']}")
    if len(cards) > 20:
        print(f"  ... 还有 {len(cards) - 20} 张")
    
    # 处理和保存
    print("\n" + "=" * 70)
    print("开始处理图片...")
    total_front, total_back = process_cards(cards)
    
    print("\n" + "=" * 70)
    print("提取完成!")
    print(f"  总卡片数: {len(cards)}")
    print(f"  正面成功: {total_front}")
    print(f"  卡背成功: {total_back}")
    print(f"\n输出目录:")
    print(f"  {SAVE_DIR_ID.absolute()}")
    print(f"    - 正面: {len(list(SAVE_DIR_ID.glob('[0-9]*.png')))} 张")
    print(f"    - 卡背: {len(list(SAVE_DIR_ID.glob('[0-9]*b.png')))} 张")
    print(f"  {SAVE_DIR_FULL.absolute()}")
    print(f"    - 正面: {len(list(SAVE_DIR_FULL.glob('[0-9]*_*.png')))} 张")
    print(f"    - 卡背: {len(list(SAVE_DIR_FULL.glob('[0-9]*b_*_back.png')))} 张")
    print("=" * 70)

if __name__ == "__main__":
    main()
