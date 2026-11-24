# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED` 或 `HELD`。冲突返回 409，客户端读取新版本后重试。

`GET /api/runs/<id>/evidence` 下载内含运行清单、行号隔离、业务证据和复核信息的 JSON。

`POST /api/runs/<id>/corrections` 接收与执行批次相同的输入，基于已签发批次生成更正结算：整批重算最新来源，仅把金额发生变化的账户写入更正行。重复提交同一来源返回既有更正。`GET /api/runs/<id>/corrections` 列出该批次的更正，`GET /api/corrections/<id>` 查询单份更正。

更正阻断返回 409 并在 `records` 中列出记录键：`SOURCE_CONFLICT` 来源存在冲突记录、`ACCOUNT_CAP` 存在超额度账户、`BASE_NOT_ISSUED` 基准批次未签发、`NO_CHANGES` 重算后无差异。基准批次不存在返回 404。
