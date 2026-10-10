# 办公室助岗自动排班工具（学工办 B4229）

电气工程学院 2026-2027 学年第一学期 · 学工办助岗自动排班小工具。
基于 Python + tkinter，支持课表 OCR 导入、智能排班、Word 导出。

---

## 一、环境要求

- Windows 10/11 64 位
- Python 3.9 ~ 3.12（推荐 3.10/3.11，PaddleOCR 兼容性最好）

## 二、安装依赖

```bash
pip install python-docx
pip install paddlepaddle          # CPU 版即可；有 GPU 可装 paddlepaddle-gpu
pip install "paddleocr>=2.7,<3.0"
```

> 如果不需要 OCR 功能，只手动录课表，可以不装 paddleocr，程序会自动降级为手动录入模式。

## 三、运行

```bash
python office_scheduler.py
```

---

## 四、使用流程（严格按这个顺序操作）

### 第 1 步：录入学生课表（区域A）

1. 在「学生姓名」框输入同学姓名。
2. 两种录课表方式：
   - **OCR 导入**：点【上传该同学课表图片】→ 选 png/jpg → 程序自动识别并推测课程，显示在列表里。
   - **手动录入**：点【手动新增课程】逐条填。
3. **关键安全规则**：OCR 识别出来的课程只是"推测"，必须在列表里核对（双击可编辑、选中可删除），确认无误后点【确认保存该同学课表】，才会真正进入排班池。**不点确认就不算数**。
4. 重复录入下一位同学。
5. 全部录完后点【保存全部课表到 JSON】，下次直接【从 JSON 加载】即可，不用重复传图。

### 第 2 步：执行排班（区域B）

1. 在「生成第几周」填周数（如 1、2、3…）。
2. 第一次排班或想重新均衡时，勾选【重置值班统计计数】。
3. 点【执行智能排班】，中间区域 C 会显示当周排班表。

排班规则（程序内部）：
- 每个岗位（星期×大节）先筛出没课的同学；
- 按历史值班次数**从少到多**排序，值班少的优先排；
- 每岗排 2 人；只有 1 人就排 1 人；没人就显示"无可用人员"；
- 多周连续排时，程序自动累计每人值班次数，保证整体均衡。

### 第 3 步：导出 Word（区域D）

点【导出 Word 文档 (.docx)】，文件名自动带周数，表格底部自动带上备注：
> 注：如有急事需要加班，严格服从办公室老师的工作安排。

---

## 五、PyInstaller 打包成 exe

### 5.1 安装打包工具

```bash
pip install pyinstaller
```

### 5.2 离线打包 PaddleOCR 模型（关键）

PaddleOCR 首次运行会自动下载模型到用户目录。要做成**离线 exe**，必须把模型文件夹一起打包进去，程序已写好 `_MEIPASS` 路径适配：

1. 先在开发机上跑一次：
   ```bash
   python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='ch')"
   ```
   这会把模型下载到 `C:\Users\<你>\.paddleocr\` 下。
2. 把以下三个模型文件夹复制到项目目录下的 `models/`：
   ```
   models/
   ├── ch_PP-OCRv4_det_infer/      # 检测模型
   ├── ch_PP-OCRv4_rec_infer/      # 识别模型
   └── ch_ppocr_mobile_v2.0_cls_infer/  # 方向分类模型
   ```
   （实际文件夹名以你本机下载的版本为准，路径在 `.paddleocr/whl/` 下找。）

### 5.3 打包命令

在项目目录（`office_scheduler.py` 所在目录）执行：

```bash
pyinstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "助岗排班工具" ^
  --add-data "models;models" ^
  --collect-all paddleocr ^
  --collect-all paddle ^
  --hidden-import "paddleocr" ^
  --hidden-import "docx" ^
  office_scheduler.py
```

参数说明：
- `--windowed`：不弹黑框命令行窗口。
- `--add-data "models;models"`：把离线 OCR 模型打进 exe，运行时解压到 `_MEIPASS`，程序会自动从这里读模型。
- `--collect-all paddleocr` / `--collect-all paddle`：Paddle 系列动态库和资源文件很多，必须用 collect-all 否则运行报缺模块。
- `--name`：exe 文件名。

### 5.4 打包产物

打包完成后，exe 位于：
```
dist\助岗排班工具\助岗排班工具.exe
```
注意 PyInstaller 默认生成的是**带依赖文件夹的目录模式**（onedir），这个目录整体拷贝到其他电脑就能用，不要只拷 exe 单文件。

> 如果一定要单文件 exe（`--onefile`），体积会非常大（2GB+），启动也慢，不推荐。

### 5.5 常见打包问题

| 报错 | 解决 |
|---|---|
| `ModuleNotFoundError: No module named 'paddle'` | 加 `--collect-all paddle` |
| OCR 初始化报模型找不到 | 确认 `models/` 目录里三个模型文件夹齐全，且 `--add-data "models;models"` 写对了 |
| 双击 exe 一闪而过 | 先去掉 `--windowed` 重新打包，看黑框里的报错 |
| docx 导出失败 | 加 `--hidden-import docx` 或 `--collect-all docx` |

---

## 六、文件说明

| 文件 | 作用 |
|---|---|
| `office_scheduler.py` | 主程序（单文件，包含所有逻辑） |
| `学生课表.json` | 运行后手动保存的课表数据（可拷给其他电脑） |
| `models/` | 离线 OCR 模型目录（打包用，开发时可不建） |

## 七、数据格式（JSON 备份）

```json
{
  "students": [
    {
      "name": "张三",
      "courses": [
        {"weekday": "周一", "big_section": "第一大节",
         "start_week": 1, "end_week": 16, "week_type": "all"}
      ]
    }
  ],
  "duty_counts": {"张三": 10}
}
```

`week_type` 取值：`all`（每周）、`single`（单周）、`double`（双周）。
