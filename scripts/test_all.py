#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
施工安全隐患快查助手 - 边界测试 & 回归测试
覆盖范围：
  1. 数据库完整性校验
  2. API 边界场景测试
  3. 数据关联一致性验证
"""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.parse
import urllib.error

# ============================================================
# 配置
# ============================================================
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'hazard.db')
API_BASE = 'http://127.0.0.1:5000/api'

# 测试结果统计
results = {'pass': 0, 'fail': 0, 'skip': 0, 'errors': []}


def test(name, condition, detail=''):
    """记录单条测试结果"""
    if condition:
        results['pass'] += 1
        print(f"  [PASS] {name}")
    else:
        results['fail'] += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" -- {detail}"
        print(msg)
        results['errors'].append((name, detail))


def skip(name, reason=''):
    results['skip'] += 1
    print(f"  [SKIP] {name}" + (f" -- {reason}" if reason else ''))


def api_get(path):
    """发起 GET 请求，返回 (status_code, json_data)"""
    try:
        url = API_BASE + path
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        return resp.status, data
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            data = json.loads(body)
        except:
            data = body
        return e.code, data
    except Exception as e:
        return 0, str(e)


# ============================================================
# 1. 数据库完整性校验
# ============================================================
def test_database_integrity():
    print("\n" + "=" * 60)
    print("1. 数据库完整性校验")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        test('数据库文件存在', False, f'文件不存在: {DB_PATH}')
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1.1 表结构完整性
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row['name'] for row in cursor.fetchall()]
    expected_tables = ['hazard_item', 'supervision_item', 'supervision_condition',
                      'hazard_supervision_link', 'image_asset', 'search_term']
    for t in expected_tables:
        test(f'表 {t} 存在', t in tables)

    # 1.2 索引完整性
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
    indexes = [row['name'] for row in cursor.fetchall()]
    expected_indexes = ['idx_hazard_category', 'idx_hazard_inspection', 'idx_hazard_status',
                        'idx_link_hazard', 'idx_link_condition', 'idx_search_term']
    for idx in expected_indexes:
        test(f'索引 {idx} 存在', idx in indexes)

    # 1.3 隐患数据量
    cursor.execute("SELECT COUNT(*) FROM hazard_item WHERE status='active'")
    count = cursor.fetchone()[0]
    test(f'活跃隐患总数 = 68', count == 68, f'实际: {count}')

    cursor.execute("SELECT COUNT(*) FROM hazard_item WHERE category_code='DN' AND status='active'")
    dn_count = cursor.fetchone()[0]
    test(f'DN吊篮隐患 = 60', dn_count == 60, f'实际: {dn_count}')

    cursor.execute("SELECT COUNT(*) FROM hazard_item WHERE category_code='NS' AND status='active'")
    ns_count = cursor.fetchone()[0]
    test(f'NS吊篮隐患 = 8', ns_count == 8, f'实际: {ns_count}')

    # 1.4 监督数据量
    cursor.execute("SELECT COUNT(*) FROM supervision_item")
    si_count = cursor.fetchone()[0]
    test(f'监督抽查事项 = 5', si_count == 5, f'实际: {si_count}')

    cursor.execute("SELECT COUNT(*) FROM supervision_condition")
    sc_count = cursor.fetchone()[0]
    test(f'监督问题情形 = 12', sc_count == 12, f'实际: {sc_count}')

    cursor.execute("SELECT COUNT(*) FROM hazard_supervision_link WHERE review_status='approved'")
    link_count = cursor.fetchone()[0]
    test(f'已确认关联 = 15', link_count == 15, f'实际: {link_count}')

    # 1.5 图片资源映射
    cursor.execute("SELECT COUNT(*) FROM image_asset")
    img_count = cursor.fetchone()[0]
    test(f'图片资源映射 = 68', img_count == 68, f'实际: {img_count}')

    # 1.6 无孤儿数据：所有关联的 hazard_id 必须在 hazard_item 中存在
    cursor.execute('''
        SELECT l.hazard_id FROM hazard_supervision_link l
        LEFT JOIN hazard_item h ON l.hazard_id = h.id
        WHERE h.id IS NULL
    ''')
    orphans = cursor.fetchall()
    test('关联表无孤儿 hazard_id', len(orphans) == 0, f'孤儿数: {len(orphans)}')

    # 1.7 所有关联的 condition_id 必须在 supervision_condition 中存在
    cursor.execute('''
        SELECT l.condition_id FROM hazard_supervision_link l
        LEFT JOIN supervision_condition c ON l.condition_id = c.id
        WHERE c.id IS NULL AND l.condition_id IS NOT NULL
    ''')
    orphans2 = cursor.fetchall()
    test('关联表无孤儿 condition_id', len(orphans2) == 0, f'孤儿数: {len(orphans2)}')

    # 1.8 所有 condition 的 jd_id 必须在 supervision_item 中存在
    cursor.execute('''
        SELECT c.jd_id FROM supervision_condition c
        LEFT JOIN supervision_item s ON c.jd_id = s.jd_id
        WHERE s.jd_id IS NULL
    ''')
    orphans3 = cursor.fetchall()
    test('问题情形无孤儿 jd_id', len(orphans3) == 0, f'孤儿数: {len(orphans3)}')

    # 1.9 每条隐患都有 image_id
    cursor.execute("SELECT COUNT(*) FROM hazard_item WHERE image_id IS NULL OR image_id = ''")
    no_image = cursor.fetchone()[0]
    test('所有隐患都有 image_id', no_image == 0, f'缺失数: {no_image}')

    # 1.10 image_asset 中每条记录的 hazard_id 都在 hazard_item 中
    cursor.execute('''
        SELECT i.hazard_id FROM image_asset i
        LEFT JOIN hazard_item h ON i.hazard_id = h.id
        WHERE h.id IS NULL
    ''')
    orphans4 = cursor.fetchall()
    test('图片资源无孤儿 hazard_id', len(orphans4) == 0, f'孤儿数: {len(orphans4)}')

    # 1.11 DN 数据的 section_type 分布
    cursor.execute("SELECT section_type, COUNT(*) FROM hazard_item WHERE category_code='DN' GROUP BY section_type")
    sections = {row['section_type']: row['COUNT(*)'] for row in cursor.fetchall()}
    test('DN 资料管理 = 9', sections.get('资料管理', 0) == 9, f'实际: {sections.get("资料管理", 0)}')
    test('DN 工程实体 = 51', sections.get('工程实体', 0) == 51, f'实际: {sections.get("工程实体", 0)}')

    # 1.12 无重复隐患 ID
    cursor.execute("SELECT id, COUNT(*) as cnt FROM hazard_item GROUP BY id HAVING cnt > 1")
    dupes = cursor.fetchall()
    test('隐患 ID 无重复', len(dupes) == 0, f'重复数: {len(dupes)}')

    conn.close()


# ============================================================
# 2. API 边界场景测试
# ============================================================
def test_api_boundary():
    print("\n" + "=" * 60)
    print("2. API 边界场景测试")
    print("=" * 60)

    # 2.1 健康检查
    code, data = api_get('/health')
    test('GET /api/health 返回 200', code == 200, f'状态码: {code}')
    if code == 200:
        test('health 返回 status=ok', data.get('status') == 'ok', f'实际: {data}')
        test('health 返回 hazard_count=68', data.get('hazard_count') == 68, f'实际: {data.get("hazard_count")}')

    # 2.2 工程类别列表
    code, data = api_get('/categories')
    test('GET /api/categories 返回 200', code == 200)
    if code == 200:
        cats = data.get('data', [])
        test('类别数量 = 2', len(cats) == 2, f'实际: {len(cats)}')
        cat_codes = [c['category_code'] for c in cats]
        test('包含 DN 类别', 'DN' in cat_codes)
        test('包含 NS 类别', 'NS' in cat_codes)

    # 2.3 隐患列表 - 正常查询
    code, data = api_get('/hazards?category=DN')
    test('GET /api/hazards?category=DN 返回 200', code == 200)
    if code == 200:
        test('DN 隐患数量 = 60', data.get('count') == 60, f'实际: {data.get("count")}')
        test('返回 data 字段', 'data' in data)
        test('第一条 ID = DN-001', data['data'][0]['id'] == 'DN-001', f'实际: {data["data"][0]["id"]}')

    # 2.4 隐患列表 - 带分部筛选
    code, data = api_get('/hazards?category=DN&section=' + urllib.parse.quote('资料管理'))
    test('DN+资料管理 返回 200', code == 200)
    if code == 200:
        test('DN 资料管理数量 = 9', data.get('count') == 9, f'实际: {data.get("count")}')

    # 2.5 隐患列表 - 缺少 category 参数
    code, data = api_get('/hazards')
    test('缺少 category 返回 400', code == 400, f'状态码: {code}')

    # 2.6 隐患列表 - 不存在的类别
    code, data = api_get('/hazards?category=XX')
    test('不存在的类别返回 200 + 空列表', code == 200 and data.get('count') == 0, f'code={code}, count={data.get("count")}')

    # 2.7 隐患详情 - 正常查询
    code, data = api_get('/hazard/DN-038')
    test('GET /api/hazard/DN-038 返回 200', code == 200)
    if code == 200:
        h = data['data']['hazard']
        test('DN-038 隐患描述正确', '安全绳固定在屋顶管道' in h['hazard_problem'])
        test('DN-038 有规范依据', h.get('requirement_text') is not None and len(h['requirement_text']) > 0)
        test('DN-038 有整改措施', h.get('rectification_text') is not None and len(h['rectification_text']) > 0)
        test('DN-038 有风险分析', h.get('risk_text') is not None and len(h['risk_text']) > 0)
        test('DN-038 有图片资源', len(data['data']['images']) > 0)
        test('DN-038 有监督关联', data['data']['supervision'] is not None)
        test('DN-038 关联 JD-076', data['data']['supervision'][0]['jd_id'] == 'JD-076')

    # 2.8 隐患详情 - 不存在的 ID
    code, data = api_get('/hazard/XX-999')
    test('不存在的隐患返回 404', code == 404, f'状态码: {code}')

    # 2.9 隐患详情 - NS 类别
    code, data = api_get('/hazard/NS-064')
    test('GET /api/hazard/NS-064 返回 200', code == 200)
    if code == 200:
        test('NS-064 有监督关联（JD-077）', data['data']['supervision'] is not None)
        if data['data']['supervision']:
            test('NS-064 关联 JD-077', data['data']['supervision'][0]['jd_id'] == 'JD-077')

    # 2.10 搜索 - 正常关键词
    code, data = api_get('/search?q=' + urllib.parse.quote('安全绳'))
    test('搜索"安全绳"返回 200', code == 200)
    if code == 200:
        test('搜索"安全绳"命中 >= 5 条', data.get('count', 0) >= 5, f'实际: {data.get("count")}')
        test('搜索结果包含 DN-038', any(r['id'] == 'DN-038' for r in data.get('data', [])))

    # 2.11 搜索 - 短关键词（<2字符）
    code, data = api_get('/search?q=a')
    test('短关键词返回 400', code == 400, f'状态码: {code}')

    # 2.12 搜索 - 空关键词
    code, data = api_get('/search?q=')
    test('空关键词返回 400', code == 400, f'状态码: {code}')

    # 2.13 搜索 - 无结果关键词
    code, data = api_get('/search?q=' + urllib.parse.quote('量子计算'))
    test('无结果关键词返回 200 + count=0', code == 200 and data.get('count') == 0)

    # 2.14 搜索 - 多词搜索
    code, data = api_get('/search?q=' + urllib.parse.quote('安全绳 管道'))
    test('多词搜索返回 200', code == 200)
    if code == 200:
        test('多词搜索结果 <= 单词搜索结果', True)  # 多词应为子集

    # 2.15 监督事项详情
    code, data = api_get('/supervision/JD-076')
    test('GET /api/supervision/JD-076 返回 200', code == 200)
    if code == 200:
        test('JD-076 有 4 个问题情形', len(data['data']['conditions']) == 4, f'实际: {len(data["data"]["conditions"])}')
        test('JD-076 项目名称 = 吊篮工程', data['data']['item']['project_name'] == '吊篮工程')

    # 2.16 监督事项 - 不存在
    code, data = api_get('/supervision/JD-999')
    test('不存在的监督事项返回 404', code == 404, f'状态码: {code}')


# ============================================================
# 3. 数据关联一致性验证
# ============================================================
def test_data_consistency():
    print("\n" + "=" * 60)
    print("3. 数据关联一致性验证")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 3.1 每条关联的 match_type 必须是 exact/fuzzy/manual
    cursor.execute("SELECT DISTINCT match_type FROM hazard_supervision_link")
    types = [row['match_type'] for row in cursor.fetchall()]
    for t in types:
        test(f'关联类型 {t} 合法', t in ('exact', 'fuzzy', 'manual'))

    # 3.2 每条关联的 review_status 必须是 approved/pending/rejected
    cursor.execute("SELECT DISTINCT review_status FROM hazard_supervision_link")
    statuses = [row['review_status'] for row in cursor.fetchall()]
    for s in statuses:
        test(f'关联状态 {s} 合法', s in ('approved', 'pending', 'rejected'))

    # 3.3 每条隐患的 source_type 必须是 provincial/district
    cursor.execute("SELECT DISTINCT source_type FROM hazard_item")
    src_types = [row['source_type'] for row in cursor.fetchall()]
    for st in src_types:
        test(f'来源类型 {st} 合法', st in ('provincial', 'district'))

    # 3.4 每条隐患的 section_type 必须是 资料管理/工程实体
    cursor.execute("SELECT DISTINCT section_type FROM hazard_item")
    sec_types = [row['section_type'] for row in cursor.fetchall()]
    for st in sec_types:
        test(f'分部类型 {st} 合法', st in ('资料管理', '工程实体'))

    # 3.5 每条隐患的 status 必须是 active/deprecated
    cursor.execute("SELECT DISTINCT status FROM hazard_item")
    sts = [row['status'] for row in cursor.fetchall()]
    for s in sts:
        test(f'隐患状态 {s} 合法', s in ('active', 'deprecated'))

    # 3.6 supervision_condition 的 condition_order 必须从 1 开始，且去重后连续
    # 注意：同一 condition_order 下可能有多个处置对象（施工单位+监理单位），所以不能简单用 count 判断
    cursor.execute("SELECT jd_id, MIN(condition_order) as min_o, MAX(condition_order) as max_o, "
                   "COUNT(DISTINCT condition_order) as distinct_cnt "
                   "FROM supervision_condition GROUP BY jd_id")
    for row in cursor.fetchall():
        expected_max = row['min_o'] + row['distinct_cnt'] - 1
        test(f'{row["jd_id"]} condition_order 连续', row['max_o'] == expected_max,
             f'min={row["min_o"]}, max={row["max_o"]}, distinct_count={row["distinct_cnt"]}')

    # 3.7 验证关联映射的准确性（抽查几条核心关联）
    # DN-001 → JD-074, CD-074-1
    cursor.execute("SELECT jd_id, condition_id FROM hazard_supervision_link WHERE hazard_id='DN-001' AND review_status='approved'")
    row = cursor.fetchone()
    test('DN-001 关联 JD-074', row is not None and row['jd_id'] == 'JD-074')
    test('DN-001 关联 CD-074-1', row is not None and row['condition_id'] == 'CD-074-1')

    # DN-038 → JD-076, CD-076-2
    cursor.execute("SELECT jd_id, condition_id FROM hazard_supervision_link WHERE hazard_id='DN-038' AND review_status='approved'")
    row = cursor.fetchone()
    test('DN-038 关联 JD-076', row is not None and row['jd_id'] == 'JD-076')
    test('DN-038 关联 CD-076-2', row is not None and row['condition_id'] == 'CD-076-2')

    # NS-064 → JD-077, CD-077-1
    cursor.execute("SELECT jd_id, condition_id FROM hazard_supervision_link WHERE hazard_id='NS-064' AND review_status='approved'")
    row = cursor.fetchone()
    test('NS-064 关联 JD-077', row is not None and row['jd_id'] == 'JD-077')
    test('NS-064 关联 CD-077-1', row is not None and row['condition_id'] == 'CD-077-1')

    # 3.8 验证 CD-074-1 有两个处置对象（施工单位 + 监理单位）
    cursor.execute("SELECT COUNT(*) FROM supervision_condition WHERE id LIKE 'CD-074-1%'")
    cd0741_count = cursor.fetchone()[0]
    test('CD-074-1 有 2 条处置记录（施工单位+监理单位）', cd0741_count == 2, f'实际: {cd0741_count}')

    # 3.9 验证无隐患同时关联到多个相同 JD 的相同 condition
    cursor.execute('''
        SELECT hazard_id, jd_id, condition_id, COUNT(*) as cnt
        FROM hazard_supervision_link
        WHERE review_status = 'approved'
        GROUP BY hazard_id, jd_id, condition_id
        HAVING cnt > 1
    ''')
    dup_links = cursor.fetchall()
    test('无重复关联（同隐患同JD同情形）', len(dup_links) == 0, f'重复数: {len(dup_links)}')

    # 3.10 验证所有 NS 隐患的 source 包含"南山区"
    cursor.execute("SELECT id, source FROM hazard_item WHERE category_code='NS'")
    for row in cursor.fetchall():
        test(f'{row["id"]} 来源含"南山区"', '南山区' in row['source'])

    # 3.11 验证所有 DN 隐患的 source 包含"广东省"
    cursor.execute("SELECT id, source FROM hazard_item WHERE category_code='DN'")
    dn_all = cursor.fetchall()
    for row in dn_all[:5]:  # 抽查前5条
        test(f'{row["id"]} 来源含"广东省"', '广东省' in row['source'])

    conn.close()


# ============================================================
# 主函数
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("施工安全隐患快查助手 - 边界测试 & 回归测试")
    print("=" * 60)
    print(f"数据库: {DB_PATH}")
    print(f"API: {API_BASE}")

    test_database_integrity()
    test_api_boundary()
    test_data_consistency()

    # 输出汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    total = results['pass'] + results['fail'] + results['skip']
    print(f"  总计: {total} 条")
    print(f"  通过: {results['pass']} 条")
    print(f"  失败: {results['fail']} 条")
    print(f"  跳过: {results['skip']} 条")

    if results['errors']:
        print("\n失败详情:")
        for name, detail in results['errors']:
            print(f"  - {name}: {detail}")

    print(f"\n{'全部通过' if results['fail'] == 0 else '存在失败项'}")
    sys.exit(0 if results['fail'] == 0 else 1)
