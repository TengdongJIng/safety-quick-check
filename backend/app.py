#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
施工安全隐患快查助手 - Flask 后端 API
提供隐患查询、监督"110"关联、图片资源等 JSON 接口
"""

import os
import sqlite3
import json
from flask import Flask, jsonify, request, g, send_from_directory, redirect
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'database', 'hazard.db')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

print(f"[STARTUP] BASE_DIR: {BASE_DIR}")
print(f"[STARTUP] DB_PATH: {DB_PATH}")
print(f"[STARTUP] FRONTEND_DIR: {FRONTEND_DIR}")
print(f"[STARTUP] FRONTEND_DIR exists: {os.path.isdir(FRONTEND_DIR)}")
print(f"[STARTUP] index.html exists: {os.path.isfile(os.path.join(FRONTEND_DIR, 'index.html'))}")


def get_db():
    """获取数据库连接（Flask g 对象单请求复用）"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """请求结束后关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ============================================================
# 辅助函数
# ============================================================

def row_to_dict(row):
    """将 sqlite3.Row 转为字典"""
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def dict_rows(cursor):
    """将查询结果全部转为字典列表"""
    return [row_to_dict(row) for row in cursor.fetchall()]


def get_supervision_links(hazard_id):
    """
    获取某条隐患关联的监督"110"问题情形
    按 JD 编号分组，同一问题情形下按处置对象分组
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT
            l.hazard_id,
            l.jd_id,
            l.condition_id,
            l.match_type,
            l.notes,
            c.condition_order,
            c.condition_text,
            c.disposal_target,
            c.disposal_measure,
            c.penalty_basis,
            s.project_name,
            s.inspection_name
        FROM hazard_supervision_link l
        JOIN supervision_condition c ON l.condition_id = c.id
        JOIN supervision_item s ON l.jd_id = s.jd_id
        WHERE l.hazard_id = ? AND l.review_status = 'approved'
        ORDER BY l.jd_id, c.condition_order, c.disposal_target
    ''', (hazard_id,))

    rows = cursor.fetchall()
    if not rows:
        return None

    # 按 JD 分组，JD 下按 condition_order 分组
    result = {}
    for row in rows:
        jd_id = row['jd_id']
        if jd_id not in result:
            result[jd_id] = {
                'jd_id': jd_id,
                'project_name': row['project_name'],
                'inspection_name': row['inspection_name'],
                'conditions': {}
            }
        cond_order = row['condition_order']
        if cond_order not in result[jd_id]['conditions']:
            result[jd_id]['conditions'][cond_order] = {
                'condition_order': cond_order,
                'condition_text': row['condition_text'],
                'disposals': []
            }
        result[jd_id]['conditions'][cond_order]['disposals'].append({
            'disposal_target': row['disposal_target'],
            'disposal_measure': row['disposal_measure'],
            'penalty_basis': row['penalty_basis']
        })

    # 转为有序列表
    output = []
    for jd_id in sorted(result.keys()):
        jd_data = result[jd_id]
        conditions = []
        for order in sorted(jd_data['conditions'].keys()):
            conditions.append(jd_data['conditions'][order])
        output.append({
            'jd_id': jd_id,
            'project_name': jd_data['project_name'],
            'inspection_name': jd_data['inspection_name'],
            'conditions': conditions
        })
    return output


# ============================================================
# API 路由
# ============================================================

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT COUNT(*) FROM hazard_item')
        count = cursor.fetchone()[0]
        return jsonify({'status': 'ok', 'hazard_count': count})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """
    获取所有工程类别列表
    返回: [{category_code, category_name, source_type, count}, ...]
    排序: 省图集(provincial)在前，区手册(district)在后
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT 
            category_code, 
            category_name, 
            source_type,
            COUNT(*) as count
        FROM hazard_item
        WHERE status = 'active'
        GROUP BY category_code, category_name, source_type
        ORDER BY 
            CASE source_type 
                WHEN 'provincial' THEN 0 
                WHEN 'district' THEN 1 
                ELSE 2 
            END,
            category_code
    ''')
    rows = dict_rows(cursor)
    return jsonify({'data': rows})


@app.route('/api/hazards', methods=['GET'])
def get_hazards():
    """
    按类别查询隐患列表（支持筛选分部工程）
    参数: ?category=DN&section=工程实体
    """
    category = request.args.get('category', '').strip()
    section = request.args.get('section', '').strip()

    if not category:
        return jsonify({'error': '缺少 category 参数'}), 400

    db = get_db()
    cursor = db.cursor()

    sql = '''
        SELECT
            id, source, source_type, category_code, category_name,
            section_type, inspection_item, hazard_problem,
            image_id, requirement_text
        FROM hazard_item
        WHERE category_code = ? AND status = 'active'
    '''
    params = [category]

    if section:
        sql += ' AND section_type = ?'
        params.append(section)

    sql += ' ORDER BY id'
    cursor.execute(sql, params)
    rows = dict_rows(cursor)
    return jsonify({'data': rows, 'count': len(rows)})


@app.route('/api/hazard/<hazard_id>', methods=['GET'])
def get_hazard_detail(hazard_id):
    """
    获取单条隐患详情（含图片资源、监督"110"关联）
    """
    db = get_db()
    cursor = db.cursor()

    # 1. 隐患基本信息
    cursor.execute('''
        SELECT * FROM hazard_item WHERE id = ? AND status = 'active'
    ''', (hazard_id,))
    row = cursor.fetchone()
    if row is None:
        return jsonify({'error': '隐患不存在或已停用'}), 404

    hazard = row_to_dict(row)

    # 2. 图片资源
    cursor.execute('''
        SELECT image_id, file_name, oss_object_key, thumb_key, status
        FROM image_asset WHERE hazard_id = ?
    ''', (hazard_id,))
    images = dict_rows(cursor)

    # 3. 监督"110"关联
    supervision = get_supervision_links(hazard_id)

    return jsonify({
        'data': {
            'hazard': hazard,
            'images': images,
            'supervision': supervision
        }
    })


@app.route('/api/search', methods=['GET'])
def search_hazards():
    """
    关键词全文检索
    参数: ?q=关键词 或 ?q=关键词1+关键词2
    搜索范围: 隐患描述、检查项、规范要求、整改措施、风险分析、辅助检索词
    """
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'error': '搜索关键词至少2个字符'}), 400

    # 分词：按空格或逗号分词
    terms = [t.strip() for t in query.replace(',', ' ').split() if len(t.strip()) >= 2]
    if not terms:
        terms = [query]

    db = get_db()
    cursor = db.cursor()

    # 构建 LIKE 条件
    like_clauses = []
    like_params = []
    for term in terms:
        pattern = f'%{term}%'
        like_clauses.append('''
            hazard_problem LIKE ?
            OR inspection_item LIKE ?
            OR requirement_text LIKE ?
            OR rectification_text LIKE ?
            OR risk_text LIKE ?
        ''')
        like_params.extend([pattern] * 5)

    # 主查询
    sql = f'''
        SELECT DISTINCT
            id, source, source_type, category_code, category_name,
            section_type, inspection_item, hazard_problem,
            image_id, requirement_text
        FROM hazard_item
        WHERE status = 'active'
        AND ({") OR (".join(like_clauses)})
        ORDER BY id
    '''
    cursor.execute(sql, like_params)
    main_results = dict_rows(cursor)
    main_ids = {r['id'] for r in main_results}

    # 辅助检索词表查询
    cursor.execute('''
        SELECT DISTINCT hazard_id FROM search_term
        WHERE term LIKE ? AND review_status = 'approved'
    ''', (f'%{query}%',))
    alias_ids = {row['hazard_id'] for row in cursor.fetchall()}

    # 补充通过别名命中但主查询未命中的记录
    extra_ids = alias_ids - main_ids
    if extra_ids:
        placeholders = ','.join('?' * len(extra_ids))
        cursor.execute(f'''
            SELECT
                id, source, source_type, category_code, category_name,
                section_type, inspection_item, hazard_problem,
                image_id, requirement_text
            FROM hazard_item
            WHERE id IN ({placeholders}) AND status = 'active'
        ''', tuple(extra_ids))
        extra_results = dict_rows(cursor)
        # 标记来源为别名匹配
        for r in extra_results:
            r['match_source'] = 'alias'
        main_results.extend(extra_results)
        main_ids.update(extra_ids)

    # 去重并排序
    seen = set()
    final_results = []
    for r in main_results:
        if r['id'] not in seen:
            seen.add(r['id'])
            if 'match_source' not in r:
                r['match_source'] = 'direct'
            final_results.append(r)

    final_results.sort(key=lambda x: x['id'])

    return jsonify({
        'data': final_results,
        'count': len(final_results),
        'query': query,
        'terms': terms
    })


@app.route('/api/supervision/<jd_id>', methods=['GET'])
def get_supervision_detail(jd_id):
    """
    获取单个监督"110"抽查事项的详情（含所有问题情形）
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT * FROM supervision_item WHERE jd_id = ?
    ''', (jd_id,))
    item = row_to_dict(cursor.fetchone())
    if item is None:
        return jsonify({'error': '监督事项不存在'}), 404

    cursor.execute('''
        SELECT
            id, condition_order, condition_text,
            disposal_target, disposal_measure, penalty_basis
        FROM supervision_condition
        WHERE jd_id = ?
        ORDER BY condition_order
    ''', (jd_id,))
    conditions = dict_rows(cursor)

    return jsonify({
        'data': {
            'item': item,
            'conditions': conditions
        }
    })


