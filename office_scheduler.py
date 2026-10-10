# -*- coding: utf-8 -*-
"""
办公室助岗自动排班工具
电气工程学院 学工办助岗 B4229
值班时间固定4个大节，工作日周一至周五。
"""

import os
import sys
import re
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ============================================================
# 资源路径处理（PyInstaller 打包后 _MEIPASS 兼容）
# ============================================================
def get_resource_path(rel_path: str = "") -> str:
    """
    获取资源绝对路径。
    - 打包后：资源解压到 sys._MEIPASS 临时目录
    - 开发时：基于脚本所在目录
    """
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel_path) if rel_path else base


# ============================================================
# 常量定义
# ============================================================
WEEKDAYS = ["周一", "周二", "周三", "周四", "周五"]

# 大节定义：名称 -> 时间段
BIG_SECTIONS = [
    ("第一大节", "1-2节 9:00-10:10"),
    ("第二大节", "3-4节 10:30-12:10"),
    ("第三大节", "5-6节 14:10-15:40"),
    ("第四大节", "7-8节 16:00-17:40"),
]
BIG_SECTION_NAMES = [b[0] for b in BIG_SECTIONS]

# 节次数字 -> 大节 映射（OCR 解析用）
SECTION_TO_BIG = {
    (1, 2): "第一大节",
    (3, 4): "第二大节",
    (5, 6): "第三大节",
    (7, 8): "第四大节",
}

WEEK_TYPE_MAP = {"all": "每周", "single": "单周", "double": "双周"}
WEEK_TYPE_REV = {v: k for k, v in WEEK_TYPE_MAP.items()}

TITLE_TEXT = "电气工程学院2026-2027学年第一学期 学工办助岗工作排班表（B4229）"
FOOT_NOTE = "注：如有急事需要加班，严格服从办公室老师的工作安排。"


# ============================================================
# 核心：冲突判定函数（严格按规格实现，不可改动）
# ============================================================
def has_conflict(courses, target_week: int, weekday: str, big_section: str) -> bool:
    """
    输入：target_week 要生成的周数 N，courses 该同学课程列表，岗位 (weekday, big_section)
    输出：True=有课冲突不能排班；False=空闲可排班
    """
    for c in courses:
        if c.get("weekday") != weekday:
            continue
        if c.get("free") is True:
            continue  # 整学期无课标记，不产生冲突
        if c.get("big_section") != big_section:
            continue
        # 条件 A：周数落在开课区间
        start_week = int(c.get("start_week", 1))
        end_week = int(c.get("end_week", 1))
        cond_a = (start_week <= target_week <= end_week)
        # 条件 B：单双周
        wt = c.get("week_type", "all")
        if wt == "all":
            cond_b = True
        elif wt == "single":
            cond_b = (target_week % 2 == 1)
        elif wt == "double":
            cond_b = (target_week % 2 == 0)
        else:
            cond_b = True
        if cond_a and cond_b:
            return True
    return False


# ============================================================
# 排班建议：自然语言解析
# ============================================================
_WEEKDAY_WORDS = {
    "周一": "周一", "星期二": "周二", "周二": "周二", "星期三": "周三",
    "周三": "周三", "星期四": "周四", "周四": "周四", "星期五": "周五",
    "周五": "周五", "星期一": "周一",
}
_BIG_WORDS = {
    "第一大节": "第一大节", "第二大节": "第二大节",
    "第三大节": "第三大节", "第四大节": "第四大节",
    "1-2节": "第一大节", "3-4节": "第二大节",
    "5-6节": "第三大节", "7-8节": "第四大节",
    "一二节": "第一大节", "三四节": "第二大节",
    "五六节": "第三大节", "七八节": "第四大节",
}
_NUM_CN = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}


