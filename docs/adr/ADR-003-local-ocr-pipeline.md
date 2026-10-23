# ADR-003：图片型 PDF 的本地 OCR 与异步入库架构

- Date: 2026-10-21
- Status: Accepted
- 关联：[SPEC-kb-ocr-ingest](../specs/SPEC-kb-ocr-ingest.md)、[意图声明](../intent/kb-ocr-ingest.md)、[bugs/pdf-low-quality-extraction](../../../bugs/pdf-low-quality-extraction/fix.md)

## 决策

1. **OCR 引擎：本地 RapidOCR（`rapidocr-onnxruntime`）**
2. **PDF 页渲染：PyMuPDF（`fitz`）**
3. **执行模型：SQLite 任务表 + ProcessPoolExecutor 单 worker，API 改 202 异步契约**

## 理由与否决方案

### 1. OCR 引擎

- ✅ RapidOCR：数据不出内网（EDA 场景资料敏感）、零调用费用、模型随 wheel 离线可用（Windows 无网络依赖）、中文印刷体精度足够、纯 Python 集成简单。代价：新增 ~100MB 依赖（onnxruntime），CPU 1-3 秒/页。
- ❌ 云端视觉大模型（智谱 GLM-4V）：版面复杂页识别质量更高，但按 token 计费、文档图片需上传外部（合规顾虑）、限流复杂。访谈中用户明确选本地。
- ❌ 传统云 OCR（百度/腾讯）：精度高但需新开账号计费，再引入一套外部服务依赖，与"数据不出内网"冲突。

### 2. 页渲染

pypdf 无渲染能力，OCR 需要页面位图。

- ✅ PyMuPDF：pip 单包安装、自带 CJK 字体、渲染快（~百 ms/页）、无系统级外部程序。许可为 AGPL/商业双许可——本项目为内部系统不分发，AGPL 义务不触发（若未来开源分发需重评）。
- ❌ pdf2image + poppler：需 Windows 预装 poppler 二进制，部署摩擦大。
- ❌ 让用户自行转图片再上传：把问题推回用户，违背"自动降级"决策。

### 3. 执行模型

OCR 分钟级耗时，同步接口必超时。

- ✅ SQLite 任务表 + 进程池：状态跨进程可见、重启后可清理残留任务；进程隔离避免 onnxruntime 卡死事件循环；与现有 DB（aiosqlite 同文件）一致，无新中间件。MVP 单 worker 串行，够用（上传是低频管理操作）。
- ❌ FastAPI BackgroundTasks/线程池：GIL + onnxruntime 部分释放不完全，仍可能拖慢 API；且进程重启任务丢失无痕迹。
- ❌ 消息队列/专业任务框架（Celery 等）：单机内部系统引入 broker 属过度设计。
- ❌ 同步 + 页数上限：访谈中用户明确选异步任务化。

## 后果

- 上传/重入库接口契约变更（202 + task_id），前端 KnowledgeBase.vue 必须配套改造——破坏性变更，一次性切换不留兼容路径（内部系统，无第三方调用方）。
- `kb.ingest.LowQualityExtraction` 的"整份拒绝"语义被按页 OCR 取代，相应回归测试需改写（不是删除）。
- 后端进程需保证任务表初始化幂等（`CREATE TABLE IF NOT EXISTS`）。
