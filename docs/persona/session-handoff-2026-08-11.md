# 会话交接(2026-08-11)

> 状态快照,供新会话/继续工作使用。

## 仓库与约束
- 仓库 `D:\MatrAIx`;包 `matraix`;远程:`fork` = Ornn8/MatrAIx-Persona-8B(用户私有/公开 fork),`origin` = 官方(禁 push)。
- **推送前必须经用户确认**(用户 2026-08 明确"别自作主张推送")。commit 可自动。
- 用户跑过的实验(任务配置/jobs/论文)不上传开源仓库。
- Windows:中文数据需 `PYTHONUTF8=1`;venv 在 `.venv\Scripts\python.exe`。

## 最近完成
- 中国 persona 管线(CGSS2017/2021、WVS):crosswalk、提取、LLM 富化、200 人池 + wvs-cn 池、消费画像 10 字段/人。全部验证过(validate 0 错误、smoke 全过)。
- 前端 i18n 重构(响应官方 PR #20 评审):单语言 pack(en-US/zh-CN)、懒加载(zh 独立 chunk)、LocalePicker、默认 en-US、personaLabelKeys 独立。typecheck/build 绿。
- TDD:vitest 26 用例全绿(commit c5ee976,在 pr 分支)。

## 进行中(未完成)
- **PR #20 官方评审第 3 点**:runtime/persona 语言的显式字段(job/request `language`)+ Follow UI|en|zh 覆盖 + 每次运行持久化生效语言与来源 + 后端不把浏览器 locale 当权威。用户已批准做(工程量无所谓)。待办:调研 job 配置/渲染调用链 → 设计字段模型 → 后端/前端实现 → 持久化 → 验证提交。
- main 上未同步 TDD 提交(c5ee976)→ 待用户确认是否 cherry-pick + push。
- PR #20 重构完成,待回复官方评审(可合并后回复)。

## 待用户确认
- main 同步 TDD 提交 + push
- PR #20 回复官方

## 常用验证
```bash
$env:PYTHONUTF8='1'
.venv\Scripts\python.exe persona\curation\existing_data\scripts\smoke_china_pipeline.py
.venv\Scripts\python.exe persona\human_extraction\scripts\validate_extraction.py --input <file> --schema persona\schema\dimensions.json
cd application\playground\frontend; npm run typecheck; npm run build; node node_modules\vitest\vitest.mjs run
```