def parse_suggestions_nl(text: str, known_names: list):
    """
    从自然语言文本中解析排班规则。
    返回: locks=[(name, weekday, big_section)],
          excludes=[(name, weekday, big_section)],
          limits={name: max_count}
    known_names: 已录入学生姓名列表（用于在文本中匹配人名）。
    """
    locks, excludes, limits = [], [], {}
    if not text or not known_names:
        return locks, excludes, limits

    # 兼容旧格式 "锁定/上限" 指令
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts[0] == "锁定" and len(parts) >= 4:
            locks.append((parts[1], parts[2], parts[3]))
            continue
        if parts[0] == "上限" and len(parts) >= 3:
            try:
                limits[parts[1]] = int(parts[2])
            except ValueError:
                pass
            continue

        # 自然语言：在这一行里找人名
        names_in_line = [n for n in known_names if n in line]
        # 找星期
        wd = None
        for k, v in _WEEKDAY_WORDS.items():
            if k in line:
                wd = v
                break
        # 找大节
        sec = None
        for k, v in _BIG_WORDS.items():
            if k in line:
                sec = v
                break

        # 找数字（用于"只值2次""最多1次"）
        m_num = re.search(r"([一二两三四五六七八九十\d]+)\s*次", line)
        max_count = None
        if m_num:
            raw = m_num.group(1)
            max_count = int(raw) if raw.isdigit() else _NUM_CN.get(raw)

        # 判断意图
        is_negative = bool(re.search(r"(不要|不排|别|不值|排除|免|不安排|不值)", line))
        is_limit = bool(re.search(r"(只|最多|限|不超过|不超|少排|少值|少点|一共)", line))

        for name in names_in_line:
            if is_limit and max_count is not None:
                limits[name] = max_count
            elif is_limit and max_count is None:
                # "少排点" 没写数字，默认上限1
                limits[name] = 1
            elif is_negative and wd and sec:
                excludes.append((name, wd, sec))
            elif is_negative and wd and not sec:
                # "不要排周四" → 周四四个大节全排除
                for s in BIG_SECTION_NAMES:
                    excludes.append((name, wd, s))
            elif not is_negative and wd and sec:
                locks.append((name, wd, sec))
            # 人名单独出现、没有岗位也没有次数 → 忽略

    # 去重
    locks = list(dict.fromkeys(locks))
    excludes = list(dict.fromkeys(excludes))
    return locks, excludes, limits


# ============================================================
# OCR 文本解析：从识别出的文本中推测课程
# ============================================================
# 星期映射：兼容 "周一" / "星期一" / "周三" / "星期三"
_WEEKDAY_PAT = re.compile(r"(?:周|星期)([一二三四五六日天])")
_WEEKDAY_CHAR = {"一": "周一", "二": "周二", "三": "周三",
                 "四": "周四", "五": "周五", "六": "周六",
                 "日": "周日", "天": "周日"}

# 周区间：1-16周 / 第1-16周 / 1~16周 / 第1到16周
_WEEKS_PAT = re.compile(r"第?\s*(\d{1,2})\s*[-~至到]\s*(\d{1,2})\s*周")

# 节次：1-2节 / 1,2节 / 第1-2节 / 第1、2节
_SEC_PAT = re.compile(r"第?\s*(\d{1,2})\s*[,、\-~]\s*(\d{1,2})\s*节")

# 大节直写：第一大节 / 第3-4大节
_BIG_PAT = re.compile(r"第?\s*([一二三四1-4])\s*[-~]?\s*([一二三四1-4]?)\s*大节")
_BIG_CHAR = {"一": 1, "二": 2, "三": 3, "四": 4,
             "1": 1, "2": 2, "3": 3, "4": 4}


def _section_num_to_big(n1: int, n2: int):
    lo, hi = min(n1, n2), max(n1, n2)
    for (a, b), name in SECTION_TO_BIG.items():
        if lo == a and hi == b:
            return name
    # 容错：任意落在 1-2 / 3-4 / 5-6 / 7-8 的都归并
    if lo <= 2:
        return "第一大节"
    if lo <= 4:
        return "第二大节"
    if lo <= 6:
        return "第三大节"
    return "第四大节"


def parse_courses_from_text(text: str):
    """
    将 OCR 识别出的整段文本按行切分，逐行解析为课程 dict。
    返回推测课程列表。
    """
    courses = []
    if not text:
        return courses

    # 按行处理；有些识别结果把多行挤在一行，用换行 + 常见分隔符切
    raw_lines = re.split(r"[\r\n]+", text)
    lines = []
    for ln in raw_lines:
        ln = ln.strip()
        if not ln:
            continue
        lines.append(ln)

    for line in lines:
        # 提取星期
        m_wd = _WEEKDAY_PAT.search(line)
        if not m_wd:
            continue  # 没有星期关键词，跳过
        weekday = _WEEKDAY_CHAR.get(m_wd.group(1))
        if weekday not in WEEKDAYS:
            continue  # 周末课程不排

        # 提取大节
        big_section = None
        m_big = _BIG_PAT.search(line)
        if m_big:
            a = _BIG_CHAR.get(m_big.group(1))
            b = _BIG_CHAR.get(m_big.group(2)) if m_big.group(2) else a
            if a and b:
                big_section = _section_num_to_big(a, b)
        if big_section is None:
            m_sec = _SEC_PAT.search(line)
            if m_sec:
                big_section = _section_num_to_big(int(m_sec.group(1)),
                                                  int(m_sec.group(2)))
        if big_section is None:
            continue  # 识别不出节次，跳过这行

        # 提取周区间
        m_wk = _WEEKS_PAT.search(line)
        if m_wk:
            start_week = int(m_wk.group(1))
            end_week = int(m_wk.group(2))
        else:
            start_week, end_week = 1, 16

        # 单双周
        if "单周" in line or "单" in line and "双" not in line:
            week_type = "single"
        elif "双周" in line:
            week_type = "double"
        else:
            week_type = "all"

        courses.append({
            "weekday": weekday,
            "big_section": big_section,
            "start_week": start_week,
            "end_week": end_week,
            "week_type": week_type,
        })

    # 去重
    seen = set()
    uniq = []
    for c in courses:
        key = (c["weekday"], c["big_section"], c["start_week"],
               c["end_week"], c["week_type"])
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


