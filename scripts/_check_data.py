#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('database/hazard.db')
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print('=== 关联记录的 review_status ===')
cursor.execute('SELECT review_status, COUNT(*) as cnt FROM hazard_supervision_link GROUP BY review_status')
rows = cursor.fetchall()
for r in rows:
    print(f'  {r["review_status"]}: {r["cnt"]}条')

print()
print('=== 完整关联记录 ===')
cursor.execute('SELECT * FROM hazard_supervision_link')
rows = cursor.fetchall()
for r in rows:
    print(f'  {r["hazard_id"]} -> {r["jd_id"]} | condition={r["condition_id"]} | status={r["review_status"]}')

conn.close()
