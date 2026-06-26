#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将数据库数据嵌入前端HTML，生成独立静态文件
无需服务器，直接在浏览器打开即可使用
"""

import os
import sqlite3
import json
import re

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'hazard.db')
FRONTEND_PATH = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index.html')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'index-static.html')


def export_data():
    """从数据库导出所有数据"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. 工程类别
    cursor.execute('''
        SELECT category_code, category_name, source_type, COUNT(*) as count
        FROM hazard_item WHERE status='active'
        GROUP BY category_code, category_name, source_type ORDER BY category_code
    ''')
    categories = [dict(row) for row in cursor.fetchall()]

    # 2. 所有隐患
    cursor.execute('''
        SELECT id, source, source_type, category_code, category_name,
               section_type, inspection_item, hazard_problem,
               requirement_text, rectification_text, risk_text, image_id
        FROM hazard_item WHERE status='active' ORDER BY id
    ''')
    hazards = [dict(row) for row in cursor.fetchall()]

    # 3. 图片资源
    cursor.execute('SELECT image_id, hazard_id, file_name, oss_object_key, thumb_key FROM image_asset')
    images = [dict(row) for row in cursor.fetchall()]

    # 4. 监督关联（按 hazard_id 分组）
    cursor.execute('''
        SELECT l.hazard_id, l.jd_id, l.condition_id, l.match_type, l.review_status, l.notes,
               c.condition_order, c.condition_text, c.disposal_target, c.disposal_measure, c.penalty_basis,
               s.project_name, s.inspection_name
        FROM hazard_supervision_link l
        JOIN supervision_condition c ON l.condition_id = c.id
        JOIN supervision_item s ON l.jd_id = s.jd_id
        ORDER BY l.hazard_id, l.jd_id, c.condition_order, c.disposal_target
    ''')
    links_raw = [dict(row) for row in cursor.fetchall()]

    # 将关联数据按 hazard_id 分组
    supervision_map = {}
    for row in links_raw:
        hid = row['hazard_id']
        if hid not in supervision_map:
            supervision_map[hid] = {}
        jd = row['jd_id']
        if jd not in supervision_map[hid]:
            supervision_map[hid][jd] = {
                'jd_id': jd,
                'project_name': row['project_name'],
                'inspection_name': row['inspection_name'],
                'conditions': {}
            }
        co = row['condition_order']
        if co not in supervision_map[hid][jd]['conditions']:
            supervision_map[hid][jd]['conditions'][co] = {
                'condition_order': co,
                'condition_text': row['condition_text'],
                'disposals': []
            }
        supervision_map[hid][jd]['conditions'][co]['disposals'].append({
            'disposal_target': row['disposal_target'],
            'disposal_measure': row['disposal_measure'],
            'penalty_basis': row['penalty_basis']
        })

    # 转换为有序列表
    supervision_data = {}
    for hid, jd_map in supervision_map.items():
        arr = []
        for jd_id in sorted(jd_map.keys()):
            item = jd_map[jd_id]
            conds = []
            for co in sorted(item['conditions'].keys()):
                conds.append(item['conditions'][co])
            arr.append({
                'jd_id': item['jd_id'],
                'project_name': item['project_name'],
                'inspection_name': item['inspection_name'],
                'conditions': conds
            })
        supervision_data[hid] = arr

    conn.close()

    return {
        'categories': categories,
        'hazards': hazards,
        'images': images,
        'supervision': supervision_data
    }


def build_static_html():
    """读取前端HTML，替换API调用为内联数据"""
    data = export_data()
    data_json = json.dumps(data, ensure_ascii=False)

    with open(FRONTEND_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # 替换 API_BASE 和 apiGet 函数为直接读取内联数据
    # 找到 <script> 标签内的内容，替换 apiGet 函数

    new_api_code = f'''
    /* ============================================================
       内联数据（无需服务器）
       ============================================================ */
    const INLINE_DATA = {data_json};

    /* ============================================================
       API 请求封装（内联模式）
       ============================================================ */
    async function apiGet(url) {{
        // 解析URL路径
        if (url === '/categories') {{
            return {{ data: INLINE_DATA.categories }};
        }}
        if (url.startsWith('/hazards')) {{
            const params = new URLSearchParams(url.split('?')[1] || '');
            const category = params.get('category');
            const section = params.get('section');
            let list = INLINE_DATA.hazards.filter(h => h.category_code === category);
            if (section) list = list.filter(h => h.section_type === section);
            return {{ data: list, count: list.length }};
        }}
        if (url.startsWith('/hazard/')) {{
            const id = url.split('/hazard/')[1];
            const h = INLINE_DATA.hazards.find(x => x.id === id);
            if (!h) throw new Error('404');
            const imgs = INLINE_DATA.images.filter(i => i.hazard_id === id);
            const sup = INLINE_DATA.supervision[id] || null;
            return {{ data: {{ hazard: h, images: imgs, supervision: sup }} }};
        }}
        if (url.startsWith('/search')) {{
            const params = new URLSearchParams(url.split('?')[1] || '');
            const q = params.get('q') || '';
            const terms = q.toLowerCase().split(/\\s+/).filter(t => t.length >= 2);
            const list = INLINE_DATA.hazards.filter(h => {{
                const text = (h.hazard_problem + ' ' + h.inspection_item + ' ' + h.requirement_text + ' ' + h.rectification_text + ' ' + h.risk_text).toLowerCase();
                return terms.every(t => text.includes(t));
            }});
            return {{ data: list, count: list.length, query: q, terms }};
        }}
        if (url === '/health') {{
            return {{ status: 'ok', hazard_count: INLINE_DATA.hazards.length }};
        }}
        throw new Error('Unknown endpoint: ' + url);
    }}
    '''

    # 替换 API_BASE 定义和 apiGet 函数
    # 先替换 API_BASE
    html = html.replace(
        "const API_BASE = '/api';",
        "const API_BASE = '/api'; // 静态模式：apiGet 已替换为内联数据读取"
    )

    # 找到 apiGet 函数并替换（使用lambda避免反斜杠转义问题）
    api_get_pattern = r'async function apiGet\(url\) \{[^}]+\}'
    html = re.sub(api_get_pattern, lambda m: new_api_code.strip(), html, flags=re.DOTALL)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print(f"[OK] 静态文件已生成: {OUTPUT_PATH}")
    print(f"[OK] 文件大小: {size_kb:.1f} KB")
    print(f"[OK] 包含数据: {len(data['hazards'])} 条隐患, {len(data['images'])} 张图片, {len(data['categories'])} 个类别")
    print(f"[OK] 监督关联: {len(data['supervision'])} 条隐患有关联")
    print(f"[OK] 使用方式: 直接用浏览器打开 index-static.html，无需启动服务器")


if __name__ == '__main__':
    build_static_html()