# ============================================================
# PaddleOCR 封装（懒加载 + 离线 _MEIPASS 资源路径）
# ============================================================
class OCREngine:
    def __init__(self):
        self._ocr = None
        self._available = None  # None=未知 True/False

    def _init(self):
        if self._available is not None:
            return self._available
        try:
            from paddleocr import PaddleOCR  # noqa: F401
        except Exception as e:
            self._available = False
            self._err = f"未安装 paddleocr：{e}"
            return False

        # 离线模型目录：打包后从 _MEIPASS/models/ 读取
        model_dir = get_resource_path(os.path.join("models"))
        try:
            kwargs = dict(use_angle_cls=True, lang="ch", show_log=False)
            det_dir = os.path.join(model_dir, "ch_PP-OCRv4_det_infer")
            rec_dir = os.path.join(model_dir, "ch_PP-OCRv4_rec_infer")
            cls_dir = os.path.join(model_dir, "ch_ppocr_mobile_v2.0_cls_infer")
            if os.path.isdir(det_dir):
                kwargs["det_model_dir"] = det_dir
                kwargs["rec_model_dir"] = rec_dir
                kwargs["cls_model_dir"] = cls_dir
            self._ocr = PaddleOCR(**kwargs)
            self._available = True
        except Exception as e:
            self._available = False
            self._err = f"OCR 初始化失败：{e}"
            return False
        return True

    def recognize(self, img_path: str):
        """返回识别出的纯文本字符串。失败抛异常。"""
        if not self._init():
            raise RuntimeError(getattr(self, "_err", "OCR 不可用"))
        result = self._ocr.ocr(img_path, cls=True)
        texts = []
        if not result:
            return ""
        # paddleocr 返回结构 [[ [box,(text,conf)], ... ]]
        for page in result:
            if not page:
                continue
            for item in page:
                try:
                    txt = item[1][0]
                    if txt:
                        texts.append(txt)
                except Exception:
                    continue
        return "\n".join(texts)


