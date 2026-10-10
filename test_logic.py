# -*- coding: utf-8 -*-
"""核心逻辑自测：冲突函数 + 排班均衡"""
from office_scheduler import has_conflict, Scheduler, parse_courses_from_text, WEEKDAYS, BIG_SECTION_NAMES

# 1. 冲突函数测试
stu = {"courses": [
    {"weekday": "周一", "big_section": "第一大节", "start_week": 1, "end_week": 16, "week_type": "all"},
    {"weekday": "周三", "big_section": "第三大节", "start_week": 3, "end_week": 10, "week_type": "single"},
    {"weekday": "周五", "big_section": "第四大节", "start_week": 1, "end_week": 8, "week_type": "double"},
]}

cases = [
    ("周一", "第一大节", 1, True),   # all
    ("周一", "第一大节", 9, True),
    ("周一", "第二大节", 1, False),  # 不同大节
    ("周三", "第三大节", 3, True),   # single 单周
    ("周三", "第三大节", 4, False),  # 双周不上
    ("周三", "第三大节", 11, False), # 超出 end_week
    ("周五", "第四大节", 2, True),   # double 双周
    ("周五", "第四大节", 3, False),  # 单周不上
    ("周五", "第四大节", 9, False),   # 超出 end_week
]
ok = True
for wd, bs, wk, expect in cases:
    got = has_conflict(stu["courses"], wk, wd, bs)
    flag = "OK" if got == expect else "FAIL"
    if got != expect:
        ok = False
    print(f"[{flag}] {wd} {bs} 第{wk}周 -> 冲突={got} (期望 {expect})")

# 2. 排班均衡测试：4个学生都全空，排班应均匀
s = Scheduler()
for name in ["甲", "乙", "丙", "丁"]:
    s.upsert_student(name, [])  # 没课 = 全空

grid = s.schedule(1)
print("\n=== 第1周排班（4人全空，每岗2人）===")
for r, bs in enumerate(BIG_SECTION_NAMES):
    for c, wd in enumerate(WEEKDAYS):
        print(f"  {bs} {wd}: {grid[r][c]['display']!r}")
print("值班计数：", s.duty_counts)

# 3. 再排一周，计数应均衡
grid2 = s.schedule(2)
print("\n=== 第2周排班后计数 ===")
print("值班计数：", s.duty_counts)
assert len(set(s.duty_counts.values())) <= 2, "计数差异过大"

# 4. OCR 解析测试
sample = """
星期一第1-2节 1-16周
周三 第3-4大节 5-12周 单周
周五第5,6节 1-8周 双周
星期日 第7-8节 1-16周
"""
courses = parse_courses_from_text(sample)
print("\n=== OCR 解析结果 ===")
for c in courses:
    print(" ", c)
# 周日应被过滤
assert not any(c["weekday"] == "周日" for c in courses), "周末课程应过滤"

print("\nALL PASS" if ok else "\nHAS FAIL")
