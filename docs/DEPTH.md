# 云账单折扣分摊台规则登记

- 规模：中型

## 功能模块

| 模块 | 动作 | 接口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 样例采信 | 预览并定位坏行 | `POST /api/stages/intake` | `app/intake/service.py` | `tests/test_intake.py` |
| M2 用量归集 | 检查领域约束 | `POST /api/stages/prepare` | `app/modules/prepare.py` | `tests/test_prepare.py` |
| M3 折扣分摊 | 查看业务计算结果 | `POST /api/stages/calculate` | `app/modules/calculate.py` | `tests/test_calculate.py` |
| M4 额度复核 | 查看签收判定 | `POST /api/stages/policy` | `app/modules/policy.py` | `tests/test_policy.py` |
| M5 运行对账 | 对照输入、采信和隔离行 | `POST /api/stages/balance` | `app/modules/reconcile.py` | `tests/test_reconcile.py` |
| M6 批次复核 | 执行批次并签发或暂缓 | `POST /api/runs、PATCH /api/runs/<id>` | `app/review/service.py` | `tests/test_review.py` |
| M7 证据交付 | 下载复核清单 | `GET /api/runs/<id>/evidence` | `app/evidence/render.py` | `tests/test_evidence.py` |
| M8 更正结算 | 基于签发批次对迟到来源整批重算并入账差额 | `POST /api/runs/<id>/corrections` | `app/correction/service.py` | `tests/test_correction.py` |

## 输入陷阱

| 编号 | 规则 | 处理 | 测试 |
|---|---|---|---|
| TRAP-02 | 去除 BOM | `app/intake/reader.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-03 | 按逻辑记录读取引号内换行 | `app/intake/reader.py` | `tests/test_intake.py::test_quoted_newline_is_one_logical_record` |
| TRAP-04 | 重复表头计入忽略行 | `app/intake/service.py` | `tests/test_intake.py::test_repeated_header_is_counted` |
| TRAP-05 | 异常列数隔离 | `app/intake/schema.py` | `tests/test_intake.py::test_extra_column_is_isolated` |
| TRAP-06 | 归一化全角数字和千分位 | `app/intake/numeric.py` | `tests/test_intake.py::test_full_width_and_grouping_are_canonical` |
| TRAP-07 | 空值行隔离 | `app/intake/numeric.py` | `tests/test_intake.py::test_sentinel_keeps_row_out_of_total` |
| TRAP-08 | 记录键保留前导零 | `app/intake/schema.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-14 | 冲突版本都进入隔离 | `app/intake/resolve.py` | `tests/test_intake.py::test_duplicate_conflict_removes_both_copies` |
| TRAP-16 | 引号未闭合时拒收文件 | `app/intake/reader.py` | `tests/test_intake.py::test_unclosed_quote_invalidates_source` |
| TRAP-18 | 区分空文件、全空白和仅表头 | `app/intake/reader.py` | `tests/test_intake.py::test_empty_states_have_distinct_causes` |
| TRAP-26 | 拒绝旧版本复核 | `app/review/store.py` | `tests/test_review.py::test_review_optimistic_lock` |
| TRAP-27 | 共享折扣重新分摊后，来源未改但金额变化的账户必须入账 | `app/correction/service.py` | `tests/test_correction.py::test_changed_accounts_include_unmodified_shared_reallocation` |
| TRAP-28 | 重算金额未变的账户不生成零额记录 | `app/correction/service.py` | `tests/test_correction.py::test_unchanged_accounts_generate_no_zero_lines` |
| TRAP-29 | 来源冲突、基准未签发或任一户超额度时整份阻断并列出记录键 | `app/correction/service.py` | `tests/test_correction.py::test_over_cap_blocks_entire_correction_with_record_keys` |
| TRAP-30 | 同一来源重试保留一条有效更正，不得重复累计 | `app/review/store.py` | `tests/test_correction.py::test_same_source_retry_keeps_single_correction_without_double_count` |

## 领域反例

金额以分为最小单位。归集正用量，以最大余额法补齐尾分。同余数时按记录键排序。账户额度不足退回复核。

逐组预期结论见 `tests/test_policy.py`，计算过程证据见 `tests/test_calculate.py`。

## 更正结算

批次签发后来源仍可能迟到修订。更正在原签发批次上追加，不改动原签发证据：

- 以最新来源整批重算每户折扣，与基准签发金额叠加历次更正后的累计值逐户对照；
- 仅重算金额发生变化的账户入账（含共享折扣重新分摊后来源未改但金额变化的账户），金额未变不生成零额记录；来源中删除的账户按零额冲正；
- 来源存在隔离行或分组约束不满足（SOURCE_CONFLICT）、基准批次未签发（BASE_NOT_ISSUED）、任一账户重算金额超额度（ACCOUNT_CAP）时整份阻断，响应列出记录键，不写入任何更正行；
- 更正按（基准批次， 来源指纹）幂等，同一来源重试返回既有更正；不同来源依次入账，每笔差额都对照最新累计值计算，累计结果始终等于最新来源的整批重算。
