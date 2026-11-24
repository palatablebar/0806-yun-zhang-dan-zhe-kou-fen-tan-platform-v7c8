from flask import jsonify

LABELS = {
    "FILE_TOO_LARGE": "文件超过 256 KiB",
    "FILE_EMPTY": "文件没有内容",
    "FILE_BLANK": "文件只有空白",
    "HEADER_ONLY": "文件只有标题行",
    "HEADER_MISMATCH": "列名与字段字典不一致",
    "ENCODING_INVALID": "请使用 UTF-8 CSV",
    "CSV_MALFORMED": "CSV 引号或行格式异常",
    "ROW_LIMIT": "文件超过 2000 行",
    "FILE_REQUIRED": "请选择 CSV 文件",
    "RUN_NOT_FOUND": "批次不存在",
    "REVIEW_FIELDS": "请填写 3 至 200 字复核意见",
    "STALE_REVIEW": "批次已更新，请刷新",
    "RUN_FINALIZED": "批次已签发",
    "UNRESOLVED_ISSUES": "存在待处理差异",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "处理阶段不存在",
    "BASE_NOT_ISSUED": "基准批次未签发",
    "SOURCE_CONFLICT": "来源存在冲突记录",
    "ACCOUNT_CAP": "存在超额度账户",
    "NO_CHANGES": "重算后无差异",
    "CORRECTION_NOT_FOUND": "更正结算不存在",
}


def response(error):
    code = error.code
    status = (
        404
        if code in {"RUN_NOT_FOUND", "SAMPLE_UNKNOWN", "STAGE_UNKNOWN", "CORRECTION_NOT_FOUND"}
        else (
            409
            if code
            in {
                "STALE_REVIEW",
                "RUN_FINALIZED",
                "UNRESOLVED_ISSUES",
                "BASE_NOT_ISSUED",
                "SOURCE_CONFLICT",
                "ACCOUNT_CAP",
                "NO_CHANGES",
            }
            else 413 if code == "FILE_TOO_LARGE" else 422
        )
    )
    payload = {"code": code, "message": LABELS.get(code, code)}
    if error.keys:
        payload["records"] = error.keys
    return jsonify(payload), status