@app.route('/api/inspection-items', methods=['GET'])
def get_inspection_items():
    """
    获取某类别下的检查项列表（按分部工程分组）
    参数: ?category=DN
    返回: [{section_type, items: [{inspection_item, count}, ...]}, ...]
    """
    category = request.args.get('category', '').strip()
    if not category:
        return jsonify({'error': '缺少 category 参数'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT section_type, inspection_item, COUNT(*) as count
        FROM hazard_item
        WHERE category_code = ? AND status = 'active'
        GROUP BY section_type, inspection_item
        ORDER BY section_type, inspection_item
    ''', (category,))
    rows = dict_rows(cursor)

    result = {}
    for row in rows:
        section = row['section_type']
        if section not in result:
            result[section] = {'section_type': section, 'items': []}
        result[section]['items'].append({
            'inspection_item': row['inspection_item'],
            'count': row['count']
        })

    return jsonify({'data': list(result.values())})


@app.route('/api/hazards-by-item', methods=['GET'])
def get_hazards_by_item():
    """
    按类别 + 检查项查询隐患列表
    参数: ?category=DN&item=安全装置
    """
    category = request.args.get('category', '').strip()
    item = request.args.get('item', '').strip()

    if not category or not item:
        return jsonify({'error': '缺少 category 或 item 参数'}), 400

    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT
            id, source, source_type, category_code, category_name,
            section_type, inspection_item, hazard_problem,
            image_id, requirement_text
        FROM hazard_item
        WHERE category_code = ? AND inspection_item = ? AND status = 'active'
        ORDER BY id
    ''', (category, item))
    rows = dict_rows(cursor)

    return jsonify({'data': rows, 'count': len(rows)})


@app.route('/api/similar-hazards/<hazard_id>', methods=['GET'])
def get_similar_hazards(hazard_id):
    """
    获取同类隐患（同类别同检查项的其他隐患）
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT category_code, inspection_item FROM hazard_item WHERE id = ? AND status = 'active'
    ''', (hazard_id,))
    row = cursor.fetchone()
    if row is None:
        return jsonify({'error': '隐患不存在'}), 404

    category_code = row['category_code']
    inspection_item = row['inspection_item']

    cursor.execute('''
        SELECT
            id, source, source_type, category_code, category_name,
            section_type, inspection_item, hazard_problem,
            image_id, requirement_text
        FROM hazard_item
        WHERE category_code = ? AND inspection_item = ? AND id != ? AND status = 'active'
        ORDER BY id
    ''', (category_code, inspection_item, hazard_id))
    rows = dict_rows(cursor)

    return jsonify({'data': rows, 'count': len(rows)})


@app.route('/api/catalog', methods=['GET'])
def get_catalog():
    """
    全局目录：按来源分组，展示类别 → 分部 → 检查项层级结构
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT
            source_type, source, category_code, category_name,
            section_type, inspection_item, COUNT(*) as count
        FROM hazard_item
        WHERE status = 'active'
        GROUP BY source_type, source, category_code, category_name, section_type, inspection_item
        ORDER BY source_type, category_code, section_type, inspection_item
    ''')
    rows = dict_rows(cursor)

    result = {}
    for row in rows:
        src_type = row['source_type']
        if src_type not in result:
            result[src_type] = {
                'source_type': src_type,
                'source': row['source'],
                'categories': {}
            }

        cat_code = row['category_code']
        if cat_code not in result[src_type]['categories']:
            result[src_type]['categories'][cat_code] = {
                'category_code': cat_code,
                'category_name': row['category_name'],
                'sections': {}
            }

        section = row['section_type']
        if section not in result[src_type]['categories'][cat_code]['sections']:
            result[src_type]['categories'][cat_code]['sections'][section] = {
                'section_type': section,
                'items': []
            }

        result[src_type]['categories'][cat_code]['sections'][section]['items'].append({
            'inspection_item': row['inspection_item'],
            'count': row['count']
        })

    output = []
    for src_type in ['provincial', 'district']:
        if src_type not in result:
            continue
        src_data = result[src_type]
        categories = []
        for cat_code in sorted(src_data['categories'].keys()):
            cat = src_data['categories'][cat_code]
            sections = []
            for sec_name in sorted(cat['sections'].keys()):
                sec = cat['sections'][sec_name]
                sections.append({
                    'section_type': sec['section_type'],
                    'items': sec['items']
                })
            total_count = sum(
                item['count']
                for sec in sections
                for item in sec['items']
            )
            categories.append({
                'category_code': cat['category_code'],
                'category_name': cat['category_name'],
                'total_count': total_count,
                'sections': sections
            })
        output.append({
            'source_type': src_data['source_type'],
            'source': src_data['source'],
            'categories': categories
        })

    return jsonify({'data': output})


@app.route('/api/image/<image_id>', methods=['GET'])
def get_image(image_id):
    """
    图片重定向接口：根据 image_id 查询 OSS URL 并重定向
    兼容旧版前端路径 /api/image/xxx
    """
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        SELECT oss_object_key FROM image_asset WHERE image_id = ?
    ''', (image_id,))
    row = cursor.fetchone()
    if row is None or not row[0]:
        return jsonify({'error': '图片不存在'}), 404

    oss_url = row[0]
    if oss_url.startswith('http'):
        return redirect(oss_url)
    else:
        return jsonify({'error': '图片URL无效'}), 404


