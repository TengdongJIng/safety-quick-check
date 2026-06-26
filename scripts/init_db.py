#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
施工安全隐患快查助手 - 数据库初始化脚本
创建 SQLite 数据库和核心表结构
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'hazard.db')

def create_tables(conn):
    cursor = conn.cursor()

    # 1. 隐患主表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hazard_item (
        id TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        source_type TEXT NOT NULL CHECK(source_type IN ('provincial', 'district')),
        category_code TEXT NOT NULL,
        category_name TEXT NOT NULL,
        section_type TEXT NOT NULL,
        inspection_item TEXT NOT NULL,
        hazard_problem TEXT NOT NULL,
        requirement_text TEXT,
        rectification_text TEXT,
        risk_text TEXT,
        image_id TEXT,
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'deprecated')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 2. 监督抽查事项表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supervision_item (
        id TEXT PRIMARY KEY,
        jd_id TEXT NOT NULL UNIQUE,
        project_name TEXT NOT NULL,
        inspection_name TEXT NOT NULL,
        inspection_method TEXT,
        source TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 3. 监督问题情形表（核心：一个JD下多个问题情形，每个情形有独立处置）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS supervision_condition (
        id TEXT PRIMARY KEY,
        jd_id TEXT NOT NULL,
        condition_order INTEGER NOT NULL,
        condition_text TEXT NOT NULL,
        disposal_target TEXT NOT NULL,
        disposal_measure TEXT NOT NULL,
        penalty_basis TEXT,
        source TEXT NOT NULL,
        FOREIGN KEY (jd_id) REFERENCES supervision_item(jd_id)
    )
    ''')

    # 4. 隐患与监督关联表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hazard_supervision_link (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hazard_id TEXT NOT NULL,
        jd_id TEXT,
        condition_id TEXT,
        match_type TEXT NOT NULL CHECK(match_type IN ('exact', 'fuzzy', 'manual')),
        review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('approved', 'pending', 'rejected')),
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (hazard_id) REFERENCES hazard_item(id),
        FOREIGN KEY (jd_id) REFERENCES supervision_item(jd_id),
        FOREIGN KEY (condition_id) REFERENCES supervision_condition(id)
    )
    ''')

    # 5. 图片资源表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_asset (
        image_id TEXT PRIMARY KEY,
        hazard_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        oss_object_key TEXT,
        thumb_key TEXT,
        original_width INTEGER,
        original_height INTEGER,
        status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available', 'missing')),
        FOREIGN KEY (hazard_id) REFERENCES hazard_item(id)
    )
    ''')

    # 6. 辅助检索词表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS search_term (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hazard_id TEXT NOT NULL,
        term_type TEXT NOT NULL CHECK(term_type IN ('synonym', 'keyword', 'manual_alias')),
        term TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'pending' CHECK(review_status IN ('approved', 'pending', 'rejected')),
        FOREIGN KEY (hazard_id) REFERENCES hazard_item(id)
    )
    ''')

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hazard_category ON hazard_item(category_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hazard_inspection ON hazard_item(inspection_item)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hazard_status ON hazard_item(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_hazard ON hazard_supervision_link(hazard_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_condition ON hazard_supervision_link(condition_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_search_term ON search_term(term)')

    conn.commit()
    print(f"[OK] 数据库已初始化: {DB_PATH}")
    print("[OK] 表结构: hazard_item, supervision_item, supervision_condition, hazard_supervision_link, image_asset, search_term")

if __name__ == '__main__':
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    conn.close()