# ============================================================
# 排班核心
# ============================================================
class Scheduler:
    def __init__(self):
        # students: {name: {"name":..., "courses":[...]}}
        self.students = {}
        # duty_counts: {name: int}
        self.duty_counts = {}

    # ---- 学生管理 ----
    def upsert_student(self, name: str, courses: list):
        name = name.strip()
        if not name:
            raise ValueError("学生姓名不能为空")
        self.students[name] = {"name": name, "courses": courses}
        self.duty_counts.setdefault(name, 0)

    def remove_student(self, name: str):
        self.students.pop(name, None)
        self.duty_counts.pop(name, None)

    def reset_counts(self):
        for k in self.duty_counts:
            self.duty_counts[k] = 0

    # ---- 持久化 ----
    def save_json(self, path: str):
        data = {
            "students": list(self.students.values()),
            "duty_counts": self.duty_counts,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_json(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.students = {s["name"]: s for s in data.get("students", [])}
        self.duty_counts = dict(data.get("duty_counts", {}))
        # 补全缺省计数
        for n in self.students:
            self.duty_counts.setdefault(n, 0)

    # ---- 排班算法 ----
    def schedule(self, target_week: int, suggestions_text: str = ""):
        """
        suggestions_text 支持自然语言，例如：
          "冯林茂排周一第一大节"
          "吴洪欣本周只值1次"
          "刘劲松不要排周四"
        也兼容旧格式：锁定/上限。
        """
        known_names = list(self.students.keys())
        locks, excludes, limits = parse_suggestions_nl(suggestions_text, known_names)
        exclude_set = set(excludes)

        # 初始化空网格
        grid = [[{"names": [], "display": ""} for _ in WEEKDAYS]
                for _ in BIG_SECTIONS]
        week_placed = {}

        # 第 1 步：应用"锁定"规则
        for name, wd, sec in locks:
            try:
                r = BIG_SECTION_NAMES.index(sec)
                c = WEEKDAYS.index(wd)
            except ValueError:
                continue
            stu = self.students.get(name)
            if not stu:
                continue
            if has_conflict(stu["courses"], target_week, wd, sec):
                continue
            if (name, wd, sec) in exclude_set:
                continue  # 同时被排除的话不锁
            if week_placed.get(name, 0) >= limits.get(name, 99):
                continue
            if len(grid[r][c]["names"]) >= 2:
                continue
            grid[r][c]["names"].append(name)
            week_placed[name] = week_placed.get(name, 0) + 1

        # 第 2 步：剩余名额按值班次数均衡补排
        for r, (sec_name, _sec_time) in enumerate(BIG_SECTIONS):
            for c, wd in enumerate(WEEKDAYS):
                slot = grid[r][c]
                already = set(slot["names"])
                candidates = []
                for name, stu in self.students.items():
                    if name in already:
                        continue
                    if has_conflict(stu["courses"], target_week, wd, sec_name):
                        continue
                    if (name, wd, sec_name) in exclude_set:
                        continue
                    if week_placed.get(name, 0) >= limits.get(name, 99):
                        continue
                    candidates.append(name)
                candidates.sort(key=lambda n: (
                    self.duty_counts.get(n, 0) + week_placed.get(n, 0), n))
                need = 2 - len(slot["names"])
                for n in candidates[:max(0, need)]:
                    slot["names"].append(n)
                    week_placed[n] = week_placed.get(n, 0) + 1

        # 第 3 步：生成显示文本，累计值班计数
        for r in range(len(BIG_SECTIONS)):
            for c in range(len(WEEKDAYS)):
                slot = grid[r][c]
                slot["display"] = ("\n".join(slot["names"])
                                   if slot["names"] else "无可用人员")
                for n in slot["names"]:
                    self.duty_counts[n] = self.duty_counts.get(n, 0) + 1
        return grid


# ============================================================
# Word 导出
# ============================================================
def export_word(grid, target_week: int, path: str):
    """按样例格式导出 docx。"""
    from docx import Document
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_ALIGN_VERTICAL
    from docx.oxml.ns import qn

    doc = Document()

    # 标题
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = h.add_run(f"电气工程学院2026-2027学年第一学期 学工办助岗工作排班表"
                    f"（B4229 第{target_week}周）")
    run.font.size = Pt(16)
    run.font.bold = True
    run.font.name = "宋体"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    doc.add_paragraph()

    # 表格：1 行表头 + 4 行大节 = 5 行；列：节次 + 5 天 = 6 列
    table = doc.add_table(rows=1 + len(BIG_SECTIONS), cols=1 + len(WEEKDAYS))
    table.style = "Table Grid"
    table.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 表头
    hdr = table.rows[0].cells
    hdr[0].text = "节次\\星期"
    for j, wd in enumerate(WEEKDAYS):
        hdr[j + 1].text = wd

    # 数据行
    for i, (sec_name, sec_time) in enumerate(BIG_SECTIONS):
        cells = table.rows[i + 1].cells
        cells[0].text = f"{sec_name}\n{sec_time}"
        for j in range(len(WEEKDAYS)):
            cells[j + 1].text = grid[i][j]["display"]

    # 设置单元格字体 + 居中
    for row in table.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in p.runs:
                    r.font.size = Pt(11)
                    r.font.name = "宋体"
                    r._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # 备注
    doc.add_paragraph()
    note = doc.add_paragraph()
    note.alignment = WD_ALIGN_PARAGRAPH.LEFT
    nr = note.add_run(FOOT_NOTE)
    nr.font.size = Pt(10.5)
    nr.font.name = "宋体"
    nr._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    doc.save(path)


# ============================================================
# GUI
# ============================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("办公室助岗自动排班工具 — 学工办 B4229")
        self.geometry("1200x780")

        self.scheduler = Scheduler()
        self.ocr = OCREngine()
        # 当前正在编辑的学生课表（未确认前不进 scheduler）
        self.current_name = tk.StringVar()
        self.pending_courses = []  # OCR/手动解析出来待确认
        self.last_grid = None
        self.last_week = 1

        self._build_ui()

    # ---------- UI 构建 ----------
    def _build_ui(self):
        # 整体：顶部 paned(左A右B) + 中部 C + 底部 D
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ---- 顶部：左右两栏 ----
        top = ttk.Frame(root)
        top.pack(fill=tk.X)
        top.columnconfigure(0, weight=1, uniform="top")
        top.columnconfigure(1, weight=1, uniform="top")

        self._build_area_a(top)
        self._build_area_b(top)

        # ---- 中部 C：排班预览表格 ----
        self._build_area_c(root)

        # ---- 底部 D：导出 ----
        self._build_area_d(root)

    def _build_area_a(self, parent):
        box = ttk.LabelFrame(parent, text="区域A  学生与课表 OCR 导入")
        box.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # 姓名行
        row1 = ttk.Frame(box)
        row1.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(row1, text="学生姓名：").pack(side=tk.LEFT)
        ttk.Entry(row1, textvariable=self.current_name, width=14).pack(side=tk.LEFT)
        ttk.Button(row1, text="上传该同学课表图片",
                   command=self.on_upload_image).pack(side=tk.LEFT, padx=6)
        ttk.Button(row1, text="手动新增课程",
                   command=self.on_add_course_manual).pack(side=tk.LEFT)

        # 课程列表
        ttk.Label(box, text="推测/手动录入课程列表（选中可编辑或删除）：").pack(
            anchor=tk.W, padx=6)
        list_frame = ttk.Frame(box)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        cols = ("weekday", "big_section", "start_week", "end_week", "week_type")
        self.course_tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                        height=6)
        for c, txt, w in [("weekday", "星期", 60),
                          ("big_section", "大节", 90),
                          ("start_week", "起周", 50),
                          ("end_week", "止周", 50),
                          ("week_type", "周类型", 70)]:
            self.course_tree.heading(c, text=txt)
            self.course_tree.column(c, width=w, anchor=tk.CENTER)
        self.course_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                           command=self.course_tree.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.course_tree.configure(yscrollcommand=sb.set)
        self.course_tree.bind("<Double-1>", self.on_edit_course)

        # 操作按钮行
        ops = ttk.Frame(box)
        ops.pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(ops, text="编辑选中", command=self.on_edit_course).pack(side=tk.LEFT)
        ttk.Button(ops, text="删除选中", command=self.on_delete_course).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="清空列表", command=self.on_clear_courses).pack(side=tk.LEFT)
        ttk.Button(ops, text="确认保存该同学课表",
                   command=self.on_save_student).pack(side=tk.RIGHT, padx=4)

        # json 持久化
        jf = ttk.Frame(box)
        jf.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(jf, text="保存全部课表到 JSON",
                   command=self.on_save_json).pack(side=tk.LEFT)
        ttk.Button(jf, text="从 JSON 加载全部课表",
                   command=self.on_load_json).pack(side=tk.LEFT, padx=4)

        # 已录入学生列表
        ttk.Label(box, text="已录入学生（用于排班）：").pack(anchor=tk.W, padx=6)
        self.students_list = tk.Listbox(box, height=4)
        self.students_list.pack(fill=tk.X, padx=6, pady=(0, 6))
        stu_ops = ttk.Frame(box)
        stu_ops.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(stu_ops, text="复制选中学生课表",
                   command=self.on_copy_courses).pack(side=tk.LEFT)
        ttk.Button(stu_ops, text="删除选中学生",
                   command=self.on_remove_student).pack(side=tk.LEFT, padx=6)

    def _build_area_b(self, parent):
        box = ttk.LabelFrame(parent, text="区域B  排班参数设置")
        box.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        row = ttk.Frame(box)
        row.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(row, text="生成第几周：").pack(side=tk.LEFT)
        self.week_var = tk.StringVar(value="1")
        ttk.Entry(row, textvariable=self.week_var, width=8).pack(side=tk.LEFT)

        self.reset_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(box, text="重置值班统计计数（执行排班前清零历史次数）",
                        variable=self.reset_var).pack(anchor=tk.W, padx=6)

        ttk.Button(box, text="执行智能排班", command=self.on_run_schedule).pack(
            anchor=tk.W, padx=6, pady=6)

        # 排班建议
        ttk.Label(box, text="排班建议（可选，每行一条）：").pack(anchor=tk.W, padx=6)
        self.suggestions_text = tk.Text(box, height=4, width=30)
        self.suggestions_text.pack(fill=tk.X, padx=6, pady=(0, 2))
        ttk.Label(box,
                  text="直接写中文要求，每行一句，例如：\n"
                       "冯林茂排周一第一大节\n"
                       "吴洪欣本周只值1次\n"
                       "刘劲松不要排周四",
                  foreground="gray").pack(anchor=tk.W, padx=6)

        # 值班次数统计
        ttk.Label(box, text="值班次数统计：").pack(anchor=tk.W, padx=6, pady=(6, 0))
        self.counts_text = tk.Text(box, height=8, state=tk.DISABLED)
        self.counts_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    def _build_area_c(self, parent):
        box = ttk.LabelFrame(parent, text="区域C  排班预览表格")
        box.pack(fill=tk.BOTH, expand=True, padx=0, pady=6)

        cols = ["节次"] + WEEKDAYS
        self.grid_tree = ttk.Treeview(box, columns=cols, show="headings", height=5)
        for c in cols:
            self.grid_tree.heading(c, text=c)
            self.grid_tree.column(c, width=150, anchor=tk.CENTER)
        self.grid_tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _build_area_d(self, parent):
        box = ttk.LabelFrame(parent, text="区域D  导出操作")
        box.pack(fill=tk.X)
        ttk.Button(box, text="导出 Word 文档 (.docx)",
                   command=self.on_export_word).pack(side=tk.LEFT, padx=20, pady=8)
        ttk.Label(box, text="导出文件名自动带周数；表格底部含备注文字。").pack(
            side=tk.LEFT, padx=10)

    # ---------- 事件：区域A ----------
    def on_upload_image(self):
        name = self.current_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "请先填写学生姓名")
            return
        path = filedialog.askopenfilename(
            title="选择课表图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp")])
        if not path:
            return
        # OCR 放到子线程，避免界面卡死
        self.config(cursor="watch")
        threading.Thread(target=self._ocr_worker, args=(path,), daemon=True).start()

    def _ocr_worker(self, path):
        try:
            text = self.ocr.recognize(path)
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("OCR 失败", str(e)))
            self.after(0, lambda: self.config(cursor=""))
            return
        courses = parse_courses_from_text(text)
        self.after(0, lambda: self._after_ocr(text, courses))

    def _after_ocr(self, raw_text, courses):
        self.config(cursor="")
        if not courses:
            messagebox.showinfo(
                "OCR 结果",
                f"识别完成但未自动解析出课程。识别原文：\n{raw_text[:500]}\n\n"
                "请使用【手动新增课程】逐条录入。")
            return
        self.pending_courses = courses
        self._refresh_course_tree()
        messagebox.showinfo(
            "OCR 完成",
            f"识别到 {len(courses)} 条推测课程，请在列表中核对/编辑后，"
            f"点击【确认保存该同学课表】。\n\n识别原文预览：\n{raw_text[:300]}")

    def on_add_course_manual(self):
        win = CourseEditWindow(self, course=None,
                               on_ok=lambda c: self._add_pending_course(c))
        win.grab_set()

    def _add_pending_course(self, course):
        self.pending_courses.append(course)
        self._refresh_course_tree()

    def on_edit_course(self, _event=None):
        sel = self.course_tree.selection()
        if not sel:
            return
        idx = self.course_tree.index(sel[0])
        win = CourseEditWindow(self, course=self.pending_courses[idx],
                               on_ok=lambda c, i=idx: self._update_pending(i, c))
        win.grab_set()

    def _update_pending(self, idx, course):
        self.pending_courses[idx] = course
        self._refresh_course_tree()

    def on_delete_course(self):
        sel = self.course_tree.selection()
        if not sel:
            return
        idx = self.course_tree.index(sel[0])
        del self.pending_courses[idx]
        self._refresh_course_tree()

    def on_clear_courses(self):
        self.pending_courses = []
        self._refresh_course_tree()

    def _refresh_course_tree(self):
        for i in self.course_tree.get_children():
            self.course_tree.delete(i)
        for c in self.pending_courses:
            if c.get("free") is True:
                self.course_tree.insert("", tk.END, values=(
                    c["weekday"], c["big_section"], "—", "—", "整学期无课"))
            else:
                self.course_tree.insert("", tk.END, values=(
                    c["weekday"], c["big_section"], c["start_week"],
                    c["end_week"],
                    WEEK_TYPE_MAP.get(c["week_type"], c["week_type"])))

    def on_save_student(self):
        name = self.current_name.get().strip()
        if not name:
            messagebox.showwarning("提示", "请填写学生姓名")
            return
        if not self.pending_courses:
            if not messagebox.askyesno("确认", "当前没有课程，确认保存为空课表？"):
                return
        # 校验
        for c in self.pending_courses:
            try:
                int(c["start_week"]); int(c["end_week"])
            except Exception:
                messagebox.showerror("错误", f"周数无效：{c}")
                return
            if int(c["start_week"]) > int(c["end_week"]):
                messagebox.showerror("错误", f"起周大于止周：{c}")
                return
        self.scheduler.upsert_student(name, self.pending_courses)
        self.pending_courses = []
        self._refresh_course_tree()
        self._refresh_students_list()
        self._refresh_counts()
        messagebox.showinfo("完成", f"已保存 {name} 的课表。")

    def on_copy_courses(self):
        sel = self.students_list.curselection()
        if not sel:
            messagebox.showwarning("提示", "请先在下面列表里选中一个学生")
            return
        src_name = self.students_list.get(sel[0])
        src = self.scheduler.students.get(src_name)
        if not src:
            return
        # 深拷贝课程列表到待确认区
        self.pending_courses = [dict(c) for c in src["courses"]]
        self._refresh_course_tree()
        # 清空姓名框，让用户输入新同学名字
        self.current_name.set("")
        messagebox.showinfo(
            "已复制课表",
            f"已把【{src_name}】的课表复制到上方列表。\n\n"
            f"请在姓名框输入新同学的名字，然后点【确认保存该同学课表】。")

    def on_remove_student(self):
        sel = self.students_list.curselection()
        if not sel:
            return
        name = self.students_list.get(sel[0])
        self.scheduler.remove_student(name)
        self._refresh_students_list()
        self._refresh_counts()

    def _refresh_students_list(self):
        self.students_list.delete(0, tk.END)
        for n in sorted(self.scheduler.students.keys()):
            self.students_list.insert(tk.END, n)

    def _refresh_counts(self):
        self.counts_text.configure(state=tk.NORMAL)
        self.counts_text.delete("1.0", tk.END)
        if not self.scheduler.duty_counts:
            self.counts_text.insert(tk.END, "（暂无学生）")
        else:
            for n, cnt in sorted(self.scheduler.duty_counts.items(),
                                 key=lambda x: (x[1], x[0])):
                self.counts_text.insert(tk.END, f"{n}：{cnt} 次\n")
        self.counts_text.configure(state=tk.DISABLED)

    def on_save_json(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="学生课表.json")
        if not path:
            return
        self.scheduler.save_json(path)
        messagebox.showinfo("完成", f"已保存到 {path}")

    def on_load_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            self.scheduler.load_json(path)
        except Exception as e:
            messagebox.showerror("加载失败", str(e))
            return
        self._refresh_students_list()
        self._refresh_counts()
        messagebox.showinfo("完成", f"已加载 {len(self.scheduler.students)} 名学生。")

    # ---------- 事件：区域B ----------
    def on_run_schedule(self):
        try:
            week = int(self.week_var.get())
        except ValueError:
            messagebox.showwarning("提示", "周数必须是整数")
            return
        if not self.scheduler.students:
            messagebox.showwarning("提示", "还没有任何学生课表，请先在区域A录入")
            return
        if self.reset_var.get():
            self.scheduler.reset_counts()
        suggestions = self.suggestions_text.get("1.0", tk.END)
        grid = self.scheduler.schedule(week, suggestions_text=suggestions)
        self.last_grid = grid
        self.last_week = week
        self._refresh_grid_tree()
        self._refresh_counts()

    def _refresh_grid_tree(self):
        for i in self.grid_tree.get_children():
            self.grid_tree.delete(i)
        for r, (sec_name, sec_time) in enumerate(BIG_SECTIONS):
            values = [f"{sec_name}\n{sec_time}"]
            for c in range(len(WEEKDAYS)):
                values.append(self.last_grid[r][c]["display"])
            self.grid_tree.insert("", tk.END, values=values)

    # ---------- 事件：区域D ----------
    def on_export_word(self):
        if self.last_grid is None:
            messagebox.showwarning("提示", "请先执行排班再导出")
            return
        default_name = (f"电气工程学院2026-2027第一学期 "
                        f"学工办助岗工作排班表（B4229 第{self.last_week}周）.docx")
        path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word", "*.docx")],
            initialfile=default_name)
        if not path:
            return
        try:
            export_word(self.last_grid, self.last_week, path)
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
            return
        messagebox.showinfo("完成", f"已导出：\n{path}")


