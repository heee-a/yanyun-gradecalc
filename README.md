# yanyun-gradecalc · 燕云十六声装备毕业度计算器

[![CI](https://github.com/heee-a/yanyun-gradecalc/actions/workflows/ci.yml/badge.svg)](https://github.com/heee-a/yanyun-gradecalc/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

给装备拍张照（手机拍屏幕也行），自动识别词条，按你的流派算**毕业度**。

```
◆ sample_1.jpg  承音 110阶  易相套装4/4  造诣 1476
   ✓ 劲: 72.2（100%）  权重1
   ✓ 最大外功攻击: 114.1（98%）  权重1
   ✓ [转]会心率: 12.7%（100%）  权重1
   ✓ 对首领单位增伤: 4.8%（100%）  权重1
   ✓ 劲: 72.2（100%）  权重1
   ✓ 无名剑法·蓄力技增伤: 8.9%（100%）  权重1
   ==> 「破竹鸢」毕业度 99.7（毕业）
```

## 它是怎么工作的

1. **OCR 识别**（RapidOCR，本机运行，图片不离开电脑）读出词条名与数值；
2. **斜拍校正配对**：手机拍屏幕必然歪。工具把数值按 x 坐标聚成“数值列”，词条名
   与数值做保序动态规划配对，并用**类型约束**（百分比词条只能配百分比数值）+
   纵向偏移线性漂移模型锁正——实测手机斜拍照片可正确配对；
3. **流派权重**：从社区的「毕业率进阶计算器」xlsx（破竹樽/牵丝玉/破竹尘/破竹鸢/牵丝翊/裂石威/裂石钧/DIY…）
   自动提取该流派建模用到的属性集合，生成 `builds/<流派>.json`；
4. **毕业度**：单词条得分 = 数值 ÷ 110阶满值（封顶 100%），按流派权重加权平均；
   同时给出所有已导入流派的对比，告诉你这件装备最适合谁。

## 快速开始

```bash
pip install -e .

# 1) 导入流派数据（指向你手里计算器 xlsx 所在目录，之后新增流派重跑即可）
ygc import-build 路径/到/计算器目录

# 2) 识别并评分（与所有流派对比，报最适配的）
ygc score 装备照片.jpg

# 3) 只看指定流派 / 导出 JSON
ygc score 照片1.jpg 照片2.jpg --build 破竹鸢 --json-out result.json

# 只识别不评分
ygc recognize 照片.jpg
```

## 整套识别 + 心法切换（网页版核心玩法）

网页版按「全套 8 件」组织：武器1/武器2/冠胄/胸甲/胫甲/腕甲/环/佩 各一个拍照格，
逐格拍完后在页面里**核对主词条、勾选副词条、改数值**，然后：

1. 选**流派**（13 个，与站点同步）；
2. 选**心法**——第三/第四心法的候选与默认值来自站点数据（如破竹鸢：断石之构/三穷致知 + 易水歌/征人归）；
3. 选**弓决**（精准/会心/会意）、**套装**、**兵装**（本系/双系）；
4. 点「计算整套毕业率」→ 返回**与 leoq7 管理器完全同源**的毕业率、DPS、总伤和面板属性
   （引擎直接加载站点同款 runtime + WASM，计算逻辑 100% 一致）。

整套引擎依赖 Node.js（>=18）与站点运行时文件：

```bash
node --version              # 需要已安装 Node
python scripts/fetch_engine.py   # 首次使用下载运行时到 engine/vendor/（约 1.7MB）
ygc-web                     # 启动网页版
```

## 网页版（手机 / 电脑都能用）

不想敲命令行？启动本地网页版（先装 flask：`pip install -e ".[web]"`）：

```bash
ygc-web            # 或 python -m yanyun_gradecalc.web
```

```
网页版已就绪，浏览器打开：
  http://localhost:8000        ← 电脑
  http://192.168.x.x:8000      ← 手机（连同一 Wi-Fi）
```

手机打开局域网地址，直接拍照上传即可；识别出词条后可在页面上改数值、
剔除误识别行，毕业度实时重算。若手机打不开，在 Windows 防火墙放行 Python。
OCR 全程在本机运行，照片不会离开你的电脑。

拍照片的姿势：**拍清楚词条区域**即可，不需要摆正——工具专门为斜拍做了校正。
避免反光和摩尔纹过重的角度。

## 持续更新（核心设计）

- **新增流派**：拿到新的计算器 xlsx → 丢进目录 → 重跑 `ygc import-build` → 完成；
- **词条满值**：`data/affix_max.json` 已对齐 [yysls.leoq7.com 装备毕业率管理器](https://yysls.leoq7.com/)
  的权威数据（37 条 110 阶满值），版本更新后可重跑
  `python scripts/update_from_site.py` 重新提取（数据文件放 `source_data/`）；
- **流派权重**：12 个流派的权重来自该站点的「最优 40 词条」分布统计
  （每个流派最优先刷什么词条一目了然，例如多数流派已不用“劲”而改用
  “最小外功攻击/敏”），`builds/<流派>.json` 可自行微调；DIY 通用模板来自
  社区 DIY 计算器；
- **定音词条**：照片里带 ◆ 标记的定音词条会标注 `[定音]`，指定武学技能类
  （如 无名剑法·蓄力技增伤）按“指定武学技能增伤”满值兜底计算。

数值全部是可编辑的 JSON，引擎不依赖任何“硬编码游戏数据”。

## 已知边界

- 武器的**基础属性行**（如 最大外功攻击 199）与词条结构相同无法从版面上区分，
  工具按“数值超过满值 1.3 倍 → 疑似基础属性行”自动排除，并在报告中标注；
  若你的满值表填错了，也会在这里暴露出来；
- [转]律词条与部分特技实测可略超普通词条满值，滚动质量按 100% 封顶；
- OCR 偶发错字（造诣→造谐之类）不影响词条识别；未收录词条会保留原文并标注
  “未识别”，不会污染评分；
- 套装效果、心法等不在单件毕业度计算范围内。

## 项目结构

```
yanyun-gradecalc/
├── yanyun_gradecalc/
│   ├── ocr.py            # OCR + 斜拍校正配对（DP + 类型约束 + 漂移模型）
│   ├── stats_dict.py     # 词条字典：别名归一化 / [转]荐◆标记 / 数值解析
│   ├── build_import.py   # 计算器 xlsx -> builds/<流派>.json
│   ├── scoring.py        # 满值表 / 滚动质量 / 流派加权毕业度
│   ├── web.py            # 网页版后端（Flask，手机/电脑通用）
│   ├── static/index.html # 网页版前端（单文件，纯色背景，无外部依赖）
│   └── cli.py            # import-build / recognize / score
├── data/affix_max.json   # 110阶词条满值表（来源：yysls.leoq7.com）
├── builds/               # 12 个流派（10 个 best40 权重 + 破竹樽/DIY 计算器导入）
├── scripts/              # update_from_site.py（站点数据更新）/ api_push.py
├── engine/               # 整套毕业率引擎（Node + 站点同款 WASM runtime）
├── scripts/              # 站点数据同步 / 引擎下载 / API 推送
└── tests/                # 20 个测试（网页与引擎层不依赖 OCR 模型）
```

## 声明

- 本项目与网易/Everstone Studio 无关，仅供个人装备养成参考；
- 不含任何游戏自动化、宏或内存读取；OCR 全程本地运行；
- 满值表与最优词条分布数据来自 [yysls.leoq7.com 装备毕业率管理器](https://yysls.leoq7.com/)，
  流派数据结构提取自公开流传的社区计算器，感谢原制作者；
  如站点数据有更新，欢迎提 PR 同步。

## License

[MIT](LICENSE)