@app.route('/api/supervision/list', methods=['GET'])
def get_supervision_list():
    """
    获取所有监督"110"抽查事项列表（含问题情形数）
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute('''
        SELECT
            s.jd_id, s.project_name, s.inspection_name, s.source,
            COUNT(DISTINCT c.condition_order) as condition_count
        FROM supervision_item s
        LEFT JOIN supervision_condition c ON s.jd_id = c.jd_id
        GROUP BY s.jd_id, s.project_name, s.inspection_name, s.source
        ORDER BY s.jd_id
    ''')
    rows = dict_rows(cursor)

    return jsonify({'data': rows, 'count': len(rows)})


# ============================================================
# 静态文件服务（H5前端）
# ============================================================
# 健康检查
# ============================================================

@app.route('/health')
def health_check():
    """健康检查端点，Railway 使用此端点判断服务是否正常"""
    return jsonify({'status': 'ok', 'service': 'safety-quick-check'}), 200


# ============================================================
# 前端静态文件服务
# ============================================================

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend')

@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def serve_frontend(path):
    """提供前端静态文件，未匹配路径返回 index.html（SPA 路由）"""
    try:
        file_path = os.path.join(FRONTEND_DIR, path)
        if os.path.isfile(file_path):
            return send_from_directory(FRONTEND_DIR, path)
        return send_from_directory(FRONTEND_DIR, 'index.html')
    except Exception as e:
        app.logger.error(f"静态文件服务错误: {e}")
        return jsonify({'error': '静态文件服务错误'}), 500


# ============================================================
# 启动
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 9000))
    print(f"[INFO] BASE_DIR: {BASE_DIR}")
    print(f"[INFO] DB_PATH: {DB_PATH}")
    print(f"[INFO] FRONTEND_DIR: {FRONTEND_DIR}")
    print(f"[INFO] 服务启动: http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
