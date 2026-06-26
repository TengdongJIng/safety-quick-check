#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 image_asset 表中所有图片的 oss_object_key 为完整 OSS URL
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'hazard.db')
OSS_BASE = 'https://yinhaun-tuji.oss-cn-shenzhen.aliyuncs.com'

def update():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取当前所有 image_asset
    cursor.execute("SELECT image_id, oss_object_key, thumb_key FROM image_asset")
    rows = cursor.fetchall()

    updated = 0
    for image_id, old_key, old_thumb in rows:
        # 构造完整URL
        # 原 key 格式: photos/DN-xxx.png  -> https://.../photos/DN-xxx.png
        # 原 thumb: thumbs/DN-xxx.webp  -> https://.../thumbs/DN-xxx.webp
        new_key = f"{OSS_BASE}/{old_key}" if old_key and not old_key.startswith('http') else old_key
        new_thumb = f"{OSS_BASE}/{old_thumb}" if old_thumb and not old_thumb.startswith('http') else old_thumb

        cursor.execute('''
            UPDATE image_asset
            SET oss_object_key = ?, thumb_key = ?
            WHERE image_id = ?
        ''', (new_key, new_thumb, image_id))
        updated += 1

    conn.commit()

    # 验证
    cursor.execute("SELECT image_id, oss_object_key FROM image_asset LIMIT 3")
    print("[验证] 更新后的图片URL示例:")
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]}")

    cursor.execute("SELECT COUNT(*) FROM image_asset WHERE oss_object_key LIKE 'http%'")
    http_count = cursor.fetchone()[0]
    print(f"\n[OK] 已更新 {updated} 条图片记录，其中 {http_count} 条已配置完整URL")

    conn.close()

if __name__ == '__main__':
    update()