# ============================================================
# 课程编辑弹窗
# ============================================================
class CourseEditWindow(tk.Toplevel):
    def __init__(self, master, course, on_ok):
        super().__init__(master)
        self.title("编辑课程")
        self.on_ok = on_ok
        self.resizable(False, False)

        c = course or {"weekday": "周一", "big_section": "第一大节",
                       "start_week": 1, "end_week": 18, "week_type": "all",
                       "free": False}

        week_choices = [str(i) for i in range(1, 19)]

        ttk.Label(self, text="星期：").grid(row=0, column=0, padx=8, pady=6, sticky=tk.E)
        self.weekday_var = tk.StringVar(value=c["weekday"])
        ttk.Combobox(self, textvariable=self.weekday_var, values=WEEKDAYS,
                      width=10, state="readonly").grid(row=0, column=1)

        ttk.Label(self, text="大节：").grid(row=1, column=0, padx=8, pady=6, sticky=tk.E)
        self.big_var = tk.StringVar(value=c["big_section"])
        ttk.Combobox(self, textvariable=self.big_var, values=BIG_SECTION_NAMES,
                      width=12, state="readonly").grid(row=1, column=1)

        # 整学期无课开关
        ttk.Label(self, text="整学期无课：").grid(row=2, column=0, padx=8, pady=6, sticky=tk.E)
        self.free_var = tk.StringVar(value="是" if c.get("free") else "否")
        free_cb = ttk.Combobox(self, textvariable=self.free_var, values=["是", "否"],
                               width=10, state="readonly")
        free_cb.grid(row=2, column=1)
        free_cb.bind("<<ComboboxSelected>>", self._on_free_changed)

        ttk.Label(self, text="起周：").grid(row=3, column=0, padx=8, pady=6, sticky=tk.E)
        self.start_var = tk.StringVar(value=str(c["start_week"]))
        self.start_cb = ttk.Combobox(self, textvariable=self.start_var,
                                     values=week_choices, width=12, state="readonly")
        self.start_cb.grid(row=3, column=1)

        ttk.Label(self, text="止周：").grid(row=4, column=0, padx=8, pady=6, sticky=tk.E)
        self.end_var = tk.StringVar(value=str(c["end_week"]))
        self.end_cb = ttk.Combobox(self, textvariable=self.end_var,
                                   values=week_choices, width=12, state="readonly")
        self.end_cb.grid(row=4, column=1)

        ttk.Label(self, text="周类型：").grid(row=5, column=0, padx=8, pady=6, sticky=tk.E)
        self.wt_var = tk.StringVar(value=WEEK_TYPE_MAP.get(c["week_type"], "每周"))
        self.wt_cb = ttk.Combobox(self, textvariable=self.wt_var,
                                  values=list(WEEK_TYPE_MAP.values()),
                                  width=10, state="readonly")
        self.wt_cb.grid(row=5, column=1)

        # 初始状态：如果默认是"无课"，灰掉下面三项
        self._on_free_changed()

        bf = ttk.Frame(self)
        bf.grid(row=6, column=0, columnspan=2, pady=10)
        ttk.Button(bf, text="确定", command=self._ok).pack(side=tk.LEFT, padx=8)
        ttk.Button(bf, text="取消", command=self.destroy).pack(side=tk.LEFT)

    def _on_free_changed(self, _event=None):
        """选"是"时灰掉起止周和周类型；选"否"时恢复。"""
        state = "disabled" if self.free_var.get() == "是" else "readonly"
        for w in (self.start_cb, self.end_cb, self.wt_cb):
            w.configure(state=state)

    def _ok(self):
        free = (self.free_var.get() == "是")
        course = {
            "weekday": self.weekday_var.get(),
            "big_section": self.big_var.get(),
            "free": free,
        }
        if not free:
            try:
                sw = int(self.start_var.get())
                ew = int(self.end_var.get())
            except ValueError:
                messagebox.showwarning("提示", "周数必须是整数")
                return
            if sw > ew:
                messagebox.showwarning("提示", "起周不能大于止周")
                return
            course["start_week"] = sw
            course["end_week"] = ew
            course["week_type"] = WEEK_TYPE_REV.get(self.wt_var.get(), "all")
        else:
            # 无课时给默认值，不影响逻辑
            course["start_week"] = 1
            course["end_week"] = 18
            course["week_type"] = "all"
        self.on_ok(course)
        self.destroy()


# ============================================================
# 入口
# ============================================================
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
